FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SONIA_HOST=0.0.0.0 \
    SONIA_PORT=8080 \
    SONIA_BI_DATASET_PATH=/data/bi

WORKDIR /app

RUN groupadd --gid 1001 sonia \
    && useradd --uid 1001 --gid sonia --no-create-home --shell /usr/sbin/nologin sonia

COPY BACK/pyproject.toml BACK/README.md ./
COPY BACK/src ./src
COPY BACK/prompts ./prompts

RUN pip install --no-cache-dir .

USER 1001:1001

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"]

CMD ["python", "-m", "bi_agent"]
