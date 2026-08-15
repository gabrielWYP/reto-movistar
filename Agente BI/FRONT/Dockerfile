FROM nginxinc/nginx-unprivileged:1.29-alpine

ENV BACKEND_HOST=bi-back \
    BACKEND_PORT=8080

COPY FRONT/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY FRONT/index.html /usr/share/nginx/html/index.html
COPY FRONT/assets /usr/share/nginx/html/assets

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["wget", "--quiet", "--tries=1", "--spider", "http://127.0.0.1:8080/"]
