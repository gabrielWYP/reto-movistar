"""Static guardrails for the shared Collections architecture."""

from __future__ import annotations

from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
BACKEND = AGENT_ROOT / "BACK" / "src" / "collections_agent"
FRONTEND = AGENT_ROOT / "FRONT"
REPOSITORY = AGENT_ROOT.parent


def test_collections_uses_only_the_shared_opencode_secret() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in BACKEND.glob("*.py"))
    assert "OPENCODE_KEY" in source
    assert "OPENAI_API_KEY" not in source
    assert "from openai" not in source
    assert "gpt-5.6-terra" not in source


def test_collections_has_no_standalone_container_topology() -> None:
    assert not (AGENT_ROOT / "compose.yaml").exists()
    assert not any(path.is_file() for path in (AGENT_ROOT / "DEPLOY").rglob("*"))
    assert not (AGENT_ROOT / "BACK" / "Dockerfile").exists()
    assert not (AGENT_ROOT / "FRONT" / "Dockerfile").exists()
    assert (REPOSITORY / "back" / "Dockerfile").is_file()
    assert (REPOSITORY / "front" / "Dockerfile").is_file()


def test_frontend_marks_only_successful_llm_responses() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    javascript = (FRONTEND / "assets" / "app.js").read_text(encoding="utf-8")
    assert 'id="ai-badge"' in html
    assert "Hecho con IA" in html
    assert 'const aiGenerated = data.mode === "llm"' in javascript
    assert "aiBadge.hidden = !aiGenerated" in javascript
    assert 'data.mode === "deterministic_fallback"' in javascript


def test_shared_proxy_and_frontend_accept_six_file_batch_uploads() -> None:
    proxy = REPOSITORY / "front" / "nginx.conf.template"
    javascript = (FRONTEND / "assets" / "app.js").read_text(encoding="utf-8")
    assert "client_max_body_size 26m;" in proxy.read_text(encoding="utf-8")
    assert 'form.append("files", file)' in javascript
    assert "files.length > 6" in javascript
