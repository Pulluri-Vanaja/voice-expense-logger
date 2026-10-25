
import re
import time
import logging
from datetime import date, timedelta
from typing import Literal, Optional

from google import genai
from google.genai import errors
from pydantic import BaseModel, Field

from config import GEMINI_API_KEY, GEMINI_MODEL


logger = logging.getLogger(__name__)


class Expense(BaseModel):
    # New assessment fields
    transaction_type: Literal["income", "expense"] = Field(
        default="expense",
        description="Whether money was received (income) or paid (expense).",
    )
    currency: str = Field(
        default="INR",
        description="Currency code, such as INR.",
    )
    party: Optional[str] = Field(
        default=None,
        description="Person, customer, vendor, or business involved.",
    )
    notes: str = Field(
        default="",
        description="Additional details about the transaction.",
    )

    # Existing fields retained for compatibility with app.py
    amount: Optional[float] = Field(
        default=None,
        description="Positive transaction amount, or null if unclear.",
    )
    category: Optional[str] = Field(
        default=None,
        description="Category such as Food, Travel, Shopping, Sales, Bills, or Other.",
    )
    merchant: Optional[str] = Field(
        default=None,
        description="Merchant or shop name, or null if unknown.",
    )
    expense_date: Optional[str] = Field(
        default=None,
        description="Transaction date in YYYY-MM-DD format.",
    )
    date_reference: Optional[str] = Field(
        default=None,
        description=(
            "Use today, yesterday, an explicit YYYY-MM-DD date, "
            "or null when the date reference is unknown."
        ),
    )
    payment_method: Optional[str] = Field(
        default=None,
        description="Payment method, such as Cash, UPI, Card, or Bank Transfer.",
    )
    description: str = Field(
        default="",
        description="Short description of the transaction.",
    )


class ExpenseExtraction(BaseModel):
    expenses: list[Expense] = Field(
        description="Every separate income or expense transaction mentioned.",
    )


def call_gemini_with_retries(client, prompt):
    """Call Gemini and retry temporary service errors."""

    for attempt in range(3):
        try:
            return client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": ExpenseExtraction,
                    "temperature": 0,
                },
            )

        except errors.APIError as error:
            if error.code in (429, 500, 502, 503, 504) and attempt < 2:
                wait_seconds = 2 ** (attempt + 1)

                logger.warning(
                    "Gemini API error %s. Retry %s/2 in %s seconds.",
                    error.code,
                    attempt + 1,
                    wait_seconds,
                )

                time.sleep(wait_seconds)
                continue

            raise

    raise RuntimeError(
        "Gemini could not process the request after three attempts."
    )


def resolve_expense_date(expense, today):
    """Resolve and validate a transaction date."""

    reference = (expense.date_reference or "").strip().lower()

    if reference == "today":
        return today.isoformat()

    if reference == "yesterday":
        return (today - timedelta(days=1)).isoformat()

    if reference:
        try:
            return date.fromisoformat(reference).isoformat()
        except ValueError:
            logger.warning(
                "Ignoring unrecognized date reference: %s",
                reference,
            )

    if expense.expense_date:
        try:
            return date.fromisoformat(
                expense.expense_date.strip()
            ).isoformat()
        except ValueError:
            logger.warning(
                "Ignoring invalid extracted date: %s",
                expense.expense_date,
            )

    # Preserve the existing behavior for unspecified dates.
    return today.isoformat()


def correct_dates_from_transcription(transcription, result, today):
    """
    Correct dates when today or yesterday appears before an
    expense action, matching the statement to its description.

    This preserves the existing relative-date correction logic.
    """

    yesterday = today - timedelta(days=1)

    pattern = re.compile(
        r"\b(?P<reference>yesterday|today)\b"
        r"[\s,!.:-]{0,30}"
        r"(?P<statement>(?:i\s+)?"
        r"(?:spent|paid|bought|purchased|ordered)\b"
        r"[^.!?]*)",
        flags=re.IGNORECASE,
    )

    for match in pattern.finditer(transcription):
        reference = match.group("reference").lower()
        statement = match.group("statement").lower()

        if reference == "yesterday":
            resolved_date = yesterday.isoformat()
        else:
            resolved_date = today.isoformat()

        for expense in result.expenses:
            description = (expense.description or "").strip().lower()

            if description and description in statement:
                expense.expense_date = resolved_date
                expense.date_reference = reference
                break

    return result


