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
    # Diretório deste ficheiro (src/ingestion)
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

    # Project root: sobe dois níveis (src/ingestion -> src -> root)
    PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))

    # Caminho correto para data/raw
    base_path = os.path.join(PROJECT_ROOT, "data", "raw")

    print("Base path usado:", base_path)
    print("global_temp existe?", os.path.exists(os.path.join(base_path, "global_temp.csv")))
    print("co2_emissions existe?", os.path.exists(os.path.join(base_path, "co2_emissions.csv")))

    # Upload NASA Data
    upload_file("raw-data", os.path.join(base_path, "global_temp.csv"), "nasa/temperature.csv")

    # Upload Carbon Data
    upload_file("raw-data", os.path.join(base_path, "co2_emissions.csv"), "carbon/co2.csv")