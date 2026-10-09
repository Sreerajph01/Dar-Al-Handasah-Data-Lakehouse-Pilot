FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    uvicorn[standard]==0.30.6 \
    opensearch-py==2.7.1 \
    httpx==0.27.2 \
    pydantic==2.9.2 \
    python-jose[cryptography]==3.3.0 \
    python-multipart==0.0.12 \
    aiofiles==24.1.0 \
    ezdxf==1.3.4

COPY . /app/

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
