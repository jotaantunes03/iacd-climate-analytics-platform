<#
.SYNOPSIS
    Automates the deployment and execution of the Climate Analytics Platform on Windows.

.DESCRIPTION
    This script performs the following actions (aligned with SETUP_WINDOWS.md):
    1. Checks and downloads required JAR dependencies.
    2. Cleans up existing Kubernetes resources and PVCs.
    3. Builds the custom Docker image for the Producer.
    4. Deploys Kubernetes infrastructure.
    5. Initializes MinIO buckets.
    6. Injects dependencies into the Spark Master.
    7. Spawns 4 separate PowerShell windows for jobs and port-forwarding.
    8. MONITORS execution and performs FULL CLEANUP upon exit.

.NOTES
    Prerequisites: Docker Desktop (K8s enabled), kubectl, git.
    Run this script from the project root.
#>

$ErrorActionPreference = "Stop"

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "   CLIMATE ANALYTICS PLATFORM - AUTO LAUNCHER       " -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan

# --- 0. Dependency Check ---
Write-Host "`n[0/9] Checking Dependencies..." -ForegroundColor Yellow
$jarsDir = ".\jars"
if (-not (Test-Path $jarsDir)) {
    Write-Host "Creating 'jars' directory..." -ForegroundColor Gray
    New-Item -ItemType Directory -Path $jarsDir | Out-Null
}

$dependencies = @{
    "postgresql-42.6.0.jar" = "https://jdbc.postgresql.org/download/postgresql-42.6.0.jar"
    "hadoop-aws-3.3.4.jar" = "https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar"
    "aws-java-sdk-bundle-1.12.540.jar" = "https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.540/aws-java-sdk-bundle-1.12.540.jar"
}

foreach ($jar in $dependencies.Keys) {
    $jarPath = Join-Path $jarsDir $jar
    if (-not (Test-Path $jarPath)) {
        $url = $dependencies[$jar]
        Write-Host "Downloading $jar..." -ForegroundColor Cyan
        try {
            Invoke-WebRequest -Uri $url -OutFile $jarPath
            Write-Host "Download complete." -ForegroundColor Green
        } catch {
            Write-Error "Failed to download $jar from $url. Please download it manually and place it in the 'jars' folder."
            exit 1
        }
    } else {
        Write-Host "Found $jar." -ForegroundColor Gray
    }
}

# --- 1. Context Setup ---
Write-Host "`n[1/9] Setting Kubernetes Context..." -ForegroundColor Yellow
try {
    kubectl config use-context docker-desktop | Out-Null
    Write-Host "Context set to 'docker-desktop'." -ForegroundColor Gray
} catch {
    Write-Warning "Could not switch to 'docker-desktop' context. Using current context."
}

# --- 2. Environment Cleanup (Section 2) ---
Write-Host "`n[2/9] Cleaning Environment..." -ForegroundColor Yellow
Write-Host "Deleting existing deployments and services..." -ForegroundColor Gray
kubectl delete -f k8s/deployment.yml --ignore-not-found

Write-Host "Deleting Persistent Volume Claims (PVCs)..." -ForegroundColor Gray
kubectl delete pvc --all --ignore-not-found

Write-Host "Waiting 10 seconds for resources to terminate..." -ForegroundColor Gray
Start-Sleep -Seconds 10

# --- 3. Build Docker Image (Section 3.1) ---
Write-Host "`n[3/9] Building Docker Image..." -ForegroundColor Yellow
Write-Host "Building 'climate-ingestion:vfinal'..." -ForegroundColor Gray
docker build -t climate-ingestion:vfinal -f Dockerfile.ingestion .

if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker build failed. Please check Dockerfile.ingestion."
}

# --- 4. Infrastructure Deployment (Section 3.2) ---
Write-Host "`n[4/9] Deploying Infrastructure..." -ForegroundColor Yellow
kubectl apply -f k8s/deployment.yml

# --- 5. Wait for Pods (Section 3.3) ---
Write-Host "`n[5/9] Waiting for Pods to Initialize..." -ForegroundColor Yellow
Write-Host "This ensures Spark, MinIO, and the Producer are ready." -ForegroundColor Gray

