# Frontend del Agente de Cobranzas/Recaudación

Interfaz estática humanizada servida por Nginx. No calcula importes ni procesa
CSV: todas las operaciones se delegan a `/api/collections/*`.

En modo standalone se publica en `http://localhost:8081`. En la aplicación
compartida se monta bajo `/agents/collections/`.
