FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY src/requirements.web.txt /tmp/requirements.web.txt
RUN pip install --no-cache-dir -r /tmp/requirements.web.txt
RUN apt-get update \
    && apt-get install --no-install-recommends -y libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY src ./src
COPY training ./training
RUN mkdir -p /app/uploads /app/previews /app/tiles

EXPOSE 8000
CMD ["uvicorn", "app.web_main:app", "--host", "0.0.0.0", "--port", "8000"]
