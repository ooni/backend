FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y build-essential

COPY . .

ENV PYTHONPATH=/app

COPY debian/etc/ooni/fastpath.conf /etc/ooni/fastpath.conf

EXPOSE 5000

CMD ["python", "./run_fastpath"]
