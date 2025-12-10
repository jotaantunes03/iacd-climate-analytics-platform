# Climate Analytics Platform: Real-Time Ingestion Setup Guide

**Version:** 1.0  
**Environment:** Windows (PowerShell) + Docker Desktop (Kubernetes)  
**Objective:** Deploy the infrastructure, initialize the Data Lake, and start the real-time data ingestion pipeline.

---

## Prerequisites

Before running the commands, ensure you have the following ready:
1.  **Docker Desktop** installed with **Kubernetes enabled**.
2.  **PowerShell** terminal.
3.  **Git** installed.
4.  **Java JAR Dependencies:** Ensure you have a folder named `jars/` in the project root containing:
    * `aws-java-sdk-bundle-1.12.540.jar`
    * `hadoop-aws-3.3.4.jar`

---

## Phase 1: Setup & Clean State

If you have run this project before, perform a full cleanup to ensure no stale data (checkpoints/databases) conflicts with the new deployment.

### 1.1. Clone Repository
```powershell
# Clone the specific branch (replace <url> with your repo URL)
git clone -b feature/real-time-ingestion <your-repo-url>
cd iacd-climate-analytics-platform
````

### 1.2. Reset Cluster Resources

Execute the following to remove all existing deployments and persistent volumes.

```powershell
# 1. Delete all K8s resources
kubectl delete -f k8s/deployment.yml

# 2. Delete Persistent Volume Claims (CRITICAL for cleaning MinIO/Postgres)
kubectl delete pvc --all

# 3. Verify cleanup (Should return "No resources found")
kubectl get all
```

-----

## Phase 2: Build & Deploy Infrastructure

We will build the custom Docker image for the ingestion component and deploy the Kubernetes cluster.

### 2.1. Build Docker Image

```powershell
# 2. Mudar explicitamente para o docker-desktop
kubectl config use-context docker-desktop
# Build the image containing the Python Producer and scripts
docker build -t climate-ingestion:vfinal -f Dockerfile.ingestion .
```

### 2.2. Deploy Kubernetes Manifests

```powershell
# Apply the configuration
kubectl apply -f k8s/deployment.yml
```

### 2.3. Wait for Pod Initialization

Monitor the pods until all status columns show **Running**.

```powershell
kubectl get pods -w
# Press Ctrl+C once all pods (minio, postgres, spark, producer) are Running
```

-----

## Phase 3: Configuration & Initialization

Now that the infrastructure is up, we must prepare the storage (MinIO) and the processing engine (Spark).

### 3.1. Initialize MinIO Buckets

Run the initialization script inside the producer container to create the `raw-data` bucket.

```powershell
kubectl exec -it deployment/stream-producer -- python src/ingestion/init_minio.py
```

  * **Expected Output:** `[CRIADO] Bucket 'raw-data'`

### 3.2. Inject Spark Dependencies

We need to copy the AWS/S3 drivers and the job script into the Spark Master pod.

```powershell
# 1. Capture Master Pod Name and IP into variables
$MASTER_POD = kubectl get pods -l app=spark-master -o jsonpath="{.items[0].metadata.name}"
$MASTER_IP = kubectl get pods -l app=spark-master -o jsonpath="{.items[0].status.podIP}"

Write-Host "Targeting Master: $MASTER_POD | Internal IP: $MASTER_IP"

# 2. Create dependencies folder inside the Pod
kubectl exec $MASTER_POD -- mkdir -p /tmp/dependencies

# 3. Inject JARs from your local 'jars/' folder
kubectl cp jars/aws-java-sdk-bundle-1.12.540.jar "$($MASTER_POD):/tmp/dependencies/aws-java-sdk-bundle-1.12.540.jar"
kubectl cp jars/hadoop-aws-3.3.4.jar "$($MASTER_POD):/tmp/dependencies/hadoop-aws-3.3.4.jar"

# 4. Upload the Streaming Job Script
kubectl cp src/jobs/streaming_job.py "$($MASTER_POD):/tmp/streaming_job.py"
```

-----

## Phase 4: Execution

Launch the Spark Structured Streaming job. This job connects to the socket stream, processes the data, and writes it to MinIO.

```powershell
kubectl exec -it $MASTER_POD -- /opt/spark/bin/spark-submit `
  --master spark://spark-master:7077 `
  --conf spark.driver.host=$MASTER_IP `
  --conf spark.driver.bindAddress=0.0.0.0 `
  --conf spark.executor.memory=512m `
  --conf spark.driver.memory=512m `
  --conf spark.cores.max=1 `
  --jars /tmp/dependencies/aws-java-sdk-bundle-1.12.540.jar,/tmp/dependencies/hadoop-aws-3.3.4.jar `
  /tmp/streaming_job.py
