import os
import uuid
import boto3
from botocore.exceptions import ClientError
from botocore.client import Config
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize S3 client
s3_client = boto3.client(
    's3',
    region_name='us-east-2',  # Specify your bucket's region
    config=Config(signature_version='s3v4'),                # S3 client to use Signature Version 4, you align with AWS's required authentication mechanism
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
)

# Declare S3 bucket name
s3_bucket_name = os.getenv('AWS_S3_BUCKET_NAME')

def upload_to_s3(client, file_path, s3_object_key, bucket_name=s3_bucket_name):
    """Uploads a file to the S3 bucket and returns the file URL."""
    try:
        client.upload_file(file_path, bucket_name, s3_object_key)
        return f"https://{bucket_name}.s3.amazonaws.com/{s3_object_key}"
    except Exception as e:
        raise Exception(f"Failed to upload to S3: {e}")


# def generate_presigned_url(client, s3_object_key, expiration=7200):
#     """Generates a presigned URL for accessing the uploaded S3 object."""
#     try:
#         response = client.generate_presigned_url(
#             'get_object',
#             Params={'Bucket': os.getenv('AWS_S3_BUCKET_NAME'), 'Key': s3_object_key},
#             ExpiresIn=expiration
#         )
#         return response
#     except Exception as e:
#         raise Exception(f"Failed to generate presigned URL: {e}")

def generate_presigned_url(client, bucket_name, object_key, expiration=7200):
    """
    Generate a presigned URL to share an S3 object

    :param client: Boto3 S3 client
    :param bucket_name: string
    :param object_key: string
    :param expiration: Time in seconds for the presigned URL to remain valid
    :return: Presigned URL as string. If error, returns None.
    """
    try:
        response = client.generate_presigned_url('get_object',
                                                    Params={'Bucket': bucket_name,
                                                            'Key': object_key},
                                                    ExpiresIn=expiration)
    except ClientError as e:
        print(f"Error generating presigned URL: {e}")
        return None

    # The response contains the presigned URL
    return response