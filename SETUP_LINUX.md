# Climate Analytics Platform: Real-Time Ingestion Pipeline

**Environment:** Ubuntu Server 22.04 (Native)
**Branch:** `feature/real-time-ingestion`
**Orchestration:** Kubernetes (Minikube)
**Container Engine:** Docker

## 1. Environment Prerequisite Setup
Execute the following commands to install the required CLI tools (`kubectl` and `minikube`).

### 1.1. System Dependencies
```bash
sudo apt update && sudo apt install -y curl git conntrack
```

### 1.2. Install Kubectl (Cluster CLI)

```bash
curl -LO "[https://dl.k8s.io/release/$(curl](https://dl.k8s.io/release/$(curl) -L -s [https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl](https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl)"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
```

### 1.3. Install Minikube (Local Cluster)

```bash
curl -LO [https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64](https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64)
sudo install minikube-linux-amd64 /usr/local/bin/minikube
```

-----

## 2\. Project Initialization

Clone the repository and initialize the Kubernetes cluster using the Docker driver.

```bash
cd ~/Desktop
git clone -b feature/real-time-ingestion https://github.com/jotaantunes03/iacd-climate-analytics-platform.git
cd iacd-climate-analytics-platform

# Start Minikube
minikube start --driver=docker
```

-----

## 3\. Image Build (Internal Registry)

**Critical Step:** You must point the shell to Minikube's internal Docker daemon. Otherwise, the cluster will not be able to pull the local images.

```bash
# 1. Point shell to Minikube's Docker environment
eval $(minikube -p minikube docker-env)

# 2. Build the ingestion image (tagged as vfinal)
docker build -t climate-ingestion:vfinal -f Dockerfile.ingestion .
```

-----

## 4\. Infrastructure Deployment

Deploy the persistent volumes, services, and pods defined in the manifest.

```bash
# 1. Apply Kubernetes manifests
kubectl apply -f k8s/deployment.yml

# 2. Enforce the correct image version for the Producer
kubectl set image deployment/stream-producer producer=climate-ingestion:vfinal

# 3. Wait for all pods to reach 'Running' or 'Completed' status
kubectl get pods -w
# Press Ctrl+C once all pods are stable
```

-----

## 5\. Execution: Spark Streaming Consumer

Launch the Spark Structured Streaming job to consume data from the TCP socket.

### 5.1. Configure Environment Variables

```bash
export MASTER_POD=$(kubectl get pods -l app=spark-master -o jsonpath="{.items[0].metadata.name}")
export MASTER_IP=$(kubectl get pods -l app=spark-master -o jsonpath="{.items[0].status.podIP}")

echo "Targeting Master Pod: $MASTER_POD at $MASTER_IP"
```

### 5.2. Deploy Job Script

Copy the streaming logic script to the Spark Master container.

```bash
kubectl cp src/jobs/streaming_job.py $MASTER_POD:/tmp/streaming_job.py
```

### 5.3. Submit Job

Execute the job with specific resource constraints to avoid OOM errors.

```bash
kubectl exec -it $MASTER_POD -- /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --conf spark.driver.host=$MASTER_IP \
  --conf spark.driver.bindAddress=0.0.0.0 \
  --conf spark.executor.memory=512m \
  --conf spark.driver.memory=512m \
  --conf spark.cores.max=1 \
  /tmp/streaming_job.py
```

*Verification:* You should see tabular data (Year, Temperature, Country) updating in the console every second.



### 5.4. Verification
After submitting the job, check the terminal output. You should see tabular data (batches) updating every second with columns: `Year`, `Temperature`, and `Country`.

