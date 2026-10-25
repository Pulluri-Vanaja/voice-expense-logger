
from database import initialize_database, add_expense, get_all_expenses

initialize_database()

expense_id = add_expense(
    amount=150,
    category="Food",
    expense_date="2026-10-24",
    merchant="Test Restaurant",
    payment_method="UPI",
    description="Lunch",
    original_transcription="I spent 150 rupees on lunch"
)

print("Expense saved with ID:", expense_id)

expenses = get_all_expenses()
print("Total saved expenses:", len(expenses))
print("Latest expense:", expenses[0])
