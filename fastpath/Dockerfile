# Stage 1: Building
FROM python:slim AS builder

RUN apt update && apt install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# Stage 2: Running
FROM python:slim 

RUN apt update && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /install /usr/local
COPY . .

ENV PYTHONPATH=/app
COPY fastpath.conf /etc/ooni/fastpath.conf

EXPOSE 5000

CMD ["python", "./run_fastpath"]
