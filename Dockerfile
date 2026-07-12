FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/app/
COPY web/ /app/web/
# mcp_http.py and mcp_server.py live at repo root
COPY mcp_http.py /app/
COPY mcp_server.py /app/

# /data is the persistent volume — SQLite lives here
RUN mkdir -p /data

EXPOSE 8080

CMD ["uvicorn", "app.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
