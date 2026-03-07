FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

ARG PORT=8000
ENV PORT=${PORT}
EXPOSE ${PORT}

CMD ["python", "server.py", "--sse"]
