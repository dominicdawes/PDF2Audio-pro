import os
import uuid
import boto3
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase: Client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))


def insert_supabase_record(supabase_client, podcast_name, s3_object_key, cdn_url, content_tags):
    """Inserts a record into the Supabase Library table."""
    try:
        data = {
            "podcast_name": podcast_name,
            "s3_object_key": s3_object_key,
            "cdn_url": cdn_url,
            "content_tags": content_tags
        }
        response = supabase_client.table("Library").insert(data).execute()
        if response.status_code != 200:
            raise Exception(f"Supabase error: {response.json()}")
    except Exception as e:
        raise Exception(f"Failed to insert into Supabase: {e}")
