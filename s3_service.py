import boto3
from dotenv import load_dotenv
import os
import uuid


load_dotenv()

BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")


class S3Service:
    def __init__(self):
        self.bucket_name = BUCKET_NAME
        self.s3_client : boto3.client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )

    def upload_file(self, file_obj, filename):
        unique_name = f"{uuid.uuid4()}_{filename}"

        self.s3_client.upload_fileobj(
            file_obj,              # ✅ actual file stream
            self.bucket_name,
            unique_name
        )

        return f"https://{self.bucket_name}.s3.amazonaws.com/{unique_name}"
        
    def download_file(self, object_name, file_path):
        try:
            self.s3_client.download_file(self.bucket_name, object_name, file_path)
            print(f"File {object_name} downloaded from {self.bucket_name} to {file_path}")
        except Exception as e:
            print(f"Error downloading file: {e}")