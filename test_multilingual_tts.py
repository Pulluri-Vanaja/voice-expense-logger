
from pathlib import Path

from audiclabs_tts import AudiClabsTTSClient

client = AudiClabsTTSClient()
output_dir = Path("multilingual_tts_tests")
output_dir.mkdir(exist_ok=True)

tests = [
    (
        "english",
        "en",
        "Hello! Your expense of 250 rupees has been recorded.",
    ),
    (
        "hindi",
        "hi",
        "आपका 250 रुपये का खर्च दर्ज कर लिया गया है।",
    ),
    (
        "telugu",
        "te",
        "మీ 250 రూపాయల ఖర్చు నమోదు చేయబడింది.",
    ),
]

# This voice is known to exist in your AudiClabs response.
voice_id = "voice_priya_en_in"

for name, language, text in tests:
    print(f"\nTesting {name} (language={language})...")

    try:
        audio_bytes = client.synthesize_speech(
            text=text,
            voice_id=voice_id,
            language=language,
            speed=1.0,
        )

        output_path = output_dir / f"{name}.mp3"
        output_path.write_bytes(audio_bytes)

        print(f"SUCCESS: Saved {output_path}")
        print(f"Audio size: {len(audio_bytes):,} bytes")

    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
