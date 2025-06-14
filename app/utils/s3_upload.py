import boto3
import os

def upload_file_to_s3(file, key, content_type='image/jpeg'):
    s3 = boto3.client(
        's3',
        region_name=os.getenv('S3_REGION', 'us-east-1')
    )
    
    s3.upload_fileobj(
        file,
        os.getenv('S3_BUCKET_NAME'),
        key,
        ExtraArgs={'ACL': 'public-read', 'ContentType': content_type}
    )
