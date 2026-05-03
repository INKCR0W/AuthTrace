FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY docker/start.sh ./docker/start.sh

RUN pip install --no-cache-dir . && chmod +x /app/docker/start.sh

EXPOSE 8000

CMD ["/app/docker/start.sh"]
