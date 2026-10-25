
import logging
from pathlib import Path

import requests

from config import AUDICLABS_API_KEY, AUDICLABS_BASE_URL

logger = logging.getLogger(__name__)


class AudiClabsAPIError(Exception):
    """Raised when an AudiClabs API request fails."""


class AudiClabsClient:
    """Client for AudiClabs speech-to-text requests."""

    def __init__(self):
        if not AUDICLABS_API_KEY:
            raise RuntimeError(
                "AudiClabs API key is missing from .env"
            )

        self.base_url = AUDICLABS_BASE_URL.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {AUDICLABS_API_KEY}"
        }

    def transcribe_audio(
        self,
        audio_path,
        language=None,
        prompt=None
    ):
        """Convert an audio file into text."""

        audio_file = Path(audio_path)

        if not audio_file.is_file():
            raise FileNotFoundError(
                f"Audio file not found: {audio_file}"
            )

        url = f"{self.base_url}/stt/transcriptions"

        data = {"model": "audic-stt-1"}

        if language:
            data["language"] = language

        if prompt:
            data["prompt"] = prompt

        try:
            with audio_file.open("rb") as file:
                response = requests.post(
                    url,
                    headers=self.headers,
                    files={"file": (
                        audio_file.name,
                        file
                    )},
                    data=data,
                    timeout=(60, 180)
                )

            request_id = response.headers.get(
                "X-Request-Id", "not provided"
            )

            logger.info(
                "AudiClabs STT status=%s request_id=%s",
                response.status_code,
                request_id
            )

            if not response.ok:
                raise AudiClabsAPIError(
                    f"Transcription failed with HTTP "
                    f"{response.status_code}. "
                    f"Request ID: {request_id}. "
                    f"Details: {response.text[:300]}"
                )

            result = response.json()
            text = result.get("text", "").strip()

            if not text:
                raise AudiClabsAPIError(
                    "The API returned no transcription text."
                )

            return text

        except requests.RequestException as error:
            logger.exception("AudiClabs request failed")
            raise AudiClabsAPIError(
                f"AudiClabs request failed: {type(error).__name__}: {error}"
            ) from error
