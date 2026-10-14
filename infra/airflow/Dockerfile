# infra/airflow/Dockerfile
# Custom Airflow image with all project dependencies pre-installed at build time.
# This avoids the _PIP_ADDITIONAL_REQUIREMENTS approach which causes
# pip.ResolutionTooDeep (200000) failures at every container startup.
ARG AIRFLOW_VERSION=2.10.2
FROM apache/airflow:${AIRFLOW_VERSION}

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev git curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

USER airflow

COPY requirements.txt /tmp/airflow-project-requirements.txt

# Install with --no-deps for the larger packages to avoid resolver depth issues,
# then install transitives explicitly via the pinned requirements file.
RUN pip install --no-cache-dir \
    --no-deps \
    dbt-trino==1.8.3 \
    && pip install --no-cache-dir \
    -r /tmp/airflow-project-requirements.txt
