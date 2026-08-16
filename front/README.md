# Frontend SON-IA

SPA estática, sin toolchain Node, publicada por Nginx en el pod `front`. Nginx
mantiene el punto único de entrada: sirve la interfaz y enruta `/api/*` y
`/health` al servicio `back`.

La misma imagen copia los frontends independientes de BI y Cobranzas. Los sirve
bajo `/bi/` y `/agents/collections/` sin exponer puertos ni Services adicionales.

Variables del contenedor:

- `BACKEND_HOST`: nombre DNS del Service backend; por defecto `back`.
- `BACKEND_PORT`: puerto HTTP del backend; por defecto `8080`.

La interfaz simula un journey controlado con datos ficticios. No persiste casos,
no emite facturas reales y no aplica pagos.