def extract_expenses(transcription: str) -> ExpenseExtraction:
    """Extract income and expense transactions from transcribed text."""

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Add it to your .env file."
        )

    if not transcription or not transcription.strip():
        raise ValueError("Transcription cannot be empty.")

    today = date.today()
    yesterday = today - timedelta(days=1)

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""
Extract every separate financial transaction from the transcription.
Transactions may be income, expenses, or a mixture of both.

REFERENCE DATES:
Today is {today.isoformat()}.
Yesterday is {yesterday.isoformat()}.

REQUIRED RULES:
1. Extract each separate transaction individually.
2. Set transaction_type to "income" when money is received.
   Set transaction_type to "expense" when money is paid or spent.
3. Amount must be positive. If the amount is unclear, use null.
4. Set currency to the explicitly stated currency when known.
   Use INR when the speaker says rupees or when the currency is
   clearly implied by the context. Do not invent a currency otherwise.
5. Extract the person, customer, vendor, or business into party.
6. Extract merchant as well when a merchant or shop is mentioned.
7. Extract category from the context. Do not force every transaction
   into an expense category. Income categories may include Sales,
   Services, Salary, or Other.
8. Extract payment_method when stated, such as Cash, UPI, Card,
   or Bank Transfer. Use null if unknown.
9. Put additional context in notes and a short transaction summary
   in description.
10. Use date_reference="yesterday" and date
    {yesterday.isoformat()} for transactions explicitly associated
    with yesterday.
11. Use date_reference="today" and date {today.isoformat()}
    for transactions explicitly associated with today.
12. For explicit calendar dates, use YYYY-MM-DD.
13. If a transaction has no stated date, use today's date and
    date_reference="today", following the existing application behavior.
14. Do not apply a date mentioned for one transaction to unrelated
    transactions.
15. Do not invent a party, amount, payment method, or transaction detail.
16. Return all transactions, including multiple transactions in one note.
17. Return data matching the supplied JSON schema.
18. Use specific categories that match the transaction's meaning:
    - Transport or travel expenses → "Transport"
    - Grocery purchases → "Groceries"
    - Food or restaurant purchases → "Food"
    - Product sales or money received from selling goods → "Sales"
    - Salary received → "Salary"
    - Service payments received → "Services"
    Do not replace a specific category with a broader category when the context is clear.

19. Preserve the exact payment method when stated. Use "Debit card" when a debit card is explicitly mentioned, "Credit card" when a credit card is explicitly mentioned, "UPI" for UPI payments, "Cash" for cash payments, and "Bank Transfer" for bank transfers. Use "Card" only when the speaker does not specify debit or credit card.

20. Always return transaction dates in YYYY-MM-DD format. Never return "today" or "yesterday" as the date value. Use date_reference to indicate relative dates.

21. Do not classify a transaction as "Food" simply because groceries are purchased. Use "Groceries" when the speaker explicitly mentions groceries.

22. Keep party and merchant separate when the information supports it. Do not invent either field when the speaker does not identify a person, vendor, or business.

23. For each transaction, independently determine its transaction type, amount, currency, party, merchant, category, payment method, date, date reference, notes, and description. Do not copy details from another transaction unless the speaker explicitly connects them.

TRANSCRIPTION:
{transcription}
"""

    response = call_gemini_with_retries(client, prompt)

    if response.parsed is not None:
        result = response.parsed
    elif response.text:
        result = ExpenseExtraction.model_validate_json(response.text)
    else:
        raise ValueError("Gemini returned an empty response.")

    # Validate amounts and normalize dates.
    for expense in result.expenses:
        if expense.amount is not None and expense.amount <= 0:
            raise ValueError(
                f"Transaction amount must be positive: {expense.amount}"
            )

        expense.expense_date = resolve_expense_date(expense, today)

        # Keep party and merchant aligned where possible.
        if not expense.party and expense.merchant:
            expense.party = expense.merchant

        if not expense.merchant and expense.party:
            expense.merchant = expense.party

        # Keep notes and description aligned for compatibility.
        if not expense.notes and expense.description:
            expense.notes = expense.description

        if not expense.description and expense.notes:
            expense.description = expense.notes

    # Preserve the existing transcription-based date correction.
    result = correct_dates_from_transcription(
        transcription=transcription,
        result=result,
        today=today,
    )

    return result