$podsReady = $false
while (-not $podsReady) {
    # Check if all pods are Running or Completed
    $phases = kubectl get pods -o jsonpath="{.items[*].status.phase}"
    if ($phases -match "Pending" -or $phases -match "ContainerCreating" -or $phases -match "Terminating") {
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 3
    } else {
        $podsReady = $true
        Write-Host "`nAll Pods appear to be running." -ForegroundColor Green
    }
}
# Extra buffer for services to bind
Start-Sleep -Seconds 20

# --- 6. Configuration & Initialization (Section 4.1) ---
Write-Host "`n[6/9] Configuring Services..." -ForegroundColor Yellow

# Get Spark Master Details
$MASTER_POD = kubectl get pods -l app=spark-master -o jsonpath="{.items[0].metadata.name}"
$MASTER_IP = kubectl get pods -l app=spark-master -o jsonpath="{.items[0].status.podIP}"

if ([string]::IsNullOrWhiteSpace($MASTER_POD)) {
    Write-Error "Could not find Spark Master pod. Exiting."
}

Write-Host "Targeting Spark Master: $MASTER_POD ($MASTER_IP)" -ForegroundColor Gray

# Initialize MinIO Buckets
Write-Host "Initializing MinIO Buckets..." -ForegroundColor Gray
# Wait specifically for producer pod to be ready to exec
kubectl wait --for=condition=ready pod -l app=stream-producer --timeout=60s | Out-Null
kubectl exec deployment/stream-producer -- python src/ingestion/init_minio.py

# --- 7. Inject Dependencies (Section 4.2) ---
Write-Host "`n[7/9] Injecting Dependencies into Spark Master..." -ForegroundColor Yellow

# Create directory
kubectl exec $MASTER_POD -- mkdir -p /tmp/dependencies

# Copy JARs
Write-Host "Copying JARs..." -ForegroundColor Gray
kubectl cp jars/aws-java-sdk-bundle-1.12.540.jar "$($MASTER_POD):/tmp/dependencies/aws-java-sdk-bundle-1.12.540.jar"
kubectl cp jars/hadoop-aws-3.3.4.jar "$($MASTER_POD):/tmp/dependencies/hadoop-aws-3.3.4.jar"
kubectl cp jars/postgresql-42.6.0.jar "$($MASTER_POD):/tmp/dependencies/postgresql-42.6.0.jar"

# Copy Scripts
Write-Host "Copying Python Scripts..." -ForegroundColor Gray
kubectl cp src/jobs/streaming_job.py "$($MASTER_POD):/tmp/streaming_job.py"
kubectl cp src/jobs/main.py "$($MASTER_POD):/tmp/main.py"

# --- 8. Launching Streaming Job (Section 5) ---
Write-Host "`n[8/9] Starting Real-Time Ingestion..." -ForegroundColor Yellow

# Window 1: Streaming Job
$cmdStream = "kubectl exec -it $MASTER_POD -- /opt/spark/bin/spark-submit --master spark://spark-master:7077 --conf spark.driver.host=$MASTER_IP --conf spark.driver.bindAddress=0.0.0.0 --conf spark.executor.memory=512m --conf spark.driver.memory=512m --conf spark.cores.max=1 --jars /tmp/dependencies/aws-java-sdk-bundle-1.12.540.jar,/tmp/dependencies/hadoop-aws-3.3.4.jar /tmp/streaming_job.py"
$argsStream = "-NoExit", "-Command", "& { `$host.ui.RawUI.WindowTitle = 'Window 1: Ingestion (Streaming Job)'; Write-Host 'Starting Streaming Job...'; $cmdStream }"
# Capture process for cleanup
$pStream = Start-Process powershell -ArgumentList $argsStream -PassThru

# --- 9. Waiting for Data & Launching Remaining Jobs ---
Write-Host "`n[9/9] Waiting for Data & Spawning Windows..." -ForegroundColor Yellow
Write-Host "Waiting 60 seconds for the Streaming Job to generate data..." -ForegroundColor Cyan

# Wait loop
for ($i = 60; $i -gt 0; $i--) {
    Write-Host -NoNewline "`rStarting Batch Job in $i seconds...   "
    Start-Sleep -Seconds 1
}
Write-Host "`nLaunching Batch Job and Dashboards!" -ForegroundColor Green

