from pyspark.sql import SparkSession
from pyspark.sql.functions import split, col, trim
import sys

# Configuração
spark = SparkSession.builder \
    .appName("ClimateStreamingRobust") \
    .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000") \
    .config("spark.hadoop.fs.s3a.access.key", "minioadmin") \
    .config("spark.hadoop.fs.s3a.secret.key", "minioadmin") \
    .config("spark.hadoop.fs.s3a.path.style.access", "true") \
    .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
    .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

# --- LIMPEZA AUTOMÁTICA DE CHECKPOINTS ---
try:
    print(">>> A limpar checkpoints antigos para evitar conflitos...")
    fs = spark._jvm.org.apache.hadoop.fs.FileSystem.get(spark._jsc.hadoopConfiguration())
    fs.delete(spark._jvm.org.apache.hadoop.fs.Path("s3a://raw-data/checkpoints/"), True)
except Exception as e:
    print(f"!!! (Info) Checkpoints não limpos ou inexistentes: {e}")

# 1. Ler do Socket
lines = spark.readStream \
    .format("socket") \
    .option("host", "stream-source") \
    .option("port", 9999) \
    .load()

# 2. Parse (Usando \\| para escapar o pipe)
raw_data = lines.select(
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

# 3. Separar Streams com Lógica ROBUSTA
# Usamos trim() para remover espaços em branco que possam enganar o filtro
# 'Domain' só existe na Temperatura. 'Item' só existe no CO2.
# Verificamos também se não é "nan" (string) ou "N/A"

df_temp = raw_data.filter(
    (trim(col("Domain")) != "N/A") &
    (trim(col("Domain")) != "nan")
).select("Year", "Value", "Area", "Element", "Unit", "Domain", "Months")

df_co2 = raw_data.filter(
    (trim(col("Item")) != "N/A") &
    (trim(col("Item")) != "nan")
).select("Year", "Value", "Area", "Element", "Unit", "Item", "Source")

# 4. Escrever
# Trigger aumentado para 10 segundos para apanhar mais dados misturados
query_temp = df_temp.writeStream \
    .outputMode("append") \
    .format("csv") \
    .option("path", "s3a://raw-data/temperature/") \
    .option("checkpointLocation", "s3a://raw-data/checkpoints/temperature/") \
    .option("header", "false") \
    .trigger(processingTime='10 seconds') \
    .start()

query_co2 = df_co2.writeStream \
    .outputMode("append") \
    .format("csv") \
    .option("path", "s3a://raw-data/emissions/") \
    .option("checkpointLocation", "s3a://raw-data/checkpoints/emissions/") \
    .option("header", "false") \
    .trigger(processingTime='10 seconds') \
    .start()

spark.streams.awaitAnyTermination()