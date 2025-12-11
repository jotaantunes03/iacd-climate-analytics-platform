"""
This script initializes the MinIO service by ensuring that the necessary buckets exist.

It connects to the MinIO server and iterates through a predefined list of
bucket names, creating each one if it does not already exist. This is intended
to be run as an initialization step to prepare the object storage for the
application.
"""

from minio import Minio
import os

# --- MinIO Configuration ---
# Since this script runs INSIDE the cluster (e.g., as an init container or a job),
# it uses the Kubernetes service name 'minio' to connect.
MINIO_ENDPOINT = "minio:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"

# List of buckets to be created in MinIO.
BUCKET_NAMES = ["raw-data", "processed-data"]

def initialize_minio_buckets():
    """
    Connects to MinIO and creates predefined buckets if they don't exist.

    This function establishes a connection to the MinIO server using the
    configured endpoint and credentials. It then checks for the existence of
    each bucket in the BUCKET_NAMES list and creates it if it's missing.
    """
    print(f"--> Connecting to MinIO at {MINIO_ENDPOINT}...")
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )

    for bucket_name in BUCKET_NAMES:
        try:
            if not client.bucket_exists(bucket_name):
                client.make_bucket(bucket_name)
                print(f"   [CREATED] Bucket '{bucket_name}'")
            else:
                print(f"   [OK] Bucket '{bucket_name}' already exists")
        except Exception as e:
            print(f"   [ERROR] While creating bucket {bucket_name}: {e}")

if __name__ == "__main__":
    initialize_minio_buckets()