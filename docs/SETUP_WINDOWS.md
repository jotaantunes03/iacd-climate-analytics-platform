# Setup Guide: Climate Analytics Platform on Windows

This guide details the steps to deploy and run the real-time climate analytics pipeline on Windows using Docker Desktop with Kubernetes.

**Target Environment:**
*   **OS:** Windows with PowerShell
*   **Orchestration:** Kubernetes (via Docker Desktop)
*   **Container Engine:** Docker

---

## 1. Prerequisites

Before you begin, ensure your environment is correctly configured:
*   **Docker Desktop:** Installed and running with the Kubernetes engine enabled.
*   **PowerShell:** Use a PowerShell terminal for all commands.
*   **Git:** Git must be installed and available in your system's PATH.
*   **Repository:** Clone the project repository to your local machine.

```powershell
# Clone the specific project branch
git clone https://github.com/jotaantunes03/iacd-climate-analytics-platform.git
cd iacd-climate-analytics-platform
```

---

## 2. Environment Cleanup (Optional)

If you have run this project before, execute the following commands to reset the Kubernetes cluster and remove any persistent data. This prevents conflicts from previous deployments.

```powershell
# 1. Delete all Kubernetes resources defined in the deployment file
kubectl delete -f k8s/deployment.yml

# 2. Delete all Persistent Volume Claims to clear data from MinIO and PostgreSQL
kubectl delete pvc --all

# 3. Verify that all resources have been removed
kubectl get all
# Expected output: "No resources found"
```

---

## 3. Build and Deploy the Infrastructure

This phase builds the custom Docker image for the data producer and deploys all necessary infrastructure components using the Kubernetes manifests.

### 3.1. Build the Docker Image
This image contains the Python server responsible for streaming data.
```powershell
# 1. Ensure kubectl is targeting the Docker Desktop cluster
kubectl config use-context docker-desktop

# 2. Build the Docker image
docker build -t climate-ingestion:vfinal -f Dockerfile.ingestion .
```

### 3.2. Deploy Kubernetes Manifests
Apply the main deployment file to create the Spark cluster, MinIO, PostgreSQL, and the data producer.
```powershell
kubectl apply -f k8s/deployment.yml
```

### 3.3. Monitor Pod Initialization
Wait for all pods to become fully operational before proceeding.
```powershell
# Monitor pod status until all are 'Running' or 'Completed'
echo "Waiting for all pods to initialize..."
kubectl get pods -w
# Press Ctrl+C once all pods are stable.
```

---

## 4. Configure and Initialize Services

With the infrastructure running, you must initialize the MinIO storage buckets and prepare the Spark cluster for job submission.

### 4.1. Initialize MinIO Buckets
Run a script inside the producer pod to create the required `raw-data` bucket in MinIO.
```powershell
kubectl exec -it deployment/stream-producer -- python src/ingestion/init_minio.py
```
**Expected Output:** A confirmation message, such as `[CREATED] Bucket 'raw-data'`.

### 4.2. Prepare Spark for Job Submission
Copy the necessary JAR dependencies and the Python job scripts into the Spark Master pod.

```powershell
# 1. Get the Spark Master pod name and IP address
$MASTER_POD = kubectl get pods -l app=spark-master -o jsonpath="{.items[0].metadata.name}"
$MASTER_IP = kubectl get pods -l app=spark-master -o jsonpath="{.items[0].status.podIP}"
Write-Host "Targeting Spark Master: $MASTER_POD | Internal IP: $MASTER_IP"

# 2. Create a directory for dependencies inside the pod
kubectl exec $MASTER_POD -- mkdir -p /tmp/dependencies

# 3. Copy the required JARs for S3 and PostgreSQL connectivity
# Note: Ensure these JARs exist in a 'jars/' folder in your project root.
kubectl cp jars/aws-java-sdk-bundle-1.12.540.jar "$($MASTER_POD):/tmp/dependencies/"
kubectl cp jars/hadoop-aws-3.3.4.jar "$($MASTER_POD):/tmp/dependencies/"
kubectl cp jars/postgresql-42.6.0.jar "$($MASTER_POD):/tmp/dependencies/"


# 4. Copy the streaming and batch processing scripts to the pod
kubectl cp src/jobs/streaming_job.py "$($MASTER_POD):/tmp/streaming_job.py"
kubectl cp src/jobs/main.py "$($MASTER_POD):/tmp/main.py"
```

