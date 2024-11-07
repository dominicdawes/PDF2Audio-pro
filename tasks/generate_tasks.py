# This file runs Celery tasks, place any logic that needs to run async
# like api calls and calls to other services. 

from celery import Celery
import logging
import os
import psutil
import requests
import tempfile
from tasks.celery_app import celery_app  # Import the Celery app instance (see celery_app.py for LocalHost config)
from utils.audio_utils import generate_audio, generate_only_dialogue_text
from utils.s3_utils import upload_to_s3, generate_presigned_url, s3_client, s3_bucket_name
from utils.supabase_utils import insert_document_supabase_record, insert_mp3_supabase_record, supabase_client
from utils.cloudfront_utils import get_cloudfront_url
from utils.instruction_templates import INSTRUCTION_TEMPLATES
from time import sleep
from datetime import datetime, timezone
import uuid

logger = logging.getLogger(__name__)

# === Simple sanity check tasks for Celery functionality === #

@celery_app.task(bind=True)
def addition_task(self, x, y):
    """
    Celery task to validate if celery and redis (message broker) are working.
    """
    print(f"DEBUG: Task received with x={x}, y={y}")
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

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def validate_and_generate_audio_task(self, files, metadata=None, instructions_key='podcast', *args):
    """
    Celery task to validate and generate audio podcast (.mp3) for a list of PDF files.
    
    Args:
        files (List): list of either urls or local paths (see audio_utils.py)
        metadata (Dict): additional metadata for processing
        *args: openai_api_key, text_model, audio_model, speaker_1_voice...
    """
    # === RENDER RESOURCE LOGGING === #
    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss
    logger.info(f"Starting {self.name} with args: {args}")
    logger.info(f"Memory usage before task: {mem_before / (1024 * 1024)} MB")

    # Store the start time
    self.update_state(meta={'start_time': datetime.now(timezone.utc).isoformat()})

    if not files:
        return {"error": "Please upload at least one PDF file before generating audio."}
    
    # Initialize presigned_url to avoid UnboundLocalError
    presigned_url = None

    try:
        # Extract the instructions from INSTRUCTION_TEMPLATES using the given instructions_key
        llm_instructions = INSTRUCTION_TEMPLATES.get(instructions_key, {})
        intro_instructions = llm_instructions.get("intro", "")
        text_instructions = llm_instructions.get("text_instructions", "")
        scratch_pad_instructions = llm_instructions.get("scratch_pad", "")
        prelude_dialog = llm_instructions.get("prelude", "")
        podcast_dialog_instructions = llm_instructions.get("dialog", "")

        # Call generate_audio with default or provided arguments
        audio_file, transcript, original_text = generate_audio(
            files,
            intro_instructions=intro_instructions,
            text_instructions=text_instructions,
            scratch_pad_instructions=scratch_pad_instructions,
            prelude_dialog=prelude_dialog,
            podcast_dialog_instructions=podcast_dialog_instructions,
            *args,  # Handle any positional arguments passed via the task
        )
    
        ## Add sources to data bucket and CDN
        for file in files:
            try:
                # Check if file is a URL and download it
                if file.startswith('http://') or file.startswith('https://'):
                    response = requests.get(file)
                    response.raise_for_status()  # Raise an error for bad responses
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                    temp_file.write(response.content)
                    temp_file.close()
                    file_path = temp_file.name
                    print('temp pdf file downloaded :)')
                else:
                    # Treat as a local file
                    file_path = file

                # Split the file name to get the extension
                ext_ending = os.path.splitext(file_path)[1]
                
                # Generate a unique object key for S3 using a UUID and the file extension
                s3_document_object_key = f"{uuid.uuid4()}{ext_ending}"
                
                # Upload file to S3
                upload_to_s3(
                    s3_client, 
                    file_path, 
                    s3_document_object_key
                )

                # Generate CloudFront URL
                cloudfront_document_url = get_cloudfront_url(s3_document_object_key)

                # Insert the document source record into Supabase
                insert_document_supabase_record(
                    client=supabase_client,
                    table_name="document_sources",  
                    cdn_url=cloudfront_document_url,                                         
                    content_tags="AI, Technology",
                    uploaded_by=metadata['uploaded_by'],
                )

            except Exception as e:
                # Log the error, including the file name, for debugging
                logger.error(f"Failed to process file {file}: {e}", exc_info=True)
            finally:
                # Clean up temporary file if it was downloaded
                if file.startswith('http://') or file.startswith('https://'):
                    os.unlink(file_path)

        ## Add mp3 to data bucket and CDN
        # Generate unique object keyh for mp3 file
        s3_mp3_object_key = f"{uuid.uuid4()}.mp3"

        # Upload to S3
        upload_to_s3(
            s3_client, 
            audio_file, 
            s3_mp3_object_key
        )

        # Generate a 2-hour presigned URL for the uploaded file
        # presigned_url = generate_presigned_url(s3_client, s3_bucket_name, s3_object_key)

        # Generate a CloudFront URL for the uploaded file
        cloudfront_podcast_url = get_cloudfront_url(s3_mp3_object_key)

        # Insert podcast into Supabase
        insert_mp3_supabase_record(
            client=supabase_client,
            table_name="media_uploads",
            podcast_title="My Podcast", 
            s3_object_key=s3_mp3_object_key, 
            cdn_url=cloudfront_podcast_url,                                         # pretty sure this s3_url will not work, but thats ok it needs to be an actual CDN link
            transcript=transcript,
            content_tags="AI, Technology",
            uploaded_by=metadata['uploaded_by'],
            is_public=metadata['is_public'],
            is_playlist=False,
        )

        # === RENDER RESOURCE LOGGING === #
        mem_after = process.memory_info().rss
        logger.info(f"Finished {self.name}")
        logger.info(f"Memory usage after task: {mem_after / (1024 * 1024)} MB")

        return {
            "cdn_url": cloudfront_podcast_url,                        # Changed (10/15) from audio_file --> audio-presign-url
            "transcript": transcript,
            "original_text": original_text,
            "error": None
        }
    
    except Exception as e:
        logger.exception(f"Task {self.name} failed with exception: {e}")
        raise
        # return {
        #     "cdn_url": cloudfront_url,
        #     "transcript": None,
        #     "original_text": None,
        #     "error": str(e)
        # }

@celery_app.task(bind=True, name='tasks.generate_tasks.generate_dialogue_only_task')
def generate_dialogue_only_task(self, files, instructions_key='podcast', *args):
    """
    Celery task to validate and generate ONLY text dialogue for a list of PDF files.

    Args:
        files (List): list of either urls or local paths (see audio_utils.py) 
        *args: openai_api_key, text_model, audio_model, speaker_1_voice...
    """
    # Store the start time
    self.update_state(meta={'start_time': datetime.now(timezone.utc).isoformat()})

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
