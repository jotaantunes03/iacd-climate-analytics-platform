from pyspark.sql import SparkSession
from pyspark.sql.functions import split, col

spark = SparkSession.builder \
    .appName("ClimateStreaming") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

# 1. Ler do Socket (Stream Source)
# O host é o nome do serviço Kubernetes: 'stream-source' na porta 9999
lines = spark.readStream \
    .format("socket") \
    .option("host", "stream-source") \
    .option("port", 9999) \
    .load()

# 2. Processar (Separar as vírgulas)
# O formato enviado pelo Produtor é: Year,Value,Area
# Exemplo: 1961,-0.096,Afghanistan
data = lines.select(
    split(col("value"), ",").getItem(0).alias("Year"),
    split(col("value"), ",").getItem(1).alias("Temperature"),
    split(col("value"), ",").getItem(2).alias("Country")
)

# 3. Output (Escreve na consola)
query = data.writeStream \
    .outputMode("append") \
    .format("console") \
    .start()

query.awaitTermination()