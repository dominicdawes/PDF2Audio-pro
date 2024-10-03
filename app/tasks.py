# This file runs Celery tasks, place any logic that needs to run async
# like api calls and calls to other services. 

from celery import Celery
from utils.audio_utils import generate_audio
import os

# Initialize Celery
celery_app = Celery('tasks', broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'))

@celery_app.task(bind=True)
def validate_and_generate_audio_task(self, files, *args):
    """
    Celery task to validate and generate audio for a list of PDF files.
    """
    if not files:
        return {"error": "Please upload at least one PDF file before generating audio."}

    try:
        # Call the generate_audio function from audio_utils
        audio_file, transcript, original_text = generate_audio(files, *args)
        return {
            "audio_file": audio_file,
            "transcript": transcript,
            "original_text": original_text,
            "error": None
        }
    except Exception as e:
        return {
            "audio_file": None,
            "transcript": None,
            "original_text": None,
            "error": str(e)
        }
