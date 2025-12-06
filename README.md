# Global Climate Change Analytics Platform

## Project Objective
This project aims to design and implement an end-to-end data engineering pipeline for comprehensive analysis of global climate change patterns using containerized distributed systems.

## Team
* João Antunes 2021220964
* Gabriel Pinto 2021220925
* José Cunha 2021223719

## Course
Advanced Infrastructures for Data Science (IACD) - MIACD 2025/2026
University of Coimbra

---

## Architecture
The pipeline leverages:
* **Ingestion:** Python Scripts (Local -> MinIO)
* **Storage:** MinIO (Raw Data / Object Storage) & PostgreSQL (Structured Data)
* **Processing:** Apache Spark (Distributed Computing)
* **Visualization:** Grafana

---

## Infrastructure Implementation Strategy

The infrastructure was built following a **step-by-step engineering approach** to ensure modularity, scalability, and data persistence. Below are the key implementation decisions:

### 1. Persistence & Storage
* **Decoupled Storage:** We use **MinIO** for raw CSV data (simulating an AWS S3 Data Lake) and **PostgreSQL** for the final processed metrics.
* **Kubernetes PVCs:** `PersistentVolumeClaims` were implemented to ensure data survives pod restarts.

### 2. Dependency Injection (The "Jars" Challenge)
* **Problem:** The official Apache Spark image does not include drivers for S3 (`hadoop-aws`, `aws-java-sdk`) or PostgreSQL.
* **Solution:** We manually inject these JARs into the Spark containers. In the Kubernetes workflow, we copy them to `/tmp/dependencies` to avoid permission issues and reference them during job submission.

### 3. Networking & Resource Management
* **Memory Limits:** To prevent Kubernetes from killing containers (OOMKilled), we strictly limited Spark Executors to `512m` RAM, ensuring they fit within the `1Gi` container limit.
* **Service Discovery:** Internal components communicate via K8s Service names (e.g., `postgres:5432`), while external access (local machine) uses `kubectl port-forward`.

### 4. Security Configuration
* **What we did:** Centralized credentials using Kubernetes `Secrets`.
* **Why:** To adhere to security best practices, sensitive data (DB passwords, MinIO keys) are decoupled from the codebase.

---

## 🚀 Part 1: Docker Compose (Local Dev)

This project uses **Docker Compose** for local development and testing.

### Quick Start
To start the entire platform locally:

```bash
docker-compose up -d
````

-----

## 🚀 Part 2: Kubernetes (Production Simulation)

In addition to Docker Compose, we implemented a full **Kubernetes** configuration (tested with Minikube) to demonstrate orchestration in a distributed environment.

### Why Kubernetes?

  * **Orchestration:** Manages the lifecycle of Spark Master, Workers, Database, and Storage.
  * **High Availability:** Self-healing pods via `Deployments`.
  * **Best Practices:** Separation of concerns using `Secrets`, `ConfigMaps`, and `Services` (ClusterIP/NodePort).

### 1\. Prerequisites

  * **Minikube** installed and running.
  * **Python 3.11+** (with virtual environment active).
  * **Library Dependencies:**
    ```bash
    pip install minio python-dotenv
    ```

### 2\. Deploy Infrastructure

Apply the deployment configuration to create Services, Deployments, PVCs, and Secrets.

```bash
kubectl apply -f k8s/deployment.yaml
```

Wait until all pods are `Running`:

```bash
kubectl get pods -w
```

-----

### 3\. Data Ingestion (Local to Cluster)

Since the MinIO service runs inside the cluster, we must open a tunnel to upload the raw data from our local machine.

**Step 3.1: Open Tunnel (Terminal A)**

```bash
kubectl port-forward service/minio 9000:9000
```

**Step 3.2: Run Ingestion Scripts (Terminal B)**
With the tunnel open, run the python scripts to create buckets and upload CSVs.

```bash
# Initialize Buckets
python src/ingestion/init_minio.py

