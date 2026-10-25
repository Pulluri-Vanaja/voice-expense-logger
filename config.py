
import os
from pathlib import Path
from dotenv import load_dotenv

# Load variables from the .env file
load_dotenv()

# Main project folder
BASE_DIR = Path(__file__).resolve().parent

# AudiClabs API settings
AUDICLABS_API_KEY = os.getenv("AUDICLABS_API_KEY")
AUDICLABS_BASE_URL = os.getenv(
    "AUDICLABS_BASE_URL",
    "https://api.audiclabs.com/v1"
)

# Gemini API settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Database location
DATABASE_PATH = Path(
    os.getenv("DATABASE_PATH", "data/expense_ledger.db")
)

# Convert a relative database path into an absolute path
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = BASE_DIR / DATABASE_PATH


def validate_config():
    """Check whether the required API keys are configured."""
    missing = []

    if not AUDICLABS_API_KEY:
        missing.append("AUDICLABS_API_KEY")

    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")

    if missing:
        raise RuntimeError(
            "Missing configuration in .env: "
            + ", ".join(missing)
        )
