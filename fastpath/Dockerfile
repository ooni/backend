FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY debian/etc/ooni/fastpath.conf /etc/ooni/fastpath.conf

EXPOSE 5000

CMD ["python", "./run_fastpath"]
