"""
This module defines a Spark Streaming job that reads climate data from a socket,
parses it, separates it into two distinct streams (temperature and CO2), and
writes them to separate locations in a MinIO S3 bucket.
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import split, col, trim
import sys

# --- Spark Session Configuration ---
# Initializes a Spark session with S3 configurations for MinIO.
spark = SparkSession.builder \
    .appName("ClimateStreamingRobust") \
    .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000") \
    .config("spark.hadoop.fs.s3a.access.key", "minioadmin") \
    .config("spark.hadoop.fs.s3a.secret.key", "minioadmin") \
    .config("spark.hadoop.fs.s3a.path.style.access", "true") \
    .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
    .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false") \
    .config("spark.sql.adaptive.enabled", "false") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

# 1. Read from Socket
# Creates a DataFrame representing the stream of data from the specified socket.
socket_stream_df = spark.readStream \
    .format("socket") \
    .option("host", "stream-source") \
    .option("port", 9999) \
    .load()

# 2. Parse Data (Escaping the pipe character)
# Splits the single 'value' column into multiple columns based on the '|' delimiter.
parsed_data_df = socket_stream_df.select(
    split(col("value"), "\\|").getItem(0).alias("Year"),
    split(col("value"), "\\|").getItem(1).alias("Value"),
    split(col("value"), "\\|").getItem(2).alias("Area"),
    split(col("value"), "\\|").getItem(3).alias("Area_Code"),
    split(col("value"), "\\|").getItem(4).alias("Element"),
    split(col("value"), "\\|").getItem(5).alias("Element_Code"),
    split(col("value"), "\\|").getItem(6).alias("Unit"),
    split(col("value"), "\\|").getItem(7).alias("Flag"),
    split(col("value"), "\\|").getItem(8).alias("Domain"),
    split(col("value"), "\\|").getItem(9).alias("Domain_Code"),
    split(col("value"), "\\|").getItem(10).alias("Months"),
    split(col("value"), "\\|").getItem(11).alias("Months_Code"),
    split(col("value"), "\\|").getItem(12).alias("Flag_Desc"),
    split(col("value"), "\\|").getItem(13).alias("Item"),
    split(col("value"), "\\|").getItem(14).alias("Item_Code"),
    split(col("value"), "\\|").getItem(15).alias("Source"),
    split(col("value"), "\\|").getItem(16).alias("Source_Code")
)

# 3. Split Streams with Robust Logic
# The logic separates the raw data into two DataFrames based on unique columns.
# We use trim() to remove whitespace that might interfere with the filter.
# 'Domain' only exists in Temperature data. 'Item' only exists in CO2 data.
# We also check for "nan" (string) or "N/A" to ensure data quality.

temperature_df = parsed_data_df.filter(
    (trim(col("Domain")) != "N/A") &
    (trim(col("Domain")) != "nan")
).select("Year", "Value", "Area", "Element", "Unit", "Domain", "Months")

co2_df = parsed_data_df.filter(
    (trim(col("Item")) != "N/A") &
    (trim(col("Item")) != "nan")
).select("Year", "Value", "Area", "Element", "Unit", "Item", "Source")

# 4. Write Streams to S3
# Configure and start the streaming queries to write the data to S3.
# The trigger is set to 10 seconds to capture more mixed data in each batch.

temperature_query = temperature_df.writeStream \
    .outputMode("append") \
    .format("csv") \
    .option("path", "s3a://raw-data/temperature/") \
    .option("checkpointLocation", "s3a://raw-data/checkpoints/temperature/") \
    .option("header", "false") \
    .trigger(processingTime='20 seconds') \
    .start()

co2_query = co2_df.writeStream \
    .outputMode("append") \
    .format("csv") \
    .option("path", "s3a://raw-data/emissions/") \
    .option("checkpointLocation", "s3a://raw-data/checkpoints/emissions/") \
    .option("header", "false") \
    .trigger(processingTime='20 seconds') \
    .start()

# Wait for any of the streams to terminate
spark.streams.awaitAnyTermination()