FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
    torch==2.5.1+cpu torchvision==0.20.1+cpu
COPY src/requirements.web.txt src/requirements.symbol-db.txt src/constraints.web.txt /tmp/
RUN pip install --no-cache-dir -c /tmp/constraints.web.txt -r /tmp/requirements.web.txt -r /tmp/requirements.symbol-db.txt \
    && pip check

COPY src/requirements.storage.txt /tmp/
RUN pip install --no-cache-dir -c /tmp/constraints.web.txt -r /tmp/requirements.storage.txt && pip check

COPY src ./src
COPY training ./training
COPY tests ./tests
RUN mkdir -p /app/uploads /app/previews /app/tiles

EXPOSE 8000
CMD ["uvicorn", "app.web_main:app", "--host", "0.0.0.0", "--port", "8000"]