# Upload Data
python src/ingestion/ingest_data.py
```

*Output should confirm: "enviado com sucesso".*

-----

### 4\. Preparation for Spark Job

We need to sync the Python code and Java dependencies to the Spark Master pod.

**Step 4.1: Update ConfigMap with Code**

```bash
kubectl create configmap spark-jobs --from-file=src/jobs/main.py --dry-run=client -o yaml | kubectl apply -f -
```

**Step 4.2: Inject JAR Dependencies**
Get the Master Pod name and copy the necessary JARs to a temporary writable directory.

```bash
MASTER_POD=$(kubectl get pods -l app=spark-master -o jsonpath="{.items[0].metadata.name}")

# Create destination folder
kubectl exec $MASTER_POD -- mkdir -p /tmp/dependencies

# Copy JARs from local 'jars/' folder to Pod
kubectl cp jars/aws-java-sdk-bundle-1.12.540.jar $MASTER_POD:/tmp/dependencies/aws-java-sdk-bundle-1.12.540.jar
kubectl cp jars/hadoop-aws-3.3.4.jar $MASTER_POD:/tmp/dependencies/hadoop-aws-3.3.4.jar
kubectl cp jars/postgresql-42.6.0.jar $MASTER_POD:/tmp/dependencies/postgresql-42.6.0.jar
```

-----

### 5\. Execute Spark Job (The "Networking Hack")

To allow the Spark Workers to communicate back to the Driver (Master) inside Kubernetes, we must explicitly tell the Driver its own Pod IP. Without this, the job hangs due to networking restrictions.

**Step 5.1: Get Master IP**

```bash
MASTER_POD_IP=$(kubectl get pods -l app=spark-master -o jsonpath="{.items[0].status.podIP}")
echo "Master IP: $MASTER_POD_IP"
```

**Step 5.2: Submit the Job**
Run the following command. Note the memory constraints (`512m`) to fit our cluster resources and the `driver.host` configuration.

```bash
kubectl exec -it deployment/spark-master -- /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --conf spark.driver.host=$MASTER_POD_IP \
  --conf spark.driver.bindAddress=0.0.0.0 \
  --conf spark.executor.memory=512m \
  --conf spark.driver.memory=512m \
  --conf spark.cores.max=1 \
  --jars /tmp/dependencies/aws-java-sdk-bundle-1.12.540.jar,/tmp/dependencies/hadoop-aws-3.3.4.jar,/tmp/dependencies/postgresql-42.6.0.jar \
  /opt/spark/jobs/main.py
```

*Expected Output:*

> `>>> SUCESSO! Job terminado.`

-----

### 6\. Verify Results & Visualization

#### 6.1 Check Database

Verify if data was successfully written to PostgreSQL.

```bash
# Open Tunnel
kubectl port-forward service/postgres 5432:5432

