# Frontend del Agente BI

Cliente estático servido por Nginx sin toolchain Node. Consume exclusivamente
HTTP/JSON mediante rutas relativas `/api/*`; Nginx usa `BACKEND_HOST` y
`BACKEND_PORT` para llegar al servicio privado.

El navegador no lee CSV, no recibe secretos y no calcula saldos, ratios, Pareto
ni concentraciones. Renderiza la respuesta natural, `presentation`, `dashboard`
y el `AgentResponse` original recibido del backend.
