import sys
from pyspark.sql import SparkSession
from pyspark.sql.functions import col
from pyspark.sql.types import DoubleType, IntegerType


def write_to_postgres(df, epoch_id, table_name):
    # Esta função é chamada a cada micro-batch
    count = df.count()
    if count > 0:
        print(f"--> [Batch {epoch_id}] Gravando {count} registos na tabela '{table_name}'...")
        try:
            df.write \
                .format("jdbc") \
                .option("url", "jdbc:postgresql://postgres:5432/climate_analysis") \
                .option("dbtable", table_name) \
                .option("user", "admin") \
                .option("password", "climatechange") \
                .option("driver", "org.postgresql.Driver") \
                .mode("append") \
                .save()
            print("   [OK] Sucesso.")
        except Exception as e:
            print(f"   [ERRO] Falha ao gravar no Postgres: {e}")
    else:
        pass  # Batch vazio, ignorar


def main():
    spark = SparkSession.builder \
        .appName("ClimateContinuousProcessor") \
        .config("spark.executor.memory", "512m") \
        .config("spark.driver.memory", "512m") \
        .config("spark.cores.max", "1") \
        .config("spark.sql.shuffle.partitions", "2") \
        .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000") \
        .config("spark.hadoop.fs.s3a.access.key", "minioadmin") \
        .config("spark.hadoop.fs.s3a.secret.key", "minioadmin") \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false") \
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")
    print(">>> PROCESSADOR CONTÍNUO ATIVO (Vigiando MinIO -> Postgres)...")

    # ---------------------------------------------------------
    # Leitura CONTÍNUA (readStream) em vez de Batch (read)
    # ---------------------------------------------------------

    # 1. Stream de Temperatura
    df_temp_raw = spark.readStream \
        .format("csv") \
        .option("header", "false") \
        .schema("year INT, temp DOUBLE, country STRING, unit STRING, _c4 STRING, _c5 STRING, _c6 STRING") \
        .load("s3a://raw-data/temperature/")

    df_temp = df_temp_raw.select(
        col("year").alias("Year"),
        col("temp").alias("Temp_Change"),
        col("country").alias("Country")
    ).filter(col("Year").isNotNull())

    # 2. Stream de Emissões
    df_co2_raw = spark.readStream \
        .format("csv") \
        .option("header", "false") \
        .schema("year INT, emissions DOUBLE, country STRING, element STRING, unit STRING, item STRING, source STRING") \
        .load("s3a://raw-data/emissions/")

    df_co2 = df_co2_raw.select(
        col("year").alias("Year"),
        col("emissions").alias("Emissions"),
        col("country").alias("Country"),
        col("item").alias("Item")
    ).filter(col("Year").isNotNull())

    # ---------------------------------------------------------
    # Escrita (writeStream)
    # ---------------------------------------------------------

    # Processar Temperatura a cada 30 segundos
    query_temp = df_temp.writeStream \
        .foreachBatch(lambda df, id: write_to_postgres(df, id, "climate_analysis")) \
        .trigger(processingTime='30 seconds') \
        .start()

    # Processar CO2 a cada 30 segundos
    query_co2 = df_co2.writeStream \
        .foreachBatch(lambda df, id: write_to_postgres(df, id, "co2_emissions")) \
        .trigger(processingTime='30 seconds') \
        .start()

    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()