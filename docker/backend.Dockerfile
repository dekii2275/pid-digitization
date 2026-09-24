FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg libgl1 libglib2.0-0 unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY src/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1+cpu torchvision==0.20.1+cpu \
    && pip install -r /tmp/requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src

RUN mkdir -p /app/uploads /app/artifacts /app/models

EXPOSE 8000
