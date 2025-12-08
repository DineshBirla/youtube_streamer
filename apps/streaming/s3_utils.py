"""S3 utilities for YouTube Streamer"""
import boto3
import logging
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.files.storage import default_storage
from .s3_utils import download_s3_file  # Add this import

logger = logging.getLogger(__name__)

def get_s3_presigned_url(mediafile, expiry=3600):
    """Generate presigned URL for FFmpeg access (1 hour expiry)"""
    s3_client = boto3.client('s3')
    try:
        bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
        if not bucket_name:
            logger.error("AWS_STORAGE_BUCKET_NAME not configured")
            return None
            
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': mediafile.file.name
            },
            ExpiresIn=expiry
        )
        logger.info(f"Generated presigned URL for {mediafile.id} (expires in {expiry}s)")
        return url
    except ClientError as e:
        logger.error(f"S3 presign failed for {mediafile.id}: {e}")
        return None

def is_s3_storage():
    """Check if using S3 storage"""
    return 's3' in str(default_storage.__class__).lower()

def download_s3_file(mediafile, expiry=3600):
    """Download S3 file to temp local file for FFmpeg"""
    if is_s3_storage():
        url = get_s3_presigned_url(mediafile, expiry)
    else:
        url = mediafile.file.url
    
    if not url:
        return None
        
    import requests
    import tempfile
    
    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
    for chunk in resp.iter_content(chunk_size=1024*1024):
        tmp_file.write(chunk)
    tmp_file.close()
    return tmp_file.name
