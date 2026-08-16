# Prompts del Agente BI

`system_v1.md` es la única fuente de verdad del prompt de sistema. Su front
matter declara `prompt_id` y `prompt_version`; `bi_agent.prompting` lo carga con
`importlib.resources`, por lo que funciona en instalación editable, wheel,
Docker y Kubernetes sin depender del directorio actual.

Los prompts se versionan como código. Todo cambio de comportamiento debe:

1. crear una nueva versión o justificar compatibilidad;
2. actualizar los casos de evaluación;
3. mantener datos permitidos, outputs, riesgos y guardrails explícitos;
4. pasar las evaluaciones de prompt incluidas en `tests/test_bi_agent.py`.

No se crea un prompt de interpretación separado: las mismas restricciones deben
regir selección e interpretación, evitando dos fuentes de verdad divergentes.
