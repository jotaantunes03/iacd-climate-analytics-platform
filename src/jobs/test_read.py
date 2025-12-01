from pyspark.sql import SparkSession
from dotenv import load_dotenv
import os


# Carrega o ficheiro .env
load_dotenv()

def test_spark_read():
    # Inicializa o Spark com os pacotes necessários para ler S3/MinIO
    # Nota: Estes packages "org.apache.hadoop..." são OBRIGATÓRIOS
    spark = SparkSession.builder \
        .appName("MinIOTest") \
        .config("spark.jars.packages", "org.apache.hadoop:hadoop-aws:3.3.4") \
        .config("spark.hadoop.fs.s3a.endpoint", "http://localhost:9000") \
        .config("spark.hadoop.fs.s3a.access.key", os.getenv("MINIO_USER")) \
        .config("spark.hadoop.fs.s3a.secret.key", os.getenv("MINIO_PASSWORD")) \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .getOrCreate()

    print("Spark Session criada! A tentar ler do MinIO...")

    try:
        # Tenta ler o CSV que acabaste de carregar
        df = spark.read.option("header", "true").csv("s3a://raw-data/nasa/temperature.csv")

        print("Sucesso! Schema do ficheiro:")
        df.printSchema()
        df.show(5)
    except Exception as e:
        print(f"Erro ao ler do MinIO: {e}")
    finally:
        spark.stop()


if __name__ == "__main__":
    test_spark_read()