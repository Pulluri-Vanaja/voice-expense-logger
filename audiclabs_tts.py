
import requests

from config import AUDICLABS_BASE_URL, AUDICLABS_API_KEY


class AudiClabsTTSClient:
    """Client for AudiClabs text-to-speech and runtime voice lookup."""

    def __init__(self):
        if not AUDICLABS_API_KEY:
            raise ValueError("AudiClabs API key is missing from .env")

        self.base_url = AUDICLABS_BASE_URL.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {AUDICLABS_API_KEY}"
        }
        self.timeout = (15, 120)

    def get_voices(self):
        """Fetch available voices from AudiClabs at runtime."""
        response = requests.get(
            f"{self.base_url}/tts/voices",
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()

        # Accommodate common API response structures.
        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            for key in ("voices", "data", "results"):
                if isinstance(data.get(key), list):
                    return data[key]

        raise ValueError(
            "Unexpected response format from AudiClabs voices API."
        )

    def synthesize_speech(
        self,
        text,
        voice_id,
        language=None,
        speed=1.0,
    ):
        """Generate speech and return the audio bytes."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Text to speak cannot be empty.")

        if not voice_id:
            raise ValueError("Please select an available voice.")

        payload = {
            "model": "audic-tts-1",
            "input": text.strip(),
            "voice": voice_id,
            "speed": speed,
            "stream": False,
        }

        if language:
            payload["language"] = language

        response = requests.post(
            f"{self.base_url}/tts/speech",
            headers=self.headers,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").lower()

        # The API may return audio directly or a JSON response.
        if "audio/" in content_type or "octet-stream" in content_type:
            return response.content

        if "application/json" in content_type:
            raise ValueError(
                "AudiClabs returned JSON instead of an audio file. "
                f"Response: {response.text[:500]}"
            )

        raise ValueError(
            "AudiClabs returned an unexpected audio response type: "
            f"{content_type or 'unknown'}"
        )
