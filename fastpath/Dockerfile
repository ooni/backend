# Stage 1: Building
FROM python:3.13.3-slim-bookworm AS builder

RUN apt update && apt install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/lib/fastpath
RUN chmod 777 /var/lib/fastpath

WORKDIR /app

COPY requirements.txt .

RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# Stage 2: Running
FROM python:3.13.3-slim-bookworm 

RUN apt update && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /install /usr/local
COPY . .

ENV PYTHONPATH=/app
COPY fastpath.conf /etc/ooni/fastpath.conf


CMD ["python", "/app/run_fastpath", "--write-to-disk"]
