
from expense_extractor import Expense, ExpenseExtraction


def test_valid_expense():
    expense = Expense(
        amount=250,
        category="Food",
        merchant="Restaurant",
        expense_date="2026-10-24",
        payment_method="UPI",
        description="Lunch"
    )

    assert expense.amount == 250
    assert expense.category == "Food"
    assert expense.expense_date == "2026-10-24"


def test_multiple_expenses():
    result = ExpenseExtraction(
        expenses=[
            Expense(
                amount=100,
                category="Food",
                merchant=None,
                expense_date="2026-10-24",
                payment_method="Cash",
                description="Tea"
            ),
            Expense(
                amount=500,
                category="Travel",
                merchant=None,
                expense_date="2026-10-24",
                payment_method="UPI",
                description="Auto fare"
            )
        ]
    )

    assert len(result.expenses) == 2
    assert result.expenses[0].amount == 100
    assert result.expenses[1].amount == 500


def test_unknown_details():
    expense = Expense(
        amount=None,
        category=None,
        merchant=None,
        expense_date=None,
        payment_method=None,
        description="Expense details unclear"
    )

    assert expense.amount is None
    assert expense.category is None
    assert expense.expense_date is None


def test_empty_expense_list():
    result = ExpenseExtraction(expenses=[])

    assert result.expenses == []


if __name__ == "__main__":
    test_valid_expense()
    test_multiple_expenses()
    test_unknown_details()
    test_empty_expense_list()

    print("All expense extraction model tests passed!")
