FROM nginxinc/nginx-unprivileged:1.29-alpine

ENV BACKEND_HOST=back \
    BACKEND_PORT=8080

COPY front/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY front/index.html /usr/share/nginx/html/index.html
COPY front/assets /usr/share/nginx/html/assets
COPY front/agents /usr/share/nginx/html/agents

USER root

RUN asset_version="$(find /usr/share/nginx/html/assets /usr/share/nginx/html/agents \
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
  CMD ["wget", "--quiet", "--tries=1", "--spider", "http://127.0.0.1:8080/health"]
