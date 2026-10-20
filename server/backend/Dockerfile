# The Waterfalls API (FastAPI). Settings come from the environment (see
# app/core/config.py); the skymon archive is mounted read-only at
# SKYMON_ARCHIVE_ROOT.
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/backend
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

USER nobody
EXPOSE 8000
ENTRYPOINT ["uvicorn", "app.main:app"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
