
import sqlite3
from config import DATABASE_PATH


def get_connection():
    """Connect to the SQLite database."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    """Create the transactions table and migrate existing databases."""
    connection = get_connection()

    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                merchant TEXT,
                expense_date TEXT NOT NULL,
                payment_method TEXT,
                description TEXT,
                original_transcription TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                transaction_type TEXT NOT NULL DEFAULT 'expense',
                currency TEXT NOT NULL DEFAULT 'INR',
                party TEXT,
                notes TEXT
            )
        """)

        # Add new columns to an existing database without deleting records.
        existing_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(expenses)"
            ).fetchall()
        }

        migrations = {
            "transaction_type": (
                "ALTER TABLE expenses ADD COLUMN "
                "transaction_type TEXT NOT NULL DEFAULT 'expense'"
            ),
            "currency": (
                "ALTER TABLE expenses ADD COLUMN "
                "currency TEXT NOT NULL DEFAULT 'INR'"
            ),
            "party": (
                "ALTER TABLE expenses ADD COLUMN party TEXT"
            ),
            "notes": (
                "ALTER TABLE expenses ADD COLUMN notes TEXT"
            ),
        }

        for column, sql in migrations.items():
            if column not in existing_columns:
                connection.execute(sql)

        # Populate new fields for records created by the old application.
        connection.execute("""
            UPDATE expenses
            SET party = merchant
            WHERE party IS NULL AND merchant IS NOT NULL
        """)

        connection.execute("""
            UPDATE expenses
            SET notes = description
            WHERE notes IS NULL AND description IS NOT NULL
        """)

        connection.commit()

    finally:
        connection.close()


def add_transaction(
    amount,
    category,
    expense_date,
    transaction_type="expense",
    currency="INR",
    party=None,
    merchant=None,
    payment_method=None,
    description=None,
    notes=None,
    original_transcription=None,
):
    """Save one income or expense transaction."""

    if transaction_type not in ("income", "expense"):
        raise ValueError(
            "transaction_type must be 'income' or 'expense'."
        )

    try:
        amount=float(amount)
    except(TypeError,ValueError):
        raise ValueError("Transaction amount must be positive.")

    if not category or not category.strip():
        raise ValueError("Transaction category cannot be empty.")

    if not expense_date:
        raise ValueError("Transaction date is required.")

    # Keep the old merchant and description fields populated for compatibility.
    if party is None:
        party = merchant

    if merchant is None:
        merchant = party

    if notes is None:
        notes = description

    if description is None:
        description = notes

    connection = get_connection()

    try:
        cursor = connection.execute("""
            INSERT INTO expenses (
                amount,
                category,
                merchant,
                expense_date,
                payment_method,
                description,
                original_transcription,
                transaction_type,
                currency,
                party,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            amount,
            category,
            merchant,
            expense_date,
            payment_method,
            description,
            original_transcription,
            transaction_type,
            currency,
            party,
            notes,
        ))

        connection.commit()
        return cursor.lastrowid

    finally:
        connection.close()


def add_expense(
    amount,
    category,
    expense_date,
    merchant=None,
    payment_method=None,
    description=None,
    original_transcription=None,
    transaction_type="expense",
    currency="INR",
    party=None,
    notes=None,
):
    """
    Backward-compatible function used by the existing app.py.
    Supports income too when transaction_type is supplied.
    """

    return add_transaction(
        amount=amount,
        category=category,
        expense_date=expense_date,
        transaction_type=transaction_type,
        currency=currency,
        party=party,
        merchant=merchant,
        payment_method=payment_method,
        description=description,
        notes=notes,
        original_transcription=original_transcription,
    )


def get_all_expenses():
    """
    Return all transactions, newest date first.
    The old function name is retained for app.py compatibility.
    """

    connection = get_connection()

    try:
        rows = connection.execute("""
            SELECT *
            FROM expenses
            ORDER BY expense_date DESC, id DESC
        """).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def get_all_transactions():
    """Return all income and expense transactions."""

    return get_all_expenses()


if __name__ == "__main__":
    initialize_database()
    print("Database initialized successfully!")
    print("Database location:", DATABASE_PATH)
