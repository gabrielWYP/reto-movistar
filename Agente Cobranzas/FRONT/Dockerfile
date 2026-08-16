FROM nginxinc/nginx-unprivileged:1.29-alpine

ENV BACKEND_HOST=collections-back \
    BACKEND_PORT=8080

COPY ["Agente Cobranzas/FRONT/nginx.conf.template", "/etc/nginx/templates/default.conf.template"]
COPY ["Agente Cobranzas/FRONT/index.html", "/usr/share/nginx/html/index.html"]
COPY ["Agente Cobranzas/FRONT/assets", "/usr/share/nginx/html/assets"]
COPY ["front/assets/safe-markdown.js", "/usr/share/nginx/html/assets/safe-markdown.js"]

USER root

RUN asset_version="$(find /usr/share/nginx/html/assets \
      -type f -print0 \
      | sort -z \
      | xargs -0 sha256sum \
      | sha256sum \
      | cut -c1-12)" \
    && sed -i "s/__ASSET_VERSION__/${asset_version}/g" \
      /usr/share/nginx/html/index.html

USER 101

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["wget", "--quiet", "--tries=1", "--spider", "http://127.0.0.1:8080/"]
