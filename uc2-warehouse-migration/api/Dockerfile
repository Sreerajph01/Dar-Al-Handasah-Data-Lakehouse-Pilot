FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    uvicorn[standard]==0.30.6 \
    trino==0.329.0 \
    pydantic==2.9.2 \
    httpx==0.27.2 \
    python-jose[cryptography]==3.3.0 \
    python-multipart==0.0.12

COPY . /app/

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