---

## 5. Run the Real-Time Streaming Job

This job reads data from the producer, processes it in real-time, and writes it to the `raw-data` bucket in MinIO.

```powershell
# 1. Get the Spark Master pod name and IP address
$MASTER_POD = kubectl get pods -l app=spark-master -o jsonpath="{.items[0].metadata.name}"
$MASTER_IP = kubectl get pods -l app=spark-master -o jsonpath="{.items[0].status.podIP}"
Write-Host "Targeting Spark Master: $MASTER_POD | Internal IP: $MASTER_IP"

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
**Note:** This job runs indefinitely. Keep the terminal open to monitor the stream. You can stop it with `Ctrl+C`.

---

## 6. Run the Historical Batch Processing Job

This one-time job reads all the raw data from MinIO, processes it, and saves the aggregated results to the PostgreSQL database for visualization.

```powershell
# 1. Get the Spark Master pod name and IP address
$MASTER_POD = kubectl get pods -l app=spark-master -o jsonpath="{.items[0].metadata.name}"
$MASTER_IP = kubectl get pods -l app=spark-master -o jsonpath="{.items[0].status.podIP}"
Write-Host "Targeting Spark Master: $MASTER_POD | Internal IP: $MASTER_IP"

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
**Success Criterion:** The job is complete when you see log output indicating that data batches are being written to Postgres.

---

## 7. Verify and Visualize Data

Confirm that the pipeline is working end-to-end by checking the data in MinIO and visualizing it in Grafana.

### 7.1. Verify Data in MinIO
Open a **new PowerShell window** and forward the MinIO service port.
```powershell
kubectl port-forward service/minio 9001:9001
```
Navigate to `http://localhost:9001` in your browser.
*   **Login:** `minioadmin` / `minioadmin`
*   **Verification:** Browse to the `raw-data` bucket. You should see `temperature/` and `emissions/` folders being populated with CSV files.

### 7.2. Visualize in Grafana
Open another **new PowerShell window** and forward the Grafana service port.
```powershell
kubectl port-forward service/grafana 3000:3000
```
Navigate to `http://localhost:3000` in your browser.

1.  **Log In:**
    *   **Username:** `admin`
    *   **Password:** `admin` (you can skip the password change prompt).

2.  **Add PostgreSQL Data Source:**
    *   Go to **Connections** > **Data Sources** > **Add data source** > **PostgreSQL**.
    *   **Host:** `postgres:5432`
    *   **Database:** `climate_analysis`
    *   **User:** `admin`
    *   **Password:** `climatechange`
    *   **TLS/SSL Mode:** `disable`
    *   Click **Save & Test**. A confirmation message "Database Connection OK" should appear.

3.  **Create a Visualization:**
    *   Go to **Dashboards** > **New Dashboard** > **Add visualization**.
    *   Select the PostgreSQL data source.
    *   Switch to the **Code** (SQL editor) view and run the query:
        ```sql
        SELECT "Year" as time, AVG("Temp_Change") as value 
        FROM climate_analysis 
        GROUP BY "Year" 
        ORDER BY "Year" ASC
        ```
    *   Click **Run Query**. If a graph appears, the pipeline is fully functional.

---

## 8. Project Cleanup

To stop the services and release system resources, run the following commands.

```powershell
# 1. Stop the port-forwarding commands by pressing Ctrl+C in their respective terminals.

# 2. Delete all Kubernetes resources
kubectl delete -f k8s/deployment.yml

# 3. (Optional) To fully reset, you can also stop the Kubernetes cluster in Docker Desktop.
```