```

> **Note:** Keep this terminal open. You will see logs indicating batch processing.

-----

## Phase 5: Verification

Verify that data is successfully arriving in the Data Lake.

### 5.1. Access MinIO Console

Open a **new PowerShell window** and run:

```powershell
kubectl port-forward service/minio 9001:9001
```

### 5.2. Browser Check

1.  Open your browser to: [http://localhost:9001](https://www.google.com/search?q=http://localhost:9001)
2.  **Credentials:** User: `minioadmin` | Pass: `minioadmin`
3.  Navigate to **Buckets** \> **raw-data**.

**Success Criteria:**
You should see two distinct folders being populated with CSV files:

  *  **`temperature/`** (Contains Temperature data)
  *  **`emissions/`** (Contains CO2/CH4/N2O data)

-----

## Architectural Overview & Next Steps

### What have we achieved?

We have successfully implemented the **Ingestion Layer** of a Lambda Architecture.

1.  **Source (Producer):** A Python script (`stream_server.py`) reads static CSVs (Temperature and CO2), standardizes their columns, and streams them continuously over a TCP Socket on port 9999.
2.  **Ingestion (Spark Streaming):** The `streaming_job.py` connects to this socket. It acts as a router.
      * It identifies the type of data based on specific columns.
      * It splits the stream into two separate paths.
3.  **Storage (Data Lake):** The data is persisted into **MinIO** (S3 compatible storage) in `CSV` format. This creates a persistent "Raw Layer" that allows for historical reprocessing if needed.

### What is missing? (The "Batch" & "Serving" Layers)

Currently, the data is sitting in CSV files in MinIO. It is not yet accessible by the dashboard.

To complete the pipeline, we need to implement **Phase 2 (Batch Processing)**:

1.  **Batch Job (`main.py`):** Create a Spark job that reads the accumulated CSV files from MinIO (`raw-data`).
2.  **Transformation:** Aggregating data (e.g., Average Temperature per Year vs. Total Emissions).
3.  **Serving Layer (PostgreSQL):** Writing the clean, structured data into the Postgres database.
4.  **Visualization (Grafana):** Connecting Grafana to Postgres to visualize the trends.

-----

## Phase 6: Batch Processing (ETL)

Agora que os dados estão a chegar ao MinIO (Raw Layer), precisamos de correr o job de processamento (`main.py`) para transformar os dados e gravá-los no PostgreSQL.

### 6.1. Preparar Dependências do Batch

O job de batch necessita do driver JDBC do PostgreSQL, que ainda não foi copiado para o cluster, e do script `main.py` atualizado.

```powershell
# 1. Recuperar variáveis (caso tenhas fechado o terminal anterior)
$MASTER_POD = kubectl get pods -l app=spark-master -o jsonpath="{.items[0].metadata.name}"
$MASTER_IP = kubectl get pods -l app=spark-master -o jsonpath="{.items[0].status.podIP}"

Write-Host "Master Pod: $MASTER_POD"

# 2. Injetar o Driver do PostgreSQL (Essencial para gravar na BD)
kubectl cp jars/postgresql-42.6.0.jar "$($MASTER_POD):/tmp/dependencies/postgresql-42.6.0.jar"

# 3. Copiar o Script de Processamento (main.py)
kubectl cp src/jobs/main.py "$($MASTER_POD):/tmp/main.py"
```

### 6.2. Executar o Job Batch

Este comando submete o job ao Spark Master. Nota que adicionámos o `.jar` do Postgres à lista de `--jars`.

> **Nota:** Certifica-te que a password da base de dados no ficheiro `src/jobs/main.py` corresponde à definida no `k8s/deployment.yml` (default: `climatechange` ou `admin123` dependendo da tua versão).

```powershell
kubectl exec -it $MASTER_POD -- /opt/spark/bin/spark-submit `
  --master spark://spark-master:7077 `
  --conf spark.driver.host=$MASTER_IP `
  --conf spark.driver.bindAddress=0.0.0.0 `
  --conf spark.executor.memory=512m `
  --conf spark.driver.memory=512m `
  --conf spark.cores.max=1 `
  --jars /tmp/dependencies/aws-java-sdk-bundle-1.12.540.jar,/tmp/dependencies/hadoop-aws-3.3.4.jar,/tmp/dependencies/postgresql-42.6.0.jar `
  /tmp/main.py
```

  * **Output Esperado:** Deverás ver logs de processamento e, no final, uma mensagem indicando `>>> SUCESSO! Job terminado.` ou logs indicando `Gravando X registos...`.

-----

## 📊 Phase 7: Visualization (Grafana)

Com os dados processados e guardados no PostgreSQL, vamos configurar o Grafana para visualizar as métricas.

### 7.1. Expor o Grafana

Abre uma **nova janela do PowerShell** e executa:

```powershell
kubectl port-forward service/grafana 3000:3000
```

### 7.2. Configurar Dashboard

1.  Acede a [http://localhost:3000](https://www.google.com/search?q=http://localhost:3000) no teu browser.

2.  **Login:** User: `admin` | Pass: `admin` (podes saltar a alteração de password).

3.  **Adicionar Data Source:**

      * Vai a **Connections** \> **Data Sources** \> **Add data source** \> **PostgreSQL**.
      * **Host:** `postgres:5432`
      * **Database:** `climate_analysis`
      * **User:** `admin`
      * **Password:** `climatechange` (conforme definido no `deployment.yml`).
      * **TLS/SSL Mode:** `disable`
      * Clica em **Save & Test**. (Deve aparecer "Database Connection OK").

4.  **Criar Gráfico:**

      * Clica em **Dashboards** \> **New Dashboard** \> **Add visualization**.
      * Seleciona o PostgreSQL.
      * Muda para a vista de código (**Code**) e cola a query:

    <!-- end list -->

    ```sql
    SELECT "Year" as time, AVG("Temp_Change") as value 
    FROM climate_analysis 
    GROUP BY "Year" 
    ORDER BY "Year" ASC
    ```

      * Clica em **Run Query**. Deverás ver o gráfico da temperatura global.

-----

## Phase 8: Cleanup

Para parar o projeto e libertar recursos do teu computador:

```powershell
# 1. Parar o Port-Forwarding (Ctrl+C nos terminais abertos)

# 2. Remover recursos do Kubernetes
kubectl delete -f k8s/deployment.yml

# 3. (Opcional) Parar o Minikube/Kubernetes no Docker
# minikube stop
```