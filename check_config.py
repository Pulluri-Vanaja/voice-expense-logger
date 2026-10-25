from dotenv import load_dotenv
import os

load_dotenv()

audiclabs_key = os.getenv("AUDICLABS_API_KEY")

if audiclabs_key:
    print("AudiClabs API key loaded successfully.")
else:
    print("API key not found. Check your .env file.")