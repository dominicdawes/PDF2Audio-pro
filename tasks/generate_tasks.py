# This file runs Celery tasks, place any logic that needs to run async
# like api calls and calls to other services. 

from celery import Celery
from tasks.celery_app import celery_app  # Import the Celery app instance (see celery_app.py for LocalHost config)
from utils.audio_utils import generate_audio, generate_only_dialogue_text
from utils.instruction_templates import INSTRUCTION_TEMPLATES
from time import sleep
from datetime import datetime
import boto


# Simple sanity check tasks for Celery functionality

@celery_app.task(bind=True)
def addition_task(self, x, y):
    """
    Celery task to validate if celery and redis (message broker) are working.
    """
    sleep(8)
    return x + y

@celery_app.task
def reverse(text):
    sleep(18)        # simulates a long api call
    return text[::-1]

@celery_app.task
def concat_task(x, y):
    sleep(9)
    return x + y

# === PRODUCTION CELERY TASKS === #

@celery_app.task(bind=True)
def validate_and_generate_audio_task(self, files, *args):
    """
    Celery task to validate and generate audio podcast (.mp3) for a list of PDF files.
    
    Args:
        files (List): list of either urls or local paths (see audio_utils.py) 
        *args: openai_api_key, text_model, audio_model, speaker_1_voice...
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

@celery_app.task(bind=True, name='tasks.generate_tasks.generate_dialogue_only_task')
def generate_dialogue_only_task(self, files, instructions_key='podcast', *args):
    """
    Celery task to validate and generate ONLY text dialogue for a list of PDF files.

    Args:
        files (List): list of either urls or local paths (see audio_utils.py) 
        *args: openai_api_key, text_model, audio_model, speaker_1_voice...
    """
    # Store the start time
    self.update_state(meta={'start_time': datetime.now(datetime.timezone.utc)})

    if not files:
        return {"error": "Please upload at least one PDF file before generating dialogue."}

    try:
        # Extract the instructions from INSTRUCTION_TEMPLATES using the given instructions_key
        llm_instructions = INSTRUCTION_TEMPLATES.get(instructions_key, {})
        intro_instructions = llm_instructions.get("intro", "")
        text_instructions = llm_instructions.get("text_instructions", "")
        scratch_pad_instructions = llm_instructions.get("scratch_pad", "")
        prelude_dialog = llm_instructions.get("prelude", "")
        podcast_dialog_instructions = llm_instructions.get("dialog", "")

        # Call the generate_only_dialogue function with the instructions as keyword arguments
        dialogue_text = generate_only_dialogue_text(
            files,
            intro_instructions=intro_instructions,
            text_instructions=text_instructions,
            scratch_pad_instructions=scratch_pad_instructions,
            prelude_dialog=prelude_dialog,
            podcast_dialog_instructions=podcast_dialog_instructions,
            *args
        )

        return {
            "dialogue_text": dialogue_text,
            "error": None
        }
    except Exception as e:
        return {
            "dialogue_text": None,
            "error": str(e)
        }
