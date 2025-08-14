# Stage 1: Building
FROM python:3.12-slim-bookworm AS builder

RUN apt update && apt install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# Stage 2: Running
FROM python:3.12-slim-bookworm 

RUN useradd -m -u 1420 -s /bin/bash fastpath

RUN apt update && rm -rf /var/lib/apt/lists/*

WORKDIR /home/fastpath/app

COPY --from=builder /install /usr/local
COPY . .

ENV PYTHONPATH=/home/fastpath/app
COPY fastpath.conf /etc/ooni/fastpath.conf

# Set up directories required by the fastpath
RUN mkdir -p /var/lib/fastpath
RUN chown -R fastpath:fastpath /var/lib/fastpath
RUN chown -R fastpath:fastpath /etc/ooni/
RUN mkdir -p /var/lib/ooniapi/
RUN chown -R fastpath:fastpath /var/lib/ooniapi/ 


USER fastpath
CMD ["python", "/home/fastpath/app/run_fastpath", "--write-to-disk"]
