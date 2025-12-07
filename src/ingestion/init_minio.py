from minio import Minio
import os

# Configurações
# Como este script corre DENTRO do cluster (no pod do producer), usamos o nome do serviço 'minio'
MINIO_ENDPOINT = "minio:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"

buckets = ["raw-data", "processed-data"]

def setup_buckets():
    print(f"--> A conectar ao MinIO em {MINIO_ENDPOINT}...")
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )

    for bucket in buckets:
        try:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
                print(f"   [CRIADO] Bucket '{bucket}'")
            else:
                print(f"   [OK] Bucket '{bucket}' já existe")
        except Exception as e:
            print(f"   [ERRO] Ao criar bucket {bucket}: {e}")

if __name__ == "__main__":
    setup_buckets()