"""Static guardrails for the standalone client-server BI architecture."""

from __future__ import annotations

from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
BI_BACKEND = AGENT_ROOT / "BACK" / "src" / "bi_agent"
BI_FRONTEND = AGENT_ROOT / "FRONT"


def test_bi_has_no_parallel_http_server_or_embedded_frontend() -> None:
    assert not (BI_BACKEND / "web_app.py").exists()
    backend_source = "\n".join(path.read_text(encoding="utf-8") for path in BI_BACKEND.glob("*.py"))
    assert "http.server" not in backend_source
    assert "ThreadingHTTPServer" not in backend_source
    assert "<!doctype html>" not in backend_source.lower()
    assert "8502" not in backend_source


def test_supervisor_boundary_does_not_depend_on_fastapi() -> None:
    application_source = (BI_BACKEND / "application.py").read_text(encoding="utf-8")
    assert "from fastapi" not in application_source
    assert "import fastapi" not in application_source


def test_bi_frontend_is_a_pure_http_client() -> None:
    frontend_source = "\n".join(
        path.read_text(encoding="utf-8") for path in BI_FRONTEND.rglob("*") if path.is_file()
    )
    assert 'fetch("/api/bi/query"' in frontend_source
    assert 'fetch("/api/bi/status"' in frontend_source
    for forbidden in (
        "BIService",
        "OPENAI_API_KEY",
        "OPENCODE_KEY",
        "CHARGE_TOTAL_AMOUNT",
        "MONTO_PAGADO",
        ".csv",
    ):
        assert forbidden not in frontend_source


def test_bi_frontend_marks_only_successful_llm_responses() -> None:
    html = (BI_FRONTEND / "index.html").read_text(encoding="utf-8")
    javascript = (BI_FRONTEND / "assets" / "app.js").read_text(encoding="utf-8")
    assert 'id="ai-badge"' in html
    assert "Hecho con IA" in html
    assert 'const aiGenerated = payload.mode === "llm"' in javascript
    assert 'byId("ai-badge").hidden = !aiGenerated' in javascript
    assert 'payload.mode === "deterministic_fallback"' in javascript


def test_front_proxies_allow_six_file_multipart_uploads() -> None:
    shared_proxy = AGENT_ROOT.parent / "front" / "nginx.conf.template"
    standalone_proxy = BI_FRONTEND / "nginx.conf.template"
    for proxy in (shared_proxy, standalone_proxy):
        assert "client_max_body_size 26m;" in proxy.read_text(encoding="utf-8")


def test_standalone_tree_has_no_legacy_paths_or_pending_prompt() -> None:
    current_test = Path(__file__).resolve()
    contents = "\n".join(
        path.read_text(encoding="utf-8")
        for path in AGENT_ROOT.rglob("*")
        if path.is_file()
        and path.resolve() != current_test
        and ".venv" not in path.parts
        and "tests" not in path.parts
        and path.suffix in {".py", ".md"}
    )
    assert "Iniciar Agente BI" not in contents
    assert "127.0.0.1:8502" not in contents
    assert "Pendiente BI-01" not in contents
    assert "C:\\Disco D" not in contents


def test_backend_has_no_frontend_assets_and_dataset_is_ignored() -> None:
    assert not any(path.suffix in {".html", ".css", ".js"} for path in BI_BACKEND.rglob("*"))
    root_ignore = (AGENT_ROOT.parent / ".gitignore").read_text(encoding="utf-8")
    docker_ignore = (AGENT_ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "Agente BI/DATASET/" in root_ignore
    assert "DATASET/" in docker_ignore
