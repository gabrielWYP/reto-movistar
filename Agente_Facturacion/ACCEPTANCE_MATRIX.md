# Matriz de aceptación · Billing Assurance

| ID | Requisito | Implementación | Endpoint/UI | Test | Resultado |
|----|-----------|----------------|-------------|------|-----------|
| AC-01 | Estado general | Snapshot determinístico con métricas, cobertura y narrativa grounded | `/api/health`, Resumen, Asistente | `test_ac01_portfolio_health` | PASS |
| AC-02 | Excepciones | Ocho códigos estables y reglas preservadas en BACK | Cinco vistas | `test_ac02_exception_detection` | PASS |
| AC-03 | Cliente/cuenta/factura | Billing 360, filtros y control documental | `/api/customer`, `/api/invoice`, `/api/gaps`, `/api/credit-notes` | `test_ac03_customer_account_invoice_analysis` | PASS |
| AC-04 | Evidencia | Evidence refs, regla, valor observado y fuente en AgentResponse | Ver evidencia / trazabilidad | `test_ac04_findings_include_evidence` | PASS |
| AC-05 | Categorías | DETERMINISTIC, HEURISTIC y DATA_QUALITY preservadas y traducidas | Badges de negocio | `test_ac05_rule_categories_are_preserved` | PASS |
| AC-06 | No inventar | Limitaciones explícitas; NC sin causalidad inferida | Asistente y caveats | `test_ac06_unsupported_claims_are_not_generated` | PASS |
| AC-07 | Siguiente validación | `recommended_validation` en hallazgos accionables | Hallazgos / evidencia | `test_ac07_recommended_validation_exists` | PASS |
| AC-08 | Lenguaje natural | Router y catálogo cerrado de cinco tools | `/api/conversation`, Asistente | `test_ac08_natural_language_routes_to_closed_tool` | PASS |
| AC-09 | Handoff | Collections/BI estructurado, sin uso de Pagos | `/api/conversation` | `test_ac09_collections_and_bi_handoff` | PASS |
| AC-10 | Sin LLM | Router, tools y narrativa determinísticos; fallback | Toda la app | `test_ac10_works_without_llm` | PASS |
| AC-11 | Dataset dinámico | Registro aislado, cinco CSV/ZIP, validación, DELETE y TTL | `/api/datasets`, Fuente de datos | `test_ac11_dynamic_dataset_upload` + 14 tests upload | PASS |
