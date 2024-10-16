import os
import uuid
import boto3
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_client: Client = create_client(
    os.getenv('SUPABASE_URL'), 
    os.getenv('SUPABASE_SERVICE_ROLE_KEY')  # Ensure this key is the service role
)


def insert_supabase_record(client, podcast_name, s3_object_key, cdn_url, content_tags):
    """Inserts a record into the Supabase Library table."""
    try:
        data = {
            "podcast_name": podcast_name,
            "s3_object_key": s3_object_key,
            "cdn_url": cdn_url,
            "content_tags": content_tags
        }
        # Execute the insert query
        response = client.table("library-test").insert(data).execute()
        
        # Check if the response contains data
        if response.data:
            # Successful insertion
            return response.data
        else:
            # If there's no data, check for errors
            raise Exception(f"Supabase error: {response.error}")
    except Exception as e:
        raise Exception(f"Failed to insert into Supabase: {e}")
