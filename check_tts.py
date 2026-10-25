
from audiclabs_tts import AudiClabsTTSClient

client = AudiClabsTTSClient()

try:
    text = (
        "Please confirm this transaction. "
        "You paid 2500 rupees to Ravi Traders "
        "for cement by cash."
    )

    audio_bytes = client.synthesize_speech(
        text=text,
        voice_id="voice_bilal_en",
        language="en",
    )

    with open("tts_test.mp3", "wb") as audio_file:
        audio_file.write(audio_bytes)

    print("Speech generated successfully!")
    print("Saved audio to tts_test.mp3")
    print("Audio size:", len(audio_bytes), "bytes")

except Exception as error:
    print("TTS test failed:", error)
