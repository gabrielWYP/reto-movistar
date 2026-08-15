"""Static guardrails for the integrated client-server BI architecture."""

from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BI_BACKEND = REPOSITORY_ROOT / "back" / "src" / "sonia" / "agents" / "bi"
BI_FRONTEND = REPOSITORY_ROOT / "front" / "agents" / "bi"


def test_bi_has_no_parallel_http_server_or_embedded_frontend() -> None:
    assert not (BI_BACKEND / "web_app.py").exists()
    backend_source = "\n".join(
        path.read_text(encoding="utf-8") for path in BI_BACKEND.glob("*.py")
    )
    assert "http.server" not in backend_source
    assert "ThreadingHTTPServer" not in backend_source
    assert "<!doctype html>" not in backend_source.lower()
    assert "8502" not in backend_source


def test_supervisor_boundary_does_not_depend_on_fastapi() -> None:
    application_source = (BI_BACKEND / "application.py").read_text(encoding="utf-8")
    assert "from fastapi" not in application_source
    assert "import fastapi" not in application_source


def test_bi_frontend_is_a_pure_http_client_configuration() -> None:
    frontend_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in BI_FRONTEND.rglob("*")
        if path.is_file()
    )
    assert "/api/bi/query" in frontend_source
    for forbidden in (
        "BIService",
        "OPENAI_API_KEY",
        "CHARGE_TOTAL_AMOUNT",
        "MONTO_PAGADO",
        ".csv",
    ):
        assert forbidden not in frontend_source


def test_integrated_tree_has_no_old_bi_package_imports_or_launcher_docs() -> None:
    audited = [
        BI_BACKEND,
        REPOSITORY_ROOT / "back" / "tests" / "agents" / "test_bi_agent.py",
        REPOSITORY_ROOT / "back" / "README.md",
    ]
    contents = "\n".join(
        path.read_text(encoding="utf-8")
        for target in audited
        for path in ([target] if target.is_file() else target.rglob("*"))
        if path.is_file() and path.suffix in {".py", ".md"}
    )
    assert "bi_agent." not in contents
    assert "Iniciar Agente BI" not in contents
    assert "127.0.0.1:8502" not in contents
