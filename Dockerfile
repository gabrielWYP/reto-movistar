FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SONIA_ENVIRONMENT=production \
    SONIA_HOST=0.0.0.0 \
    SONIA_PORT=8080 \
    SONIA_FRONTEND_DIR=/app/front

WORKDIR /app

RUN groupadd --gid 1001 sonia \
    && useradd --uid 1001 --gid sonia --no-create-home --shell /usr/sbin/nologin sonia

COPY back/pyproject.toml back/README.md LICENSE ./
COPY back/src ./src
COPY front ./front
COPY ["Agente BI/BACK/pyproject.toml", "Agente BI/BACK/README.md", "/opt/bi-agent/"]
COPY ["Agente BI/BACK/src", "/opt/bi-agent/src"]
COPY ["Agente BI/BACK/prompts", "/opt/bi-agent/prompts"]
COPY ["Agente BI/FRONT", "/app/front/bi"]
COPY ["Agente Cobranzas/BACK/pyproject.toml", "Agente Cobranzas/BACK/README.md", "/opt/collections-agent/"]
COPY ["Agente Cobranzas/BACK/src", "/opt/collections-agent/src"]
COPY ["Agente Cobranzas/BACK/prompts", "/opt/collections-agent/prompts"]
COPY ["Agente Cobranzas/FRONT/index.html", "/app/front/agents/collections/index.html"]
COPY ["Agente Cobranzas/FRONT/assets", "/app/front/agents/collections/assets"]

RUN asset_version="$(find /app/front/assets /app/front/agents /app/front/bi/assets \
      -type f -print0 \
      | sort -z \
      | xargs -0 sha256sum \
      | sha256sum \
      | cut -c1-12)" \
    && sed -i "s/__ASSET_VERSION__/${asset_version}/g" \
      /app/front/index.html \
      /app/front/agents/collections/config.js \
      /app/front/agents/collections/index.html \
      /app/front/bi/index.html \
    && pip install --no-cache-dir /opt/bi-agent /opt/collections-agent .

USER 1001:1001

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"]

CMD ["python", "-m", "sonia"]