# Check Row Count
psql -h localhost -p 5432 -U admin -d climate_analysis -c "SELECT COUNT(*) FROM climate_analysis;"
```

#### 6.2 Grafana Dashboard

Visualize the data trends.

1.  **Open Tunnel:**
    ```bash
    kubectl port-forward service/grafana 3000:3000
    ```
2.  **Access:** [http://localhost:3000](https://www.google.com/search?q=http://localhost:3000) (User: `admin` / Pass: `admin`)
3.  **Configure Data Source:**
      * **Type:** PostgreSQL
      * **Host:** `postgres:5432` (Internal K8s DNS)
      * **Database:** `climate_analysis`
      * **User/Pass:** `admin` / `climatechange`
      * **SSL:** Disable
4.  **Create Query:**
    ```sql
    SELECT "Year" as time, AVG("Temp_Change") as value 
    FROM climate_analysis 
    GROUP BY "Year" 
    ORDER BY "Year" ASC
    ```

-----

### 7\. Cleanup

To stop the cluster and remove resources:

```bash
kubectl delete -f k8s/deployment.yaml
```

-----

## 🔧 Technical Challenges & Solutions

Migrating from a local Docker Compose environment to a distributed Kubernetes cluster introduced several engineering challenges. Below is a summary of the critical issues encountered and the architectural solutions implemented.

### 1\. Memory Management (OOMKilled)

  * **The Issue:** Spark Workers were crashing immediately upon startup (`CrashLoopBackOff`), with Kubernetes reporting `OOMKilled` (Out of Memory).
  * **Root Cause:** The JVM Heap memory requested by Spark (`2GB`) exceeded the strict container limit defined in the Kubernetes manifest (`1Gi`). The Linux kernel terminated the process to protect the node.
  * **Solution:** We tuned the JVM parameters to fit the container constraints. We reduced `SPARK_WORKER_MEMORY` to `800m` and strictly limited the executor memory in the job submission (`--conf spark.executor.memory=512m`), leaving a safety buffer for the container OS overhead.

### 2\. Dependency Management (Missing Classpaths)

  * **The Issue:** Spark jobs failed with `java.lang.ClassNotFoundException: org.apache.hadoop.fs.s3a.S3AFileSystem`.
  * **Root Cause:** The official Apache Spark Docker image is lightweight and lacks the necessary JAR libraries to communicate with S3-compatible storage (MinIO) and PostgreSQL.
  * **Solution:** We implemented a manual **Dependency Injection** strategy. Instead of building a custom heavy image, we copy the required JARs (`hadoop-aws`, `aws-java-sdk`, `postgresql`) into the pods at runtime (`/tmp/dependencies`) and reference them dynamically during `spark-submit`.

### 3\. Network Address Translation (NAT) & Spark Callbacks

  * **The Issue:** Jobs were submitted successfully but hung indefinitely with the warning: `Initial job has not accepted any resources`.
  * **Root Cause:** Spark uses a random port mechanism for the Driver-Executor communication. When running inside Kubernetes, the Worker tried to connect back to the Driver via the Service hostname, but the specific dynamic port was blocked by the Kubernetes Service abstraction.
  * **Solution:** We used **Headless IP Injection**. We retrieved the specific Pod IP of the Master node (`kubectl get pod ...`) and forced the Spark Driver to advertise this specific IP (`--conf spark.driver.host=$IP`) instead of the hostname, enabling direct Pod-to-Pod communication.

### 4\. Service Discovery (DNS Resolution)

  * **The Issue:** Connection refused errors when Python scripts tried to access `localhost:5432` or `localhost:9000` from within the cluster.
  * **Root Cause:** In a local development environment, `localhost` works because ports are mapped to the host. In Kubernetes, each pod is an isolated network entity; `localhost` refers only to the pod itself.
  * **Solution:** We utilized **Kubernetes Internal DNS**. All connection strings were updated to use the Service names defined in our deployment (`postgres:5432`, `minio:9000`), allowing Kubernetes to automatically resolve the correct ClusterIPs.

-----

## 🛠️ Appendix: Kubernetes Cheat Sheet

Useful commands used during the development and debugging of this project.

**Networking & IPs**

```bash
# View all Pod IPs and Nodes
kubectl get pods -o wide

# Get only the internal IP of the Spark Master (useful for scripts)
kubectl get pods -l app=spark-master -o jsonpath="{.items[0].status.podIP}"
```

**Debugging & Logs**

```bash
# Watch logs of a specific pod in real-time
kubectl logs -f <pod_name>

# View logs from the previous instance (if the pod crashed/restarted)
kubectl logs <pod_name> --previous

# Inspect pod details (Events, Errors, OOMKilled status)
kubectl describe pod <pod_name>
```

**Access & Files**

```bash
# Open a shell inside a container
kubectl exec -it <pod_name> -- /bin/bash

# Copy files from local machine to a pod
kubectl cp ./localfile.txt <pod_name>:/tmp/remotefile.txt
```

**Management**

```bash
# Restart a deployment (useful after updating configmaps)
kubectl rollout restart deployment/spark-worker

# Delete a specific pod (Kubernetes will recreate it automatically)
kubectl delete pod <pod_name>
```

```
```