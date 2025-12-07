# Climate Analytics Platform: Real-Time Ingestion Setup (Linux/Minikube)

**Environment:** Ubuntu / Linux (Native or WSL2)
**Orchestration:** Kubernetes (Minikube)
**Architecture:** Lambda (Ingestion Layer implemented)

This guide covers the deployment of the infrastructure and the execution of the **Real-Time Ingestion Pipeline**, where data is streamed from a Python TCP Server, processed by Spark Structured Streaming, and stored in a MinIO Data Lake.

---

## 1. Prerequisites

Ensure you have the following installed:
* **Minikube** & **Kubernetes CLI (kubectl)**
* **Docker**
* **Python 3.9+**
* **Git**

### 1.1. Download JAR Dependencies
Your local project folder must contain a `jars/` directory with the required AWS/Hadoop drivers. If missing, download them:

```bash
mkdir -p jars
wget -P jars/ [https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.540/aws-java-sdk-bundle-1.12.540.jar](https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.540/aws-java-sdk-bundle-1.12.540.jar)
wget -P jars/ [https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar](https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar)
````

-----

## 2\. Clean State (Reset)

If you have run this project before, perform a full cleanup to ensure no stale data (checkpoints/databases) conflicts with the new deployment.

```bash
# 1. Delete all K8s resources
kubectl delete -f k8s/deployment.yml

# 2. Delete Persistent Volume Claims (CRITICAL for cleaning MinIO/Postgres)
kubectl delete pvc --all

# 3. Verify cleanup (Should show "No resources found")
kubectl get all
```

-----

## 3\. Build & Deploy Infrastructure

### 3.1. Build Docker Image

We need to build the image inside Minikube's Docker daemon so the cluster can access it.

```bash
# 1. Point shell to Minikube's Docker environment
eval $(minikube -p minikube docker-env)

# 2. Build the image (Contains the Producer and Utils)
docker build -t climate-ingestion:vfinal -f Dockerfile.ingestion .
```

### 3.2. Deploy Kubernetes Manifests

```bash
# Apply the configuration
kubectl apply -f k8s/deployment.yml

# Wait for pods to be ready (Press Ctrl+C when all are 'Running')
kubectl get pods -w
```

-----

## 4\. Initialization & Configuration

### 4.1. Inject Spark Dependencies & Code

We need to copy the AWS/S3 drivers and the streaming job script into the Spark Master pod.

```bash
# 1. Export Pod Name and IP
export MASTER_POD=$(kubectl get pods -l app=spark-master -o jsonpath="{.items[0].metadata.name}")
export MASTER_IP=$(kubectl get pods -l app=spark-master -o jsonpath="{.items[0].status.podIP}")

echo "Targeting Master: $MASTER_POD | IP: $MASTER_IP"

# 2. Create dependencies folder inside the Pod
kubectl exec $MASTER_POD -- mkdir -p /tmp/dependencies

# 3. Inject JARs from your local 'jars/' folder
kubectl cp jars/aws-java-sdk-bundle-1.12.540.jar $MASTER_POD:/tmp/dependencies/aws-java-sdk-bundle-1.12.540.jar
kubectl cp jars/hadoop-aws-3.3.4.jar $MASTER_POD:/tmp/dependencies/hadoop-aws-3.3.4.jar

# 4. Upload the Streaming Job Script
kubectl cp src/jobs/streaming_job.py $MASTER_POD:/tmp/streaming_job.py
```

-----

## 5\. Execute Real-Time Ingestion

Launch the Spark Structured Streaming job. This job connects to the socket stream (port 9999), splits the data by type (Temperature vs Emissions), and writes it to MinIO.

```bash
kubectl exec -it $MASTER_POD -- /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --conf spark.driver.host=$MASTER_IP \
  --conf spark.driver.bindAddress=0.0.0.0 \
  --conf spark.executor.memory=512m \
  --conf spark.driver.memory=512m \
  --conf spark.cores.max=1 \
  --jars /tmp/dependencies/aws-java-sdk-bundle-1.12.540.jar,/tmp/dependencies/hadoop-aws-3.3.4.jar \
  /tmp/streaming_job.py
```

> **Note:** Keep this terminal open to monitor the logs.

-----

## 6\. Verification

Verify that data is successfully arriving in the Data Lake.

### 6.1. Access MinIO Console

Open a **new terminal window** and run:

```bash
kubectl port-forward service/minio 9001:9001
```

### 6.2. Browser Check

1.  Open your browser to: [http://localhost:9001](https://www.google.com/search?q=http://localhost:9001)
2.  **Credentials:** User: `minioadmin` | Pass: `minioadmin`
3.  Navigate to **Buckets** \> **raw-data**.

**Success Criteria:**
You should see two distinct folders being populated with CSV files:

  *  **`temperature/`** (Contains Temperature data)
  *  **`emissions/`** (Contains CO2/CH4/N2O data)

-----

## 7\. Troubleshooting (If streams are empty)

If files are created but remain empty (0 bytes):

1.  **Clear Checkpoints:**
    Access MinIO browser, go to `raw-data` and delete the `checkpoints` folder. Spark cannot resume from a checkpoint if the socket source was reset.

2.  **Restart Producer:**
    Restart the python server to ensure it is sending data from the beginning.

    ```bash
    kubectl rollout restart deployment/stream-producer
    ```

3.  **Restart Spark Job:**
    Run the `spark-submit` command (Section 5) again.

<!-- end list -->

