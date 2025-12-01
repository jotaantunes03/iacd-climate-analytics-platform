from pyspark.sql import SparkSession
from pyspark.sql.functions import col, expr, regexp_replace

# 1. Inicializar Spark com suporte a S3 e Postgres
spark = SparkSession.builder \
    .appName("ClimateAnalytics") \
    .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000") \
    .config("spark.hadoop.fs.s3a.access.key", "minioadmin") \
    .config("spark.hadoop.fs.s3a.secret.key", "minioadmin") \
    .config("spark.hadoop.fs.s3a.path.style.access", "true") \
    .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
    .getOrCreate()

# 2. Ler Dados (Ajustar caminho se estiveres a testar local vs docker)
# No cluster usa: s3a://raw-data/Emissions.csv
df_emissions = spark.read.csv("s3a://raw-data/Emissions.csv", header=True, inferSchema=True)
df_temp = spark.read.csv("s3a://raw-data/Temperature.csv", header=True, inferSchema=True)

# 3. TRUQUE: Unpivot (Melt) no ficheiro de Emissões
# Transformar colunas Y1961, Y1962... numa única coluna "Year" e "Emission"
# Isto é complexo, precisamos gerar uma string SQL dinâmica para o 'stack'
year_columns = [c for c in df_emissions.columns if c.startswith('Y') and not c.endswith('F') and not c.endswith('N')]
stack_expr = f"stack({len(year_columns)}, " + \
             ", ".join([f"'{c}', {c}" for c in year_columns]) + \
             ") as (Year_Raw, Emission_Value)"

df_emissions_long = df_emissions.select(
    col("Area"),
    col("Item"), 
    expr(stack_expr)
).withColumn("Year", regexp_replace("Year_Raw", "Y", "").cast("int"))

# 4. Limpar Temperaturas
df_temp_clean = df_temp.select(
    col("Area"),
    col("Year"),
    col("Value").alias("Temp_Change")
).filter(col("Element") == "Temperature change")

# 5. Juntar Tudo (Join)
df_final = df_emissions_long.join(
    df_temp_clean, 
    on=["Area", "Year"], 
    how="inner"
)

# 6. Gravar no Postgres (Tabela final para o Grafana)
# Nota: Precisas do driver JDBC configurado
df_final.write \
    .format("jdbc") \
    .option("url", "jdbc:postgresql://postgres:5432/climate_db") \
    .option("dbtable", "climate_analysis") \
    .option("user", "admin") \
    .option("password", "password") \
    .mode("overwrite") \
    .save()

print("Processamento concluído!")
spark.stop()