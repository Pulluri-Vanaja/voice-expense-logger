
from audiclabs_client import AudiClabsClient


def main():
    client = AudiClabsClient()
    print("AudiClabs client initialized successfully!")

    try:
        client.transcribe_audio("audio_file_that_does_not_exist.wav")
    except FileNotFoundError:
        print("Missing audio file handled correctly.")


if __name__ == "__main__":
    main()
