FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SONIA_HOST=0.0.0.0 \
    SONIA_PORT=8080

WORKDIR /app

RUN groupadd --gid 1001 sonia \
    && useradd --uid 1001 --gid sonia --no-create-home --shell /usr/sbin/nologin sonia

COPY ["Agente Cobranzas/BACK/pyproject.toml", "Agente Cobranzas/BACK/README.md", "./"]
COPY ["Agente Cobranzas/BACK/src", "./src"]
COPY ["Agente Cobranzas/BACK/prompts", "./prompts"]

RUN pip install --no-cache-dir .

USER 1001:1001

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"]

CMD ["python", "-m", "collections_agent"]
