"""
This module defines a Spark Streaming application to process climate data.

It reads temperature and CO2 emission data from a MinIO S3-compatible storage,
processes it in micro-batches, and writes the results to two separate
PostgreSQL tables.
"""

import sys
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col
from pyspark.sql.types import DoubleType, IntegerType

# Centralized JDBC settings for PostgreSQL connection
PG_CONFIG = {
    "url": "jdbc:postgresql://postgres:5432/climate_analysis",
    "user": "admin",
    "password": "climatechange",
    "driver": "org.postgresql.Driver"
}

def write_to_postgres(df: DataFrame, epoch_id: int, table_name: str):
    """
    Writes a DataFrame to a PostgreSQL table in a micro-batch.

    This function is executed for each micro-batch of the streaming query.
    It handles writing the data to the specified table and logs the status.

    Args:
        df (DataFrame): The DataFrame to be written.
        epoch_id (int): The current micro-batch ID.
        table_name (str): The name of the target PostgreSQL table.
    """
    # This function is called for each micro-batch
    count = df.count()
    if count > 0:
        print(f"--> [Batch {epoch_id}] Writing {count} records to table '{table_name}'...")
        try:
            df.write \
                .format("jdbc") \
                .options(**PG_CONFIG) \
                .option("dbtable", table_name) \
                .mode("append") \
                .save()
            print("   [OK] Success.")
        except Exception as e:
            print(f"   [ERROR] Failed to write to Postgres: {e}")
    else:
        # Empty batch, skipping.
        pass


def main():
    """
    Initializes the Spark session and starts the streaming queries.

    This is the main entry point of the application. It sets up the Spark
    session with S3 and JDBC configurations, defines two separate streaming
    pipelines for temperature and CO2 data, and starts them. The application
    waits for the termination of the streams.
    """
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
    print(">>> CONTINUOUS PROCESSOR ACTIVE (Watching MinIO -> Postgres)...")

    # ---------------------------------------------------------
    # Continuous reading (readStream) instead of Batch (read)
    # ---------------------------------------------------------

    # 1. Temperature Stream
    # Read raw temperature data from the S3 source.
    df_temp_raw = spark.readStream \
        .format("csv") \
        .option("header", "false") \
        .schema("year INT, temp DOUBLE, country STRING, unit STRING, _c4 STRING, _c5 STRING, _c6 STRING") \
        .load("s3a://raw-data/temperature/")

    # Select and clean the required columns for the temperature data.
    df_temp = df_temp_raw.select(
        col("year").alias("Year"),
        col("temp").alias("Temp_Change"),
        col("country").alias("Country")
    ).filter(col("Year").isNotNull())

    # 2. Emissions Stream
    # Read raw CO2 emissions data from the S3 source.
    df_co2_raw = spark.readStream \
        .format("csv") \
        .option("header", "false") \
        .schema("year INT, emissions DOUBLE, country STRING, element STRING, unit STRING, item STRING, source STRING") \
        .load("s3a://raw-data/emissions/")

    # Select and clean the required columns for the CO2 emissions data.
    df_co2 = df_co2_raw.select(
        col("year").alias("Year"),
        col("emissions").alias("Emissions"),
        col("country").alias("Country"),
        col("item").alias("Item")
    ).filter(col("Year").isNotNull())

    # ---------------------------------------------------------
    # Writing (writeStream)
    # ---------------------------------------------------------

    # Process Temperature every 30 seconds
    query_temp = df_temp.writeStream \
        .foreachBatch(lambda df, id: write_to_postgres(df, id, "climate_analysis")) \
        .trigger(processingTime='30 seconds') \
        .start()

    # Process CO2 every 30 seconds
    query_co2 = df_co2.writeStream \
        .foreachBatch(lambda df, id: write_to_postgres(df, id, "co2_emissions")) \
        .trigger(processingTime='30 seconds') \
        .start()

    # Wait for any of the streams to terminate
    spark.streams.awaitAnyTermination()

if __name__ == "__main__":
    main()