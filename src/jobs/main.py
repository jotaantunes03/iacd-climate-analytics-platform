import sys
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, expr, regexp_replace

def main():
    # 1. Configurar Spark
    spark = SparkSession.builder \
        .appName("ClimateAnalytics") \
        .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000") \
        .config("spark.hadoop.fs.s3a.access.key", "minioadmin") \
        .config("spark.hadoop.fs.s3a.secret.key", "minioadmin") \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false") \
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")
    
    print(">>> A iniciar processamento...")

    try:
        # 2. Ler Dados do MinIO (CAMINHOS CORRIGIDOS)
        df_emissions = spark.read.csv("s3a://raw-data/carbon/co2.csv", header=True, inferSchema=True)
        df_temp = spark.read.csv("s3a://raw-data/nasa/temperature.csv", header=True, inferSchema=True)
        
        print(">>> Ficheiros lidos com sucesso. A transformar...")

        # 3. Transformação
        year_columns = [c for c in df_emissions.columns if c.startswith('Y') and not c.endswith('F') and not c.endswith('N')]
        
        stack_expr = f"stack({len(year_columns)}, " + \
                     ", ".join([f"'{c}', {c}" for c in year_columns]) + \
                     ") as (Year_Raw, Emission_Value)"

        df_emissions_long = df_emissions.select(
            col("Area").alias("Country"),
            col("Item"), 
            expr(stack_expr)
        ).withColumn("Year", regexp_replace("Year_Raw", "Y", "").cast("int"))

        # 4. Limpar Temperaturas
        df_temp_clean = df_temp.select(
            col("Area").alias("Country"),
            col("Year"),
            col("Value").alias("Temp_Change")
        ).filter(col("Element") == "Temperature change")

        # Join final
        df_final = df_emissions_long.join(
            df_temp_clean, 
            on=["Country", "Year"], 
            how="inner"
        )

        print(">>> Dados transformados. Exemplo:")
        df_final.show(5)

        # 5. Gravar no Postgres (Tabela e DB corrigidas)
        print(">>> A gravar na Base de Dados...")
        df_final.write \
            .format("jdbc") \
            .option("url", "jdbc:postgresql://postgres:5432/climate_db") \
            .option("dbtable", "public.climate_analysis") \
            .option("dbtable", "public.climate_analysis") \
            .option("user", "admin") \
            .option("password", "climatechange") \
            .option("driver", "org.postgresql.Driver") \
            .mode("overwrite") \
            .save()
            
        print(">>> SUCESSO! Job terminado.")

    except Exception as e:
        print(f"!!! ERRO CRÍTICO: {e}")
        sys.exit(1)
    finally:
        spark.stop()

if __name__ == "__main__":
    main()