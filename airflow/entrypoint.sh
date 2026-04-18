#!/bin/bash
set -e

# --- Run as root: fix Hugging Face cache permissions then re-exec as airflow ---
if [ "$(id -u)" = "0" ]; then
  if [ "$1" != "--as-airflow" ]; then
    echo "Fixing permissions for /opt/airflow/.cache..."
    mkdir -p /opt/airflow/.cache
    chown -R airflow:airflow /opt/airflow/.cache
    exec runuser -u airflow -g airflow -- /bin/bash "$0" --as-airflow
  fi
  shift   # remove --as-airflow from $@
fi

# Clean up any existing PID files and processes (Airflow 3 components)
echo "Cleaning up any existing Airflow processes..."
pkill -f "airflow api-server" || true
pkill -f "airflow dag-processor" || true
pkill -f "airflow triggerer" || true
pkill -f "airflow scheduler" || true
rm -f /opt/airflow/airflow-webserver.pid
rm -f /opt/airflow/airflow-api-server.pid
rm -f /opt/airflow/airflow-scheduler.pid
rm -f /opt/airflow/airflow-dag-processor.pid
rm -f /opt/airflow/airflow-triggerer.pid

# Wait for processes to fully terminate
sleep 2

# 1. Migrate database (Quick Start: airflow db migrate)
echo "Migrating Airflow database..."
airflow db migrate

# 2. Create admin user (FAB auth manager; airflow users create)
echo "Creating admin user..."
airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com \
    --password admin || echo "Admin user already exists"

# 3–6. Start components: run scheduler, dag-processor, triggerer in background;
#      run api-server in FOREGROUND so port 8080 is reliably served and logs are visible.
#      (Daemon api-server in Docker can die silently; see apache/airflow#52270.)
echo "Starting scheduler, dag-processor, triggerer in background..."
airflow scheduler --daemon &
sleep 2
airflow dag-processor --daemon &
sleep 1
airflow triggerer --daemon &
sleep 2

echo "Starting API server on 0.0.0.0:8080 (foreground)..."
exec airflow api-server --host 0.0.0.0 --port 8080