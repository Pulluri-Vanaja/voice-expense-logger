
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import streamlit as st
import google.generativeai as genai

from config import validate_config
from database import initialize_database, get_all_expenses, get_connection
from audiclabs_client import AudiClabsClient, AudiClabsAPIError
from audiclabs_tts import AudiClabsTTSClient
from expense_extractor import extract_expenses


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Voice Expense Logger",
    page_icon="🎙️",
    layout="wide",
)

DEFAULTS = {
    "transcription_widget": "",
    "extracted_expenses": [],
    "original_transcription": "",
    "editor_version": 0,
    "clear_transcription_on_next_run": False,
    "tts_audio": None,
    "tts_snapshot": None,
    "confirmation_checked": False,
    "confirmation_reset_pending": False,
    "available_tts_voices": {},
    "preferred_tts_voice": None,
    "readback_text": "",
    "readback_language": "en",
    "ledger_answer": "",
    "ledger_answer_audio": None,
    "ledger_answer_question": "",
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value

if st.session_state["clear_transcription_on_next_run"]:
    st.session_state["transcription_widget"] = ""
    st.session_state["clear_transcription_on_next_run"] = False


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def model_to_dict(model):
    if isinstance(model, dict):
        return model.copy()
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    if hasattr(model, "dict"):
        return model.dict()
    raise TypeError(f"Unsupported transaction type: {type(model).__name__}")


def optional_text(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    value = str(value).strip()
    return value or None


def normalize_transaction(transaction):
    item = model_to_dict(transaction)

    defaults = {
        "transaction_type": "expense",
        "currency": "INR",
        "party": None,
        "merchant": None,
        "category": None,
        "amount": None,
        "expense_date": None,
        "date_reference": None,
        "payment_method": None,
        "notes": "",
        "description": "",
    }

    for key, value in defaults.items():
        item.setdefault(key, value)

    if not item.get("party"):
        item["party"] = item.get("merchant")
    if not item.get("merchant"):
        item["merchant"] = item.get("party")
    if not item.get("notes"):
        item["notes"] = item.get("description")

    return item


def extract_list(payload, possible_keys):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in possible_keys:
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def get_runtime_languages():
    """Load STT languages and include Telugu as an explicit option."""
    import logging
    import requests
    from config import AUDICLABS_API_KEY, AUDICLABS_BASE_URL

    logger = logging.getLogger(__name__)
    options = {"auto": "Auto detect"}
    try:
        response = requests.get(
            f"{AUDICLABS_BASE_URL.rstrip('/')}/stt/languages",
            headers={"Authorization": f"Bearer {AUDICLABS_API_KEY}"},
            timeout=(10, 30),
        )
        response.raise_for_status()
        items = extract_list(
            response.json(),
            ("languages", "data", "results"),
        )

        for item in items:
            if isinstance(item, str):
                code, label = item, item
            elif isinstance(item, dict):
                code = (
                    item.get("code")
                    or item.get("language_code")
                    or item.get("id")
                    or item.get("value")
                )
                label = (
                    item.get("name")
                    or item.get("label")
                    or item.get("language")
                    or code
                )
            else:
                continue

            if isinstance(label, dict):
                label = label.get("name") or label.get("code") or code

            if code:
                options[str(code)] = str(label)
    except (requests.RequestException, ValueError, TypeError) as error:
        logger.warning("Could not load AudiClabs STT languages: %s", error
        )

    
    return options


def translate_readback(text, language_code):
    """Translate spoken confirmation text into the selected language."""
    if language_code == "en":
        return text

    language_names = {
        "hi": "Hindi",
        "te": "Telugu",
    }

    target_language = language_names.get(language_code)
    if not target_language:
        raise ValueError("Unsupported read-back language.")

    api_key = (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
    )

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is missing. Add it to your .env file."
        )

    genai.configure(api_key=api_key)

    model_name = (
        os.getenv("GEMINI_MODEL")
        or "gemini-2.5-flash-lite"
    )

    model = genai.GenerativeModel(model_name)

    prompt = f"""
Translate this transaction confirmation into natural {target_language}.

Rules:
- Preserve every amount, number, date, currency and payment detail.
- Do not add or remove transaction information.
- Keep shop, person and vendor names unchanged.
- Translate the surrounding sentences naturally.
- Return only the translated text.

Text:
{text}
"""

    response = model.generate_content(prompt)
    translated = (getattr(response, "text", None) or "").strip()

    if not translated:
        raise ValueError("Gemini returned an empty translation.")

    return translated


def build_readback(rows, language_code="en"):
    """Build a confirmation summary from the editable transaction rows."""
    lines = ["Please review these transactions."]

    for index, row in enumerate(rows, start=1):
        kind = str(row.get("transaction_type") or "expense").lower()
        action = "income received" if kind == "income" else "expense recorded"

        amount = row.get("amount")
        currency = str(row.get("currency") or "INR").upper()
        party = optional_text(row.get("party")) or "unspecified party"
        category = optional_text(row.get("category")) or "unspecified category"
        transaction_date = (
            optional_text(row.get("expense_date")) or "unspecified date"
        )
        payment = (
            optional_text(row.get("payment_method"))
            or "unspecified payment method"
        )
        notes = optional_text(row.get("notes"))

        try:
            amount_text = f"{float(amount):,.2f} {currency}"
        except (TypeError, ValueError):
            amount_text = f"{amount} {currency}"

        line = (
            f"Transaction {index}: {action}, {amount_text}, "
            f"party {party}, category {category}, "
            f"date {transaction_date}, payment method {payment}."
        )

        if notes:
            line += f" Notes: {notes}."

        lines.append(line)

    lines.append(
        "Please check the table and confirm only if everything is correct."
    )

    return translate_readback(" ".join(lines), language_code)


def snapshot_rows(rows):
    return json.dumps(
        rows,
        sort_keys=True,
        default=str,
        ensure_ascii=False,
    )


def reset_confirmation():
    st.session_state["confirmation_reset_pending"] = True
    st.session_state["tts_audio"] = None
    st.session_state["tts_snapshot"] = None


def apply_pending_confirmation_reset():
    if st.session_state["confirmation_reset_pending"]:
        st.session_state["confirmation_checked"] = False
        st.session_state["confirmation_reset_pending"] = False


def validate_rows(rows):
    valid_rows = []
    errors = []

    for index, row in enumerate(rows, start=1):
        try:
            transaction_type = optional_text(row.get("transaction_type"))
            if transaction_type not in ("income", "expense"):
                raise ValueError("Type must be income or expense.")

            amount = pd.to_numeric(row.get("amount"), errors="coerce")
            if pd.isna(amount) or float(amount) <= 0:
                raise ValueError("Amount must be a positive number.")

            currency = optional_text(row.get("currency"))
            category = optional_text(row.get("category"))
            date_value = optional_text(row.get("expense_date"))

            if not currency:
                raise ValueError("Currency cannot be empty.")
            if not category:
                raise ValueError("Category cannot be empty.")
            if not date_value:
                raise ValueError("Date is required.")

            parsed_date = pd.to_datetime(
                date_value,
                format="%Y-%m-%d",
                errors="coerce",
            )

            if pd.isna(parsed_date):
                raise ValueError("Date must use YYYY-MM-DD format.")

            valid_rows.append({
                "transaction_type": transaction_type,
                "amount": float(amount),
                "currency": currency.upper(),
                "party": optional_text(row.get("party")),
                "category": category,
                "expense_date": parsed_date.strftime("%Y-%m-%d"),
                "payment_method": optional_text(row.get("payment_method")),
                "notes": optional_text(row.get("notes")) or "",
            })

        except (ValueError, TypeError, OverflowError) as error:
            errors.append(f"Row {index}: {error}")

    return valid_rows, errors


def save_transactions(rows):
    """Save all confirmed transactions in a single database transaction."""
    connection = None

    try:
        connection = get_connection()

        for row in rows:
            connection.execute(
                """
                INSERT INTO expenses (
                    amount, category, merchant, expense_date,
                    payment_method, description, original_transcription,
                    transaction_type, currency, party, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["amount"],
                    row["category"],
                    row["party"],
                    row["expense_date"],
                    row["payment_method"],
                    row["notes"],
                    st.session_state["original_transcription"],
                    row["transaction_type"],
                    row["currency"],
                    row["party"],
                    row["notes"],
                ),
            )

        connection.commit()
        return True, None

    except Exception as error:
        if connection is not None:
            connection.rollback()
        logger.exception("Saving transactions failed")
        return False, str(error)

    finally:
        if connection is not None:
            connection.close()


def get_runtime_tts_voices():
    """Load available TTS voices dynamically from AudiClabs."""
    client = AudiClabsTTSClient()
    voices = client.get_voices()

    return [
        voice for voice in voices
        if isinstance(voice, dict) and voice.get("voice_id")
    ]


def get_english_voice():
    """Choose an available English voice from the runtime voice list."""
    voices = get_runtime_tts_voices()

    if not voices:
        raise ValueError("AudiClabs returned no available TTS voices.")

    voice = next(
        (
            item for item in voices
            if str(item.get("language", "")).lower() == "en"
        ),
        voices[0],
    )

    return voice["voice_id"]


# --------------------------------------------------
# Ledger question helpers
# --------------------------------------------------

def parse_ledger_question(question, available_categories):
    """
    Parse common English ledger questions into filters.

    This initial version deliberately uses transparent rules rather than
    allowing an LLM to calculate or invent totals.
    """
    q = question.lower().strip()
    today = date.today()

    transaction_type = "all"

    income_words = (
        "income", "earned", "earning", "received", "sales", "revenue"
    )
    expense_words = (
        "expense", "expenses", "spent", "spend", "paid", "cost", "bought"
    )

    has_income = any(word in q for word in income_words)
    has_expense = any(word in q for word in expense_words)

    if has_income and not has_expense:
        transaction_type = "income"
    elif has_expense and not has_income:
        transaction_type = "expense"

    start_date = None
    end_date = None

    if "yesterday" in q:
        start_date = end_date = today - timedelta(days=1)

    elif "today" in q:
        start_date = end_date = today

    elif "last week" in q:
        start_date = today - timedelta(days=today.weekday() + 7)
        end_date = start_date + timedelta(days=6)

    elif "this week" in q or "week" in q:
        start_date = today - timedelta(days=today.weekday())
        end_date = today

    elif "last month" in q:
        first_this_month = today.replace(day=1)
        end_date = first_this_month - timedelta(days=1)
        start_date = end_date.replace(day=1)

    elif "this month" in q or "month" in q:
        start_date = today.replace(day=1)
        end_date = today

    elif "this year" in q or "year" in q:
        start_date = today.replace(month=1, day=1)
        end_date = today

    # Recognize an explicitly stated YYYY-MM-DD date.
    if start_date is None:
        match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", q)
        if match:
            try:
                start_date = end_date = date.fromisoformat(match.group(1))
            except ValueError:
                pass

    # Match categories already stored in the database.
    category = None
    for existing_category in sorted(
        available_categories,
        key=len,
        reverse=True,
    ):
        if existing_category.lower() in q:
            category = existing_category
            break

    return {
        "transaction_type": transaction_type,
        "start_date": start_date,
        "end_date": end_date,
        "category": category,
    }


def answer_ledger_question(question):
    """Calculate the answer from saved database records."""
    if not question or not question.strip():
        return "Please enter a question about your saved transactions."

    records = get_all_expenses()

    if not records:
        return (
            "Your ledger is empty. Save a transaction before asking "
            "a question."
        )

    df = pd.DataFrame(records)

    if "amount" not in df.columns or "expense_date" not in df.columns:
        raise ValueError(
            "The ledger must contain amount and expense_date columns."
        )

    if "transaction_type" not in df.columns:
        df["transaction_type"] = "expense"
    if "currency" not in df.columns:
        df["currency"] = "INR"
    if "category" not in df.columns:
        df["category"] = "Uncategorized"

    df["transaction_type"] = (
        df["transaction_type"]
        .fillna("expense")
        .astype(str)
        .str.lower()
    )

    df["currency"] = (
        df["currency"].fillna("INR").astype(str).str.upper()
    )

    df["_amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["_date"] = pd.to_datetime(
        df["expense_date"], errors="coerce"
    ).dt.date

    categories = {
        str(category).strip()
        for category in df["category"].dropna().tolist()
        if str(category).strip()
    }

    filters = parse_ledger_question(question, categories)

    if filters["transaction_type"] != "all":
        df = df[
            df["transaction_type"] == filters["transaction_type"]
        ]

    if filters["category"]:
        df = df[
            df["category"].astype(str).str.lower()
            == filters["category"].lower()
        ]

    if filters["start_date"]:
        df = df[
            df["_date"].notna()
            & (df["_date"] >= filters["start_date"])
        ]

    if filters["end_date"]:
        df = df[
            df["_date"].notna()
            & (df["_date"] <= filters["end_date"])
        ]

    if df.empty:
        return "No matching transactions were found for that question."

    df = df[df["_amount"].notna()]

    if df.empty:
        return "No valid transaction amounts were found."

    period = ""

    if filters["start_date"] and filters["end_date"]:
        if filters["start_date"] == filters["end_date"]:
            period = f" on {filters['start_date']}"
        else:
            period = (
                f" from {filters['start_date']} "
                f"to {filters['end_date']}"
            )
    elif filters["start_date"]:
        period = f" since {filters['start_date']}"

    category_text = (
        f" for category {filters['category']}"
        if filters["category"]
        else ""
    )

    if filters["transaction_type"] == "income":
        label = "Income"
    elif filters["transaction_type"] == "expense":
        label = "Expenses"
    else:
        label = "Transaction totals"

    totals = (
        df.groupby("currency")["_amount"]
        .sum()
        .sort_index()
    )

    formatted_totals = ", ".join(
        f"{currency} {amount:,.2f}"
        for currency, amount in totals.items()
    )

    answer = (
        f"{label}{category_text}{period}: {formatted_totals}. "
        f"Based on {len(df)} matching transaction(s)."
    )

    # Include a net balance only when the question asks for it.
    if any(term in question.lower() for term in ("balance", "net")):
        all_records = pd.DataFrame(records)

        if "transaction_type" not in all_records.columns:
            all_records["transaction_type"] = "expense"
        if "currency" not in all_records.columns:
            all_records["currency"] = "INR"

        all_records["transaction_type"] = (
            all_records["transaction_type"]
            .fillna("expense")
            .astype(str)
            .str.lower()
        )
        all_records["currency"] = (
            all_records["currency"]
            .fillna("INR")
            .astype(str)
            .str.upper()
        )
        all_records["_amount"] = pd.to_numeric(
            all_records["amount"], errors="coerce"
        ).fillna(0)

        if filters["start_date"] and "expense_date" in all_records.columns:
            all_records["_date"] = pd.to_datetime(
                all_records["expense_date"], errors="coerce"
            ).dt.date

            all_records = all_records[
                all_records["_date"].notna()
                & (all_records["_date"] >= filters["start_date"])
            ]

        if filters["end_date"] and "_date" in all_records.columns:
            all_records = all_records[
                all_records["_date"].notna()
                & (all_records["_date"] <= filters["end_date"])
            ]

        balances = []

        for currency, group in all_records.groupby("currency"):
            income = group.loc[
                group["transaction_type"] == "income", "_amount"
            ].sum()

            expenses = group.loc[
                group["transaction_type"] == "expense", "_amount"
            ].sum()

            balances.append(
                f"{currency} {income - expenses:,.2f}"
            )

        if balances:
            answer += " Net balance by currency: " + ", ".join(balances) + "."

    return answer


# --------------------------------------------------
# Initialize
# --------------------------------------------------

st.title("🎙️ Voice Expense Logger")

st.write(
    "Record income and expenses by voice, review extracted transactions, "
    "listen to a spoken summary, and save confirmed records."
)

try:
    validate_config()
    initialize_database()
except Exception as error:
    logger.exception("Application initialization failed")
    st.error(f"Application initialization failed: {error}")
    st.stop()


# --------------------------------------------------
# 1. Upload audio and transcribe
# --------------------------------------------------

st.header("1. Upload audio")

audio_file = st.file_uploader(
    "Choose an audio file",
    type=["wav", "mp3", "mpeg", "m4a", "webm"],
)

language_options = get_runtime_languages()

language = st.selectbox(
    "Audio language",
    options=list(language_options.keys()),
    format_func=lambda value: language_options[value],
)

if st.button("🎧 Transcribe Audio", disabled=audio_file is None):
    temporary_audio_path = None

    try:
        with st.spinner("Transcribing audio..."):
            suffix = Path(audio_file.name).suffix or ".wav"

            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix,
            ) as temporary_file:
                temporary_file.write(audio_file.getvalue())
                temporary_audio_path = temporary_file.name

            try:
               
                stt_prompt = (
                    "This audio contains Indian business transactions and may be spoken "
                    "in Telugu, Hindi, or English. Recognize the spoken language accurately. "
                    "For Telugu speech, preserve the words in Telugu script (తెలుగు); "
                    "do not transliterate Telugu speech into Devanagari or Hindi. "
                    "For Hindi speech, use Devanagari script. For English speech, use "
                    "English spelling. Preserve the original spoken words without translating "
                    "or paraphrasing them. Pay close attention to amounts in rupees (INR), "
                    "vendor names, dates, and payment methods such as cash, UPI, debit card, "
                    "credit card, and bank transfer. Do not guess words that are unclear."
                    )

                client = AudiClabsClient()

                transcript = client.transcribe_audio(
                    audio_path=temporary_audio_path,
                    language=None if language == "auto" else language,
                    prompt=stt_prompt
                )
                st.write("DEBUG — Raw transcription:", repr(transcript))


            finally:
                if temporary_audio_path:
                    Path(temporary_audio_path).unlink(missing_ok=True)

        transcript = transcript.strip()

        if not transcript:
            st.warning("No transcription text was returned.")
        else:
            reset_confirmation()
            st.session_state["transcription_widget"] = transcript
            st.session_state["original_transcription"] = transcript
            st.session_state["extracted_expenses"] = []
            st.session_state["available_tts_voices"] = {}
            st.session_state["readback_text"] = ""

            st.success("Transcription completed.")

    except AudiClabsAPIError as error:
        logger.exception("AudiClabs transcription failed")
        st.error(f"Transcription failed: {error}")

    except Exception as error:
        logger.exception("Unexpected transcription error")
        st.error(f"Could not transcribe audio: {error}")


# --------------------------------------------------
# 2. Review transcription and extract transactions
# --------------------------------------------------

st.header("2. Review the transcription")

edited_transcription = st.text_area(
    "Correct speech-recognition mistakes before extraction",
    key="transcription_widget",
    height=130,
    placeholder="Your recognized speech will appear here...",
)

if st.button(
    "✨ Extract Transactions",
    disabled=not edited_transcription.strip(),
):
    try:
        with st.spinner("Extracting transactions with Gemini..."):
            result = extract_expenses(edited_transcription.strip())

            extracted = [
                normalize_transaction(item)
                for item in result.expenses
            ]

            reset_confirmation()
            st.session_state["extracted_expenses"] = extracted
            st.session_state["original_transcription"] = (
                edited_transcription.strip()
            )
            st.session_state["available_tts_voices"] = {}
            st.session_state["readback_text"] = ""

        if extracted:
            st.success(
                f"Extracted {len(extracted)} transaction(s). "
                "Review every field below."
            )
        else:
            st.warning("No transactions were found in the transcription.")

    except Exception as error:
        logger.exception("Transaction extraction failed")
        st.error(f"Could not extract transactions: {error}")


# --------------------------------------------------
# 3. Edit, read back, confirm, and save
# --------------------------------------------------

st.header("3. Review, confirm, and save")

transactions = st.session_state["extracted_expenses"]

if transactions:
    st.subheader("Extracted transaction data")
    st.json(transactions, expanded=True)

    transaction_df = pd.DataFrame(transactions)

    expected_columns = [
        "transaction_type",
        "amount",
        "currency",
        "party",
        "category",
        "expense_date",
        "payment_method",
        "notes",
    ]

    for column in expected_columns:
        if column not in transaction_df.columns:
            transaction_df[column] = None

    transaction_df = transaction_df[expected_columns]

    edited_df = st.data_editor(
        transaction_df,
        key=f"transaction_editor_{st.session_state['editor_version']}",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "transaction_type": st.column_config.SelectboxColumn(
                "Type",
                options=["income", "expense"],
                required=True,
            ),
            "amount": st.column_config.NumberColumn(
                "Amount",
                min_value=0.01,
                format="%.2f",
                required=True,
            ),
            "currency": st.column_config.TextColumn(
                "Currency",
                required=True,
            ),
            "party": st.column_config.TextColumn("Party / Business"),
            "category": st.column_config.TextColumn(
                "Category",
                required=True,
            ),
            "expense_date": st.column_config.TextColumn(
                "Date (YYYY-MM-DD)",
                required=True,
            ),
            "payment_method": st.column_config.TextColumn("Payment method"),
            "notes": st.column_config.TextColumn("Notes"),
        },
    )

    current_rows = edited_df.to_dict(orient="records")
    current_snapshot = snapshot_rows(current_rows)

    st.subheader("🔊 Spoken read-back")

    readback_languages = {
        "English": "en",
        "Hindi (हिन्दी)": "hi",
        "Telugu (తెలుగు)": "te",
    }

    selected_language_label = st.selectbox(
        "Read-back language",
        options=list(readback_languages.keys()),
        key="readback_language_selector",
    )

    readback_language_code = readback_languages[selected_language_label]
    st.session_state["readback_language"] = readback_language_code

    st.caption(
        "Hindi and Telugu confirmation text is translated before TTS. "
        "Review the text and audio before confirming."
    )

    if st.button("Generate spoken confirmation"):
        try:
            with st.spinner(
                "Preparing the confirmation and generating audio..."
            ):
                readback_text = build_readback(
                    current_rows,
                    readback_language_code,
                )

                voice_items = get_runtime_tts_voices()

                if not voice_items:
                    raise ValueError(
                        "AudiClabs did not return any selectable voices."
                    )

                voice_options = {
                    item["voice_id"]: (
                        f"{item.get('name', item['voice_id'])} "
                        f"({item.get('language') or 'language unspecified'})"
                    )
                    for item in voice_items
                }

                preferred_voice = next(
                    (
                        item["voice_id"]
                        for item in voice_items
                        if str(item.get("language", "")).lower() == "en"
                    ),
                    voice_items[0]["voice_id"],
                )

                tts_client = AudiClabsTTSClient()

                audio_bytes = tts_client.synthesize_speech(
                    text=readback_text,
                    voice_id=preferred_voice,
                    language=readback_language_code,
                )

                if not audio_bytes:
                    raise ValueError("AudiClabs returned empty audio.")

                reset_confirmation()

                st.session_state["available_tts_voices"] = voice_options
                st.session_state["preferred_tts_voice"] = preferred_voice
                st.session_state["readback_text"] = readback_text
                st.session_state["tts_audio"] = audio_bytes
                st.session_state["tts_snapshot"] = current_snapshot

                st.success("Spoken confirmation generated.")

        except Exception as error:
            logger.exception("Read-back generation failed")
            st.error(f"Could not generate confirmation audio: {error}")

    if st.session_state["readback_text"]:
        st.markdown("**Text sent to the speech service:**")
        st.write(st.session_state["readback_text"])

    voice_options = st.session_state["available_tts_voices"]

    if voice_options:
        voice_ids = list(voice_options.keys())
        preferred_voice = st.session_state["preferred_tts_voice"]

        selected_index = (
            voice_ids.index(preferred_voice)
            if preferred_voice in voice_ids
            else 0
        )

        selected_voice = st.selectbox(
            "Read-back voice",
            options=voice_ids,
            format_func=lambda value: voice_options[value],
            index=selected_index,
            key="selected_tts_voice",
        )

        if st.button("Regenerate audio with selected voice"):
            try:
                with st.spinner("Generating audio with selected voice..."):
                    readback_text = build_readback(
                        current_rows,
                        readback_language_code,
                    )

                    tts_client = AudiClabsTTSClient()

                    audio_bytes = tts_client.synthesize_speech(
                        text=readback_text,
                        voice_id=selected_voice,
                        language=readback_language_code,
                    )

                    if not audio_bytes:
                        raise ValueError("AudiClabs returned empty audio.")

                    reset_confirmation()

                    st.session_state["tts_audio"] = audio_bytes
                    st.session_state["tts_snapshot"] = current_snapshot
                    st.session_state["readback_text"] = readback_text
                    st.session_state["preferred_tts_voice"] = selected_voice

                    st.success("Audio regenerated with selected voice.")

            except Exception as error:
                logger.exception("Voice regeneration failed")
                st.error(f"Could not regenerate audio: {error}")

    if st.session_state["tts_audio"]:
        if st.session_state["tts_snapshot"] != current_snapshot:
            st.warning(
                "The table changed since the audio was generated. "
                "Generate the spoken confirmation again before saving."
            )
            reset_confirmation()

        else:
            st.audio(
                st.session_state["tts_audio"],
                format="audio/mp3",
            )

            st.caption(
                "Listen to the spoken summary and verify every field "
                "in the editable table."
            )

            apply_pending_confirmation_reset()

            st.checkbox(
                "I have reviewed the table and confirm these "
                "transactions are correct.",
                key="confirmation_checked",
            )

            if st.button("💾 Confirm and save transactions"):
                if not st.session_state["confirmation_checked"]:
                    st.error(
                        "Please check the confirmation box before saving."
                    )

                elif st.session_state["tts_snapshot"] != snapshot_rows(
                    edited_df.to_dict(orient="records")
                ):
                    st.error(
                        "The table changed after the read-back. "
                        "Generate the confirmation audio again."
                    )
                    reset_confirmation()

                else:
                    valid_rows, errors = validate_rows(current_rows)

                    if errors:
                        st.error("Please fix these errors. Nothing was saved.")
                        for message in errors:
                            st.write(f"- {message}")

                    elif not valid_rows:
                        st.warning("There are no transactions to save.")

                    else:
                        success, error_message = save_transactions(valid_rows)

                        if success:
                            st.success(
                                f"Saved {len(valid_rows)} confirmed "
                                "transaction(s)."
                            )

                            reset_confirmation()
                            st.session_state["extracted_expenses"] = []
                            st.session_state["original_transcription"] = ""
                            st.session_state["available_tts_voices"] = {}
                            st.session_state["readback_text"] = ""
                            st.session_state["clear_transcription_on_next_run"] = True
                            st.session_state["editor_version"] += 1

                            st.rerun()

                        else:
                            st.error(
                                f"Could not save transactions: {error_message}"
                            )

else:
    st.info("Extract transactions from your transcription to review them.")


# --------------------------------------------------
# 4. Ledger, filters, totals, and CSV export
# --------------------------------------------------

st.divider()
st.header("4. Transaction ledger")

try:
    records = get_all_expenses()

    if records:
        ledger_df = pd.DataFrame(records)

        if "transaction_type" not in ledger_df.columns:
            ledger_df["transaction_type"] = "expense"

        if "currency" not in ledger_df.columns:
            ledger_df["currency"] = "INR"

        if "party" not in ledger_df.columns:
            ledger_df["party"] = (
                ledger_df["merchant"]
                if "merchant" in ledger_df.columns
                else None
            )

        if "notes" not in ledger_df.columns:
            ledger_df["notes"] = (
                ledger_df["description"]
                if "description" in ledger_df.columns
                else ""
            )

        ledger_df["transaction_type"] = (
            ledger_df["transaction_type"]
            .fillna("expense")
            .astype(str)
            .str.lower()
        )

        ledger_df["currency"] = (
            ledger_df["currency"]
            .fillna("INR")
            .astype(str)
            .str.upper()
        )

        col1, col2, col3 = st.columns(3)

        with col1:
            type_filter = st.selectbox(
                "Transaction type",
                ["All", "income", "expense"],
            )

        with col2:
            categories = sorted(
                ledger_df["category"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )

            category_filter = st.selectbox(
                "Category",
                ["All"] + categories,
            )

        with col3:
            dates = pd.to_datetime(
                ledger_df["expense_date"],
                errors="coerce",
            )

            min_date = dates.min().date() if dates.notna().any() else None
            max_date = dates.max().date() if dates.notna().any() else None

            if min_date and max_date:
                date_range = st.date_input(
                    "Date range",
                    value=(min_date, max_date),
                )
            else:
                date_range = ()

        filtered_df = ledger_df.copy()

        if type_filter != "All":
            filtered_df = filtered_df[
                filtered_df["transaction_type"] == type_filter
            ]

        if category_filter != "All":
            filtered_df = filtered_df[
                filtered_df["category"].astype(str) == category_filter
            ]

        if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
            start_date, end_date = date_range

            record_dates = pd.to_datetime(
                filtered_df["expense_date"],
                errors="coerce",
            ).dt.date

            filtered_df = filtered_df[
                record_dates.notna()
                & (record_dates >= start_date)
                & (record_dates <= end_date)
            ]

        st.dataframe(
            filtered_df,
            use_container_width=True,
            hide_index=True,
        )

        if not filtered_df.empty:
            st.subheader("Income, expenses, and balance by currency")

            summary_df = filtered_df.copy()

            summary_df["_amount"] = pd.to_numeric(
                summary_df["amount"],
                errors="coerce",
            ).fillna(0)

            currency_summary = (
                summary_df.groupby(
                    ["currency", "transaction_type"],
                    dropna=False,
                )["_amount"]
                .sum()
                .unstack(fill_value=0)
            )

            for kind in ("income", "expense"):
                if kind not in currency_summary.columns:
                    currency_summary[kind] = 0.0

            currency_summary["net_balance"] = (
                currency_summary["income"] - currency_summary["expense"]
            )

            st.dataframe(
                currency_summary.reset_index(),
                use_container_width=True,
                hide_index=True,
            )

            st.subheader("Totals by category")

            category_totals = (
                summary_df.groupby(
                    ["currency", "transaction_type", "category"],
                    as_index=False,
                    dropna=False,
                )["_amount"]
                .sum()
                .rename(columns={"_amount": "total_amount"})
            )

            st.dataframe(
                category_totals,
                use_container_width=True,
                hide_index=True,
            )

        st.download_button(
            "⬇️ Download filtered ledger as CSV",
            data=filtered_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="transaction_ledger.csv",
            mime="text/csv",
        )

    else:
        st.info("No transactions have been saved yet.")

except Exception as error:
    logger.exception("Could not load transaction ledger")
    st.error(f"Could not load the transaction ledger: {error}")


# --------------------------------------------------
# 5. Ask questions about the saved ledger
# --------------------------------------------------

st.divider()
st.header("5. Ask your ledger")

st.write(
    "Ask about saved income and expenses. The totals are calculated "
    "from your database and the answer can be spoken aloud."
)

st.caption(
    "Examples: How much did I spend this week? "
    "What was my income this month? "
    "How much did I spend on transport yesterday?"
)

ledger_question = st.text_input(
    "Type your question",
    placeholder="How much did I spend on transport this week?",
    key="ledger_question_input",
)

if st.button("🔎 Get ledger answer"):
    try:
        with st.spinner("Checking your saved transactions..."):
            answer = answer_ledger_question(ledger_question)

        st.session_state["ledger_answer"] = answer
        st.session_state["ledger_answer_question"] = ledger_question
        st.session_state["ledger_answer_audio"] = None

    except Exception as error:
        logger.exception("Ledger question failed")
        st.error(f"Could not answer the ledger question: {error}")

if st.session_state["ledger_answer"]:
    st.markdown("**Answer**")
    st.write(st.session_state["ledger_answer"])

    if st.button("🔊 Speak the answer"):
        try:
            with st.spinner("Generating spoken answer..."):
                voice_id = get_english_voice()
                tts_client = AudiClabsTTSClient()

                audio_bytes = tts_client.synthesize_speech(
                    text=st.session_state["ledger_answer"],
                    voice_id=voice_id,
                    language="en",
                )

                if not audio_bytes:
                    raise ValueError("AudiClabs returned empty audio.")

                st.session_state["ledger_answer_audio"] = audio_bytes

        except Exception as error:
            logger.exception("Ledger answer TTS failed")
            st.error(f"Could not speak the answer: {error}")

    if st.session_state["ledger_answer_audio"]:
        st.audio(
            st.session_state["ledger_answer_audio"],
            format="audio/mp3",
        )
