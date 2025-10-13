FROM python:3.10-slim

WORKDIR /app


COPY server.py .
COPY client.py .

EXPOSE 8080

CMD ["python", "server.py", "/app/content", "8080"]