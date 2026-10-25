
import sqlite3
from pathlib import Path

DB_PATH = Path("data") / "expense_ledger.db"

if not DB_PATH.exists():
    print("Database not found:", DB_PATH.resolve())
    raise SystemExit(1)

with sqlite3.connect(DB_PATH) as conn:
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM expenses")
    count = cursor.fetchone()[0]
    print(f"Current records: {count}")

    confirm = input("Delete ALL test transactions? Type DELETE: ")

    if confirm == "DELETE":
        cursor.execute("DELETE FROM expenses")
        print(f"Deleted {cursor.rowcount} records.")
        print("Database table structure is preserved.")
    else:
        print("Cancelled. No records deleted.")
