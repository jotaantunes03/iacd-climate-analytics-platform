# Global Climate Change Analytics Platform

## Project Objective
This project aims to design and implement an end-to-end data engineering pipeline for comprehensive analysis of global climate change patterns using containerized distributed systems.

## Team
* João Antunes 2021220964
* Gabriel Pinto 2021220925
* José Cunha 2021223719

## Architecture
The pipeline leverages:
* **Ingestion:** Spark Streaming
* **Storage:** MinIO (Raw) & PostgreSQL (Structured)
* **Processing:** Apache Spark
* **Visualization:** Grafana

## Course
Advanced Infrastructures for Data Science (IACD) - MIACD 2025/2026
University of Coimbra

---

## Infrastructure Implementation Strategy

The infrastructure was built following a **step-by-step engineering approach** to ensure modularity, scalability, and data persistence. Below are the key implementation decisions made during the setup phase:

### 1. Directory Structure & Persistence
* **What we did:** Implemented a structured file system separating `data/` (storage) from `workspace/` (code).
* **Why:**
    * **Persistence:** Volumes mapped to `data/minio` and `data/postgres` ensure that raw data and processed metrics survive container restarts.
    * **Hot-Swapping:** The `workspace/` volume allows the team to develop Python scripts locally and execute them immediately inside the Spark container without rebuilding Docker images.

### 2. Dependency Injection (Custom Drivers)
* **What we did:** Manually injected specific Java JARs (`hadoop-aws`, `aws-java-sdk-bundle`, `postgresql`) into the Spark classpath via a mounted `jars/` volume.
* **Why:** By default, Spark cannot communicate with S3-compatible storage or Relational Databases.
    * `hadoop-aws` & `aws-sdk`: Enable the `s3a://` protocol for MinIO integration.
    * `postgresql-jdbc`: Enables writing DataFrames directly to the SQL database.

### 3. Container Orchestration & Networking
* **What we did:** Defined a `docker-compose.yml` with a custom bridge network (`climate-net`).
* **Why:** This ensures **Service Discovery** (containers communicate via hostnames like `spark-master` or `postgres`) and provides network isolation from the host machine.

### 4. Security Configuration
* **What we did:** Centralized credentials in a `.env` file.
* **Why:** To adhere to security best practices, sensitive data (DB passwords, MinIO keys) are decoupled from the codebase.

---

## Infrastructure Setup (Docker)

This project uses **Docker Compose** to orchestrate the distributed environment. The setup is designed to be cross-platform (compatible with macOS Apple Silicon, Windows, and Linux) by using official Apache Spark images.

### Prerequisites
* Docker Desktop installed and running.

### Quick Start
To start the entire platform, run the following command in the project root:

```bash
docker-compose up -d