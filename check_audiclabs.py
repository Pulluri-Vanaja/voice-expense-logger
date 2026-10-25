import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("AUDICLABS_API_KEY")
BASE_URL = os.getenv(
    "AUDICLABS_BASE_URL",
    "https://api.audiclabs.com/v1"
)

if not API_KEY:
    print("API key not found in .env")
    raise SystemExit(1)

headers = {"Authorization": f"Bearer {API_KEY}"}

endpoints = [
    "stt/languages",
    "stt/models",
    "tts/languages",
    "tts/voices",
]

for endpoint in endpoints:
    print(f"\nChecking {endpoint}...")
    try:
        response = requests.get(
            f"{BASE_URL}/{endpoint}",
            headers=headers,
            timeout=20
        )
        print("HTTP status:", response.status_code)

        if response.ok:
            print("Lookup successful.")
        else:
            print("Access check failed. Response:", response.text[:300])

    except requests.RequestException as error:
        print("Connection error:", error)