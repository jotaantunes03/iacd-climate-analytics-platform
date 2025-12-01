from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv
import os

# Carrega o ficheiro .env
load_dotenv()

# Configuração do Cliente
client = Minio(
    "localhost:9000",
    access_key=os.getenv("MINIO_USER"),
    secret_key=os.getenv("MINIO_PASSWORD"),
    secure=False
)


def upload_file(bucket_name, file_path, object_name):
    """Faz upload de um ficheiro local para o MinIO"""
    try:
        client.fput_object(
            bucket_name, object_name, file_path,
        )
        print(f"'{object_name}' enviado com sucesso para o bucket '{bucket_name}'.")
    except S3Error as err:
        print(f"Erro no upload: {err}")


if __name__ == "__main__":
    # Caminhos para os teus ficheiros locais
    base_path = "../../data/raw"

    # Upload NASA Data
    upload_file("raw-data", f"{base_path}/global_temp.csv", "nasa/temperature.csv")

    # Upload Carbon Data
    upload_file("raw-data", f"{base_path}/co2_emissions.csv", "carbon/co2.csv")
