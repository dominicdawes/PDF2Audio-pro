from celery import Celery, chain
import logging
import os
import json
import psutil
import requests
import tempfile
from tasks.celery_app import celery_app  # Import the Celery app instance (see celery_app.py for LocalHost config)
from utils.audio_utils import generate_audio, generate_only_dialogue_text
from utils.s3_utils import upload_to_s3, s3_client, s3_bucket_name
from utils.supabase_utils import insert_conversation_supabase_record, supabase_client
from utils.cloudfront_utils import get_cloudfront_url
from utils.instruction_templates import INSTRUCTION_TEMPLATES
from time import sleep
from datetime import datetime, timezone
import uuid

# langchain dependencies
from langchain.text_splitter import CharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def rag_chat_task(self, user_id, conversation_id, query, document_ids):
    """
    Celery task for handling RAG (Retrieval-Augmented Generation) chatbot logic.

    example json body from the front-end
    {
        "user_id": "user-32kfowdkbf0ouskhw9hs-sk",
        "conversation_id": "conv456",      // Or leave empty for a new conversation
        "query": "What were the results of the researchers' conclusion?",
        "document_ids": ["fjs78dkbf9fksfnuhis-89s", "789s-khw9hdfjksdjhk9sdh"]
    }
    """
    try:
        # Step 1: Vectorize the query
        embedding_model = OpenAIEmbeddings()
        query_embedding = embedding_model.embed_query(query)
        
        # Step 2: Fetch relevant document chunks
        relevant_chunks = fetch_relevant_chunks(query_embedding, document_ids)
        
        # Combine retrieved chunks into a single context for RAG
        context = " ".join([chunk["content"] for chunk in relevant_chunks])

        # Step 3: Generate the answer using RAG
        answer = generate_answer(query, context)

        # Step 4: Save query and response in message history
        save_conversation(conversation_id, user_id, query, answer)

        return {"answer": answer}
    except Exception as e:
        raise Exception(f"RAG Chat Task failed: {str(e)}")

def fetch_relevant_chunks(query_embedding, document_ids):
    response = supabase_client.rpc("match_document_chunks", {
        "query_embedding": query_embedding,
        "document_ids": document_ids
    }).execute()

    if response.error:
        raise Exception(f"Error fetching relevant chunks: {response.error}")

    return response.data

def generate_answer(query, context):
    llm = OpenAI(model_name="text-davinci-003")  # Replace with your LLM model
    prompt_template = PromptTemplate(
        input_variables=["context", "query"],
        template="Answer the question based on the context:\n\nContext:\n{context}\n\nQuestion:\n{query}\n\nAnswer:"
    )
    chain = LLMChain(llm=llm, prompt=prompt_template)
    answer = chain.run({"context": context, "query": query})
    return answer

def save_conversation(conversation_id, user_id, query, answer):
    messages = [
        {
            "conversation_id": conversation_id,
            "message_role": "user",
            "message_content": query,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "conversation_id": conversation_id,
            "message_role": "assistant",
            "message_content": answer,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    ]

    # Insert the document source record into Supabase
    res = insert_conversation_supabase_record(
        client=supabase_client,
        messaegs=messages,
    )

    response = supabase_client.table("message").insert(messages).execute()

    if response.error:
        raise Exception(f"Error saving messages: {response.error}")

## OLD CODE
@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def rag_query_task(self, files, metadata=None, instructions_key='podcast', *args):
    """
    Celery task to validate and generate audio podcast (.mp3) for a list of PDF files.
    
    Args:
        files (List): list of either urls or local paths (see audio_utils.py)
        metadata (Dict): additional metadata for processing {'uploaded_by':, length:, temperature:, model_choice:...}
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
    
        ## Add mp3 to data bucket and CDN
        # Generate unique object keyh for mp3 file
        s3_mp3_object_key = f"{uuid.uuid4()}.mp3"

        # Upload to AWS S3 Bucket
        upload_to_s3(
            s3_client, 
            audio_file, 
            s3_mp3_object_key
        )

        # Generate a CloudFront URL for the uploaded file
        cloudfront_podcast_url = get_cloudfront_url(s3_mp3_object_key)

        # Insert podcast into Supabase
        insert_mp3_supabase_record(
            client=supabase_client,
            table_name="media_uploads",
            podcast_title="My Podcast", 
            cdn_url=cloudfront_podcast_url,                                        
            transcript=transcript,
            content_tags=["Fitness", "Technology"],  # Pass content_tags as an array,
            uploaded_by=metadata['uploaded_by'],
            is_public=metadata['is_public'],
            is_playlist=False,
        )

        # === RENDER RESOURCE LOGGING === #
        mem_after = process.memory_info().rss
        logger.info(f"Finished {self.name}")
        logger.info(f"Memory usage after task: {mem_after / (1024 * 1024)} MB")

        return {
            "cdn_url": cloudfront_podcast_url,    
            "transcript": transcript,
            "original_text": original_text,
            "error": None
        }
    
    except Exception as e:
        logger.exception(f"Task {self.name} failed with exception: {e}")
        raise # ask gpt how to do this