FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && apt-get clean

COPY . /app

RUN pip install --no-cache-dir flask aiohttp

EXPOSE 5000

CMD ["python", "leader.py"]
