FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p outputs/briefs outputs/alerts outputs/ai logs storage credentials assets

HEALTHCHECK --interval=5m --timeout=30s --retries=3 \
    CMD python -c "from app.config import get_settings; get_settings()" || exit 1

CMD ["python", "-m", "app.main", "scheduler"]
