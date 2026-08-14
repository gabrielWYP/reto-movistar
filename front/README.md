# SON-IA Billing Frontend

Frontend estático independiente. Solo consume rutas relativas `/api/*`; no contiene reglas financieras, rutas de datasets ni secretos.

- Producción/Compose/K3S: Nginx no-root en puerto 8080, configurado con `BACKEND_HOST` y `BACKEND_PORT`.
- Demo local: `python front/dev_server.py`, proxy local sin lógica de negocio.

Los bloques de trazabilidad están cerrados por defecto y el contexto conversacional reside en el navegador.
