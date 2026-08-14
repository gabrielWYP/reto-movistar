≠rá^—f•ñÿ¶{Nly 'v√Æ∂õ≠# Frontend - Agente de Cobranzas

Interfaz est√°tica para usuarios de negocio. La capa visual est√° separada para facilitar su mantenimiento:

- `index.html`: estructura y contenido sem√°ntico de la pantalla.
- `assets/styles.css`: estilos visuales y dise√±o adaptable.
- `assets/app.js`: interacci√≥n de la interfaz y llamadas a la API.

Nginx publica la p√°gina y redirige exclusivamente `/api/*` y `/health` al backend interno.
Por tanto, el navegador no recibe ninguna clave de OpenAI ni conoce la direcci√≥n privada del
pod backend.