# Window 2: Batch Job (Section 6)
$cmdBatch = "kubectl exec -it $MASTER_POD -- /opt/spark/bin/spark-submit --master spark://spark-master:7077 --conf spark.driver.host=$MASTER_IP --conf spark.driver.bindAddress=0.0.0.0 --conf spark.executor.memory=512m --conf spark.driver.memory=512m --conf spark.cores.max=1 --jars /tmp/dependencies/aws-java-sdk-bundle-1.12.540.jar,/tmp/dependencies/hadoop-aws-3.3.4.jar,/tmp/dependencies/postgresql-42.6.0.jar /tmp/main.py"
$argsBatch = "-NoExit", "-Command", "& { `$host.ui.RawUI.WindowTitle = 'Window 2: Processing (Batch Job)'; Write-Host 'Starting Batch Job...'; $cmdBatch }"
$pBatch = Start-Process powershell -ArgumentList $argsBatch -PassThru

# Window 3: MinIO (Section 7.1)
$cmdMinio = "kubectl port-forward service/minio 9001:9001"
$argsMinio = "-NoExit", "-Command", "& { `$host.ui.RawUI.WindowTitle = 'Window 3: MinIO Console'; Write-Host 'Exposing MinIO on port 9001...'; $cmdMinio }"
$pMinio = Start-Process powershell -ArgumentList $argsMinio -PassThru

# Window 4: Grafana (Section 7.2)
$cmdGrafana = "kubectl port-forward service/grafana 3000:3000"
$argsGrafana = "-NoExit", "-Command", "& { `$host.ui.RawUI.WindowTitle = 'Window 4: Grafana Dashboard'; Write-Host 'Exposing Grafana on port 3000...'; $cmdGrafana }"
$pGrafana = Start-Process powershell -ArgumentList $argsGrafana -PassThru

# --- Interactive Monitor & Cleanup ---
Write-Host "`n[SUCCESS] System is Running!" -ForegroundColor Green
Write-Host "----------------------------------------------------"
Write-Host "1. Ingestion Window: Watch the micro-batches processing."
Write-Host "2. Processing Window: Watch the batch ETL job."
Write-Host "3. MinIO: http://localhost:9001 (User/Pass: minioadmin)"
Write-Host "4. Grafana: http://localhost:3000 (User/Pass: admin)"
Write-Host "----------------------------------------------------"
Write-Host ">> Press 'Q' to STOP all services and CLEAN UP the cluster <<" -ForegroundColor Cyan

while ($true) {
    if ($Host.UI.RawUI.KeyAvailable) {
        $key = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        if ($key.Character -eq 'q' -or $key.Character -eq 'Q') {
            break
        }
    }
    Start-Sleep -Milliseconds 500
}

# --- Cleanup Logic ---
Write-Host "`n[SHUTDOWN] Stopping external windows..." -ForegroundColor Yellow

# Função auxiliar para matar a árvore de processos (Janela + Comando interno)
function Kill-Tree {
    param([System.Diagnostics.Process]$proc)
    if ($proc -and -not $proc.HasExited) {
        Write-Host "Killing process tree for PID: $($proc.Id)..." -ForegroundColor Gray
        # /T = Mata processos filhos (kubectl), /F = Força bruta
        taskkill /PID $proc.Id /T /F | Out-Null
    }
}

# Matar as janelas usando a função robusta
Kill-Tree $pStream
Kill-Tree $pBatch
Kill-Tree $pMinio
Kill-Tree $pGrafana

# Garantia extra: Matar processos orfãos do kubectl que possam ter sobrado
Write-Host "Ensuring all kubectl port-forwards are dead..." -ForegroundColor Gray
Get-Process kubectl -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# Give a moment for processes to die
Start-Sleep -Seconds 2

Write-Host "`n[CLEANUP] Removing Kubernetes resources..." -ForegroundColor Yellow
kubectl delete -f k8s/deployment.yml --ignore-not-found
kubectl delete pvc --all --ignore-not-found

Write-Host "`n[DONE] Environment is clean. Goodbye!" -ForegroundColor Green
Start-Sleep -Seconds 3
