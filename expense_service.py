
from database import add_expense, initialize_database
from expense_extractor import extract_expenses


def process_transcription(transcription):
    """Extract expenses from text and save valid records."""

    result = extract_expenses(transcription)
    print("DEBUG - Gemini extraction:", result.model_dump())
    initialize_database()

    saved_expenses = []

    for expense in result.expenses:
        # Do not save records without a clear amount.
        if expense.amount is None or expense.amount <= 0:
            continue

        # Ask the user to clarify missing required fields later.
        if not expense.category or not expense.expense_date:
            continue

        expense_id = add_expense(
            amount=expense.amount,
            category=expense.category,
            expense_date=expense.expense_date,
            merchant=expense.merchant,
            payment_method=expense.payment_method,
            description=expense.description,
            original_transcription=transcription,
        )

        saved_expenses.append({
            "id": expense_id,
            "amount": expense.amount,
            "category": expense.category,
            "merchant": expense.merchant,
            "expense_date": expense.expense_date,
            "payment_method": expense.payment_method,
            "description": expense.description,
        })
    print("DEBUG - Saved expenses:", saved_expenses)
    return saved_expenses
