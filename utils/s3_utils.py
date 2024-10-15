import os
import uuid
import boto3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize S3 client
s3 = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
)

bucket_name = os.getenv('AWS_S3_BUCKET_NAME')

def upload_to_s3(s3_client, file_path, s3_object_key, bucket_name):
    """Uploads a file to the S3 bucket and returns the file URL."""
    try:
        s3_client.upload_file(file_path, bucket_name, s3_object_key)
        return f"https://{bucket_name}.s3.amazonaws.com/{s3_object_key}"
    except Exception as e:
        raise Exception(f"Failed to upload to S3: {e}")


def generate_presigned_url(s3_object_key, expiration=7200):
    """Generates a presigned URL for accessing the uploaded S3 object."""
    try:
        response = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': s3_object_key},
            ExpiresIn=expiration
        )
        return response
    except Exception as e:
        raise Exception(f"Failed to generate presigned URL: {e}")
