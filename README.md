# Voice Expense Logger

A voice-enabled expense tracking application that converts natural-language transaction descriptions into structured expense records. Users can describe expenses using voice or text, review the extracted details, and maintain an expense ledger.

## Project Overview

Manually recording daily expenses can be time-consuming. The Voice Expense Logger simplifies this process by allowing users to describe a transaction in natural language. The application processes the input, extracts relevant transaction details, and stores the structured record in a local SQLite database.

## Key Features

- **Voice Input:** Supports speech-to-text processing through the AudicLabs API.
- **Expense Extraction:** Uses Google Gemini to extract structured details from transaction descriptions.
- **Expense Ledger:** Stores expense records in a SQLite database.
- **Transaction Details:** Organizes information such as amount, category, payment method, description, and transaction date when available.
- **Expense Summary:** Displays recorded expenses and total spending.
- **CSV Export:** Supports exporting expense records for further analysis.
- **Text-to-Speech:** Integrates AudicLabs text-to-speech functionality for supported audio responses.

## Technology Stack

- **Programming Language:** Python
- **User Interface:** Streamlit
- **LLM:** Google Gemini
- **Speech Services:** AudicLabs Speech-to-Text and Text-to-Speech APIs
- **Database:** SQLite
- **Configuration:** Python environment variables using `.env`
- **Data Export:** CSV

## How It Works

1. The user describes an expense using voice or text.
2. Voice input is converted into text using the speech-to-text service.
3. Gemini extracts the transaction information into structured fields.
4. The application processes the extracted information and saves the expense to SQLite.
5. The user can review the ledger, view expense summaries, and export records.

## Project Setup

### 1. Clone the repository

```bash
git clone https://github.com/Pulluri-Vanaja/voice-expense-logger.git
cd voice-expense-logger
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
```

Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root and add your own API credentials:

```env
AUDICLABS_API_KEY=your_audiclabs_api_key
AUDICLABS_BASE_URL=https://api.audiclabs.com/v1
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
DATABASE_PATH=data/expense_ledger.db
```

Use the exact environment variable names expected by your `config.py`. Never commit your real API keys or tokens to GitHub.

### 5. Run the application

```bash
streamlit run app.py
```

Streamlit will display a local URL in the terminal. Open it in your browser to use the application.

## Security and Configuration

- API credentials are stored in environment variables rather than directly in source code.
- The `.env` file and local database should be excluded from version control.
- External API functionality depends on valid credentials, service availability, and applicable API limits.

## Future Improvements

- Add monthly and category-wise spending analytics.
- Support budget limits and spending alerts.
- Improve handling of ambiguous or incomplete transactions.
- Add recurring-expense detection and more advanced reports.

## Author

**Vanaja Pulluri**

Developed as a voice-based expense tracking project for the AudicLabs AI Application Developer technical assessment.
