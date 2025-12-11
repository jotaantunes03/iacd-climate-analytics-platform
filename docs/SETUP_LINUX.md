# Setup Guide: Climate Analytics Platform on Linux

This guide details the steps to deploy and run the real-time climate analytics pipeline on a native Ubuntu Server 22.04 environment using Minikube and Docker.

**Target Environment:**
*   **OS:** Ubuntu Server 22.04
*   **Branch:** `feature/real-time-ingestion`
*   **Orchestration:** Kubernetes (Minikube)
*   **Container Engine:** Docker

---

## 1. Install Prerequisites

Install the necessary command-line tools and system dependencies.

### 1.1. System Dependencies
```bash
sudo apt update && sudo apt install -y curl git conntrack
```

### 1.2. Install `kubectl`
`kubectl` is the command-line tool for interacting with a Kubernetes cluster.
```bash
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
```

### 1.3. Install `minikube`
`minikube` is used to run a local Kubernetes cluster.
```bash
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube
```

---

## 2. Initialize the Project

Clone the project repository and start the local Kubernetes cluster.

```bash
# Navigate to your preferred directory
cd ~/Desktop

# Clone the specific project branch
git clone -b feature/real-time-ingestion https://github.com/jotaantunes03/iacd-climate-analytics-platform.git
cd iacd-climate-analytics-platform

# Start the Minikube cluster using the Docker driver
minikube start --driver=docker
```

---

## 3. Build the Application Image

Build the Docker image for the data ingestion service.

**IMPORTANT:** You must connect your terminal to Minikube's internal Docker registry. This allows the Kubernetes cluster to find and use the local image you are about to build.

```bash
# 1. Point your shell to Minikube's Docker daemon
eval $(minikube -p minikube docker-env)

# 2. Build the ingestion image and tag it as 'climate-ingestion:vfinal'
docker build -t climate-ingestion:vfinal -f Dockerfile.ingestion .
```

---

## 4. Deploy Kubernetes Infrastructure

Apply the Kubernetes manifests to deploy all required resources, including services, persistent volumes, and pods for Spark, MinIO, and PostgreSQL.

```bash
# 1. Apply all manifests from the deployment file
kubectl apply -f k8s/deployment.yml

# 2. Ensure the producer deployment uses the correct local image
kubectl set image deployment/stream-producer producer=climate-ingestion:vfinal

# 3. Monitor pod status until all are 'Running' or 'Completed'
echo "Waiting for all pods to initialize..."
kubectl get pods -w
# Press Ctrl+C once all pods are stable.
```

---

## 5. Run the Real-Time Streaming Job

Launch the Spark Structured Streaming job that consumes data from the producer and displays it in real-time.

### 5.1. Set Environment Variables
These variables capture the Spark Master's pod name and IP address, which are required for submitting the job.
```bash
export MASTER_POD=$(kubectl get pods -l app=spark-master -o jsonpath="{.items[0].metadata.name}")
export MASTER_IP=$(kubectl get pods -l app=spark-master -o jsonpath="{.items[0].status.podIP}")

echo "Targeting Spark Master Pod: $MASTER_POD at $MASTER_IP"
```

### 5.2. Copy Script to Spark Master
Copy the Python script containing the streaming logic into the Spark Master pod.
```bash
kubectl cp src/jobs/streaming_job.py $MASTER_POD:/tmp/streaming_job.py
```

### 5.3. Submit the Spark Job
Submit the job to the Spark cluster with resource limits to prevent memory issues.
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

### 5.4. Verify the Stream
After submission, the console will display micro-batches of data every few seconds. This job runs indefinitely until manually stopped (`Ctrl+C`).

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
```

---

## 6. Run the Historical Batch Processing Job

The streaming job is for real-time visualization only. To permanently store the full dataset in PostgreSQL for dashboard analysis, run this one-time batch job.

### 6.1. Deploy Dependencies and Script
The batch job requires JAR files for S3 and PostgreSQL connectivity.

```bash
# 1. Create a directory for dependencies
mkdir -p jars

# 2. Download the required JARs
wget -P jars/ https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.540/aws-java-sdk-bundle-1.12.540.jar
wget -P jars/ https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar
wget -P jars/ https://jdbc.postgresql.org/download/postgresql-42.6.0.jar

# 3. Copy JARs and the batch script to the Spark Master pod
kubectl exec $MASTER_POD -- mkdir -p /tmp/dependencies
kubectl cp jars/aws-java-sdk-bundle-1.12.540.jar $MASTER_POD:/tmp/dependencies/
kubectl cp jars/hadoop-aws-3.3.4.jar $MASTER_POD:/tmp/dependencies/
kubectl cp jars/postgresql-42.6.0.jar $MASTER_POD:/tmp/dependencies/
kubectl cp src/jobs/main.py $MASTER_POD:/tmp/main.py
```

### 6.2. Submit the Batch Job
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
**Success Criterion:** The job is complete when you see log output indicating that data batches are being written to Postgres.

---

## 7. Visualize Data in Grafana

Verify the end-to-end pipeline by connecting Grafana to the PostgreSQL database and visualizing the processed data.

### 7.1. Expose the Grafana Service
Open a **new terminal window** and forward the Grafana port to your local machine.
```bash
kubectl port-forward service/grafana 3000:3000 --address 0.0.0.0
```

### 7.2. Configure Grafana and Visualize
Navigate to `http://localhost:3000` in your web browser.

1.  **Log In:**
    *   **Username:** `admin`
    *   **Password:** `admin`
    *   (You can skip the password change prompt)

2.  **Add PostgreSQL Data Source:**
    *   Navigate to **Connections** > **Data Sources** > **Add data source**.
    *   Select **PostgreSQL**.
    *   Configure the connection with the following settings:
        *   **Host:** `postgres:5432` (This uses Kubernetes' internal DNS)
        *   **Database:** `climate_analysis`
        *   **User:** `admin`
        *   **Password:** `climatechange`
        *   **TLS/SSL Mode:** `disable`
    *   Click **Save & Test**. A confirmation message "Database Connection OK" should appear.

3.  **Create a Visualization:**
    *   Navigate to **Dashboards** > **New Dashboard** > **Add visualization**.
    *   Select the PostgreSQL data source you just configured.
    *   Switch to the **Code** (SQL editor) view and paste the following query:
        ```sql
        SELECT "Year" as time, AVG("Temp_Change") as value 
        FROM climate_analysis 
        GROUP BY "Year" 
        ORDER BY "Year" ASC
        ```
    *   Click **Run Query**. If a time-series graph appears, the entire batch pipeline is working correctly.

---

## 8. Common Operations & Troubleshooting

Here are some useful commands for managing the environment.

| Action                  | Command                                   |
| :---------------------- | :---------------------------------------- |
| **Check Pod Status**    | `kubectl get pods`                        |
| **View Producer Logs**  | `kubectl logs -l app=stream-producer -f`  |
| **Restart Producer**    | `kubectl delete pod -l app=stream-producer` |
| **Stop the Cluster**    | `minikube stop`                           |
| **Delete the Cluster**  | `minikube delete`                         |
| **Reset Docker Env**    | `eval $(minikube docker-env -u)`           |