**Example Output:**
```text
-------------------------------------------
Batch: 5
-------------------------------------------
+----+-----------+-----------+
|Year|Temperature|    Country|
+----+-----------+-----------+
|1997|      0.425|Afghanistan|
|1998|      0.577|Afghanistan|
+----+-----------+-----------+
````

> **Note:** This job runs indefinitely. Do not close this terminal if you want to keep seeing the stream. To stop it, press `Ctrl+C`.

-----

## 6\. Historical Data Processing (Batch Job)

The streaming job above visualizes real-time data but does **not** save it to the database. To populate the PostgreSQL database for the dashboards, you must run the batch processor once.

### 6.1. Deploy Dependencies & Script

The batch job requires additional JARs (for S3 and Postgres connectivity) and the main processing script.

```bash
# 1. Download required JARs (if not present)
mkdir -p jars
wget -P jars/ [https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.540/aws-java-sdk-bundle-1.12.540.jar](https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.540/aws-java-sdk-bundle-1.12.540.jar)
wget -P jars/ [https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar](https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar)
wget -P jars/ [https://jdbc.postgresql.org/download/postgresql-42.6.0.jar](https://jdbc.postgresql.org/download/postgresql-42.6.0.jar)

# 2. Copy JARs to Spark Master
kubectl exec $MASTER_POD -- mkdir -p /tmp/dependencies
kubectl cp jars/aws-java-sdk-bundle-1.12.540.jar $MASTER_POD:/tmp/dependencies/
kubectl cp jars/hadoop-aws-3.3.4.jar $MASTER_POD:/tmp/dependencies/
kubectl cp jars/postgresql-42.6.0.jar $MASTER_POD:/tmp/dependencies/

# 3. Copy Batch Script
kubectl cp src/jobs/main.py $MASTER_POD:/tmp/main.py
```

### 6.2. Run the Batch Job

```bash
kubectl exec -it $MASTER_POD -- /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --conf spark.driver.host=$MASTER_IP \
  --conf spark.driver.bindAddress=0.0.0.0 \
  --conf spark.executor.memory=512m \
  --conf spark.driver.memory=512m \
  --conf spark.cores.max=1 \
  --jars /tmp/dependencies/aws-java-sdk-bundle-1.12.540.jar,/tmp/dependencies/hadoop-aws-3.3.4.jar,/tmp/dependencies/postgresql-42.6.0.jar \
  /tmp/main.py
```

*Success Criterion:* The logs should end with `>>> SUCESSO! Job terminado.`

-----

## 7\. Visualization & System Validation (Grafana)

Verify the end-to-end pipeline via the VM's web browser.

### 7.1. Expose Grafana Service

Open a **new terminal window** and run:

```bash
kubectl port-forward service/grafana 3000:3000 --address 0.0.0.0
```

### 7.2. Browser Validation Steps

Open the browser inside your VM (Firefox/Chrome) or on your host machine (using the VM's IP) and navigate to `http://localhost:3000`.

1.  **Login:**

      * **User:** `admin`
      * **Password:** `admin` (skip password change if prompted).

2.  **Configure Data Source:**

      * Go to **Connections** \> **Data Sources** \> **Add data source**.
      * Select **PostgreSQL**.
      * **Host:** `postgres:5432` (Internal K8s DNS).
      * **Database:** `climate_analysis`.
      * **User:** `admin`
      * **Password:** `climatechange`.
      * **TLS/SSL Mode:** `disable`.
      * Click **Save & Test**.
      * *Success Criterion:* Green message "Database Connection OK".

3.  **Visualize Data:**

      * Go to **Dashboards** \> **New Dashboard** \> **Add visualization**.
      * Select the PostgreSQL datasource.
      * Switch to **Code** view (SQL Editor) and run:
        ```sql
        SELECT "Year" as time, AVG("Temp_Change") as value 
        FROM climate_analysis 
        GROUP BY "Year" 
        ORDER BY "Year" ASC
        ```
      * Click **Run Query**. If the graph loads, the batch pipeline is fully functional.

-----

## 8\. Operational Cheat Sheet

| Action | Command |
| :--- | :--- |
| **Check Cluster Status** | `kubectl get pods` |
| **View Producer Logs** | `kubectl logs -l app=stream-producer -f` |
| **Restart Producer** | `kubectl delete pod -l app=stream-producer` |
| **Stop Cluster** | `minikube stop` |
| **Reset Environment** | `minikube delete` |

```
```