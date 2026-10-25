
from unittest.mock import patch

from database import initialize_database, get_all_expenses
from expense_extractor import Expense, ExpenseExtraction
from expense_service import process_transcription


def test_process_transcription():
    initialize_database()

    # Prepare fake Gemini output without calling the real API.
    fake_result = ExpenseExtraction(
        expenses=[
            Expense(
                amount=120,
                category="Food",
                merchant="Cafe",
                expense_date="2026-10-24",
                payment_method="UPI",
                description="Coffee"
            ),
            Expense(
                amount=None,
                category="Food",
                merchant=None,
                expense_date="2026-10-24",
                payment_method=None,
                description="Amount unclear"
            )
        ]
    )

    with patch(
        "expense_service.extract_expenses",
        return_value=fake_result
    ):
        saved = process_transcription(
            "I bought coffee and mentioned another unclear expense."
        )

    assert len(saved) == 1
    assert saved[0]["amount"] == 120
    assert saved[0]["category"] == "Food"

    # Confirm the expense was saved to SQLite.
    all_expenses = get_all_expenses()
    assert any(
        row["id"] == saved[0]["id"]
        for row in all_expenses
    )

    print("Expense service test passed!")


if __name__ == "__main__":
    test_process_transcription()
