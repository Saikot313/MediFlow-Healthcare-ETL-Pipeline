
FROM apache/airflow:2.10.5-python3.11

COPY docker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    -c "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.11.txt"
