from minio import Minio
import os
from dotenv import load_dotenv


# Carrega o ficheiro .env
load_dotenv()

# Configurações (Viriam Idealmente de variáveis de ambiente, mas para já hardcode para testar)
minio_client = Minio(
    "localhost:9000",
    access_key=os.getenv("MINIO_USER"),
    secret_key=os.getenv("MINIO_PASSWORD"),
    secure=False
)

buckets = ["raw-data", "processed-data"]


def setup_buckets():
    for bucket in buckets:
        if not minio_client.bucket_exists(bucket):
            minio_client.make_bucket(bucket)
            print(f"Bucket '{bucket}' criado com sucesso.")
        else:
            print(f"Bucket '{bucket}' já existe.")


if __name__ == "__main__":
    setup_buckets()
