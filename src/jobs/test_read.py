"""
This module provides a test utility to verify Spark's ability to read from a MinIO bucket.

It initializes a Spark session with the necessary S3 configurations,
attempts to read a CSV file from a specified MinIO bucket, and prints the
schema and a preview of the DataFrame upon success.
"""

from pyspark.sql import SparkSession
from dotenv import load_dotenv
import os

# Load the .env file to get MinIO credentials
load_dotenv()

def test_spark_read_from_minio():
    """
    Initializes a Spark session and tests reading data from MinIO.

    This function configures a Spark session to connect to a MinIO instance
    using credentials from environment variables. It then attempts to read a
    CSV file from the 'raw-data/nasa' bucket and displays its schema and
    first 5 rows.

    The required packages 'org.apache.hadoop:hadoop-aws:3.3.4' are included
    in the Spark configuration to enable S3A filesystem support.
    """
    # Initialize Spark with the necessary packages to read from S3/MinIO
    # Note: These "org.apache.hadoop..." packages are MANDATORY
    spark = SparkSession.builder \
        .appName("MinIOTest") \
        .config("spark.jars.packages", "org.apache.hadoop:hadoop-aws:3.3.4") \
        .config("spark.hadoop.fs.s3a.endpoint", "http://localhost:9000") \
        .config("spark.hadoop.fs.s3a.access.key", os.getenv("MINIO_USER")) \
        .config("spark.hadoop.fs.s3a.secret.key", os.getenv("MINIO_PASSWORD")) \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .getOrCreate()

    print("Spark Session created! Attempting to read from MinIO...")

    try:
        # Attempt to read the CSV you just uploaded
        df = spark.read.option("header", "true").csv("s3a://raw-data/nasa/temperature.csv")

        print("Success! File schema:")
        df.printSchema()
        df.show(5)
    except Exception as e:
        print(f"Error reading from MinIO: {e}")
    finally:
        # Stop the Spark session
        spark.stop()


if __name__ == "__main__":
    test_spark_read_from_minio()