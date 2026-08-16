"""Static guardrails for the independent and shared Collections architecture."""

from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
BACKEND = AGENT_ROOT / "BACK" / "src" / "collections_agent"
FRONTEND = AGENT_ROOT / "FRONT"
REPOSITORY = AGENT_ROOT.parent


def test_collections_uses_openai_secret_without_hardcoding_credentials() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in BACKEND.glob("*.py"))
    assert "OPENAI_API_KEY" in source
    assert "OPENCODE_KEY" not in source
    assert "from openai import OpenAI" in source
    assert "sk-" not in source


def test_collections_keeps_independent_two_service_topology() -> None:
    assert (AGENT_ROOT / "compose.yaml").is_file()
    assert (AGENT_ROOT / "BACK" / "Dockerfile").is_file()
    assert (AGENT_ROOT / "FRONT" / "Dockerfile").is_file()
    manifests = AGENT_ROOT / "DEPLOY" / "kubernetes"
    assert {path.name for path in manifests.glob("*.yaml")} == {
        "back.yaml",
        "configmap.yaml",
        "front.yaml",
        "kustomization.yaml",
    }
    compose = (AGENT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "collections-back:" in compose
    assert "collections-front:" in compose
    assert "OPENAI_API_KEY" in compose


def test_shared_main_keeps_only_minimal_collections_adapters() -> None:
    shared_api = (REPOSITORY / "back" / "src" / "sonia" / "entrypoints" / "api.py").read_text(
        encoding="utf-8"
    )
    assert "create_collections_router" in shared_api
    assert (REPOSITORY / "front" / "agents" / "collections" / "config.js").is_file()
    shared_implementation = REPOSITORY / "back" / "src" / "sonia" / "agents" / "collections"
    assert not any(shared_implementation.rglob("*.py"))


def test_frontend_marks_only_successful_llm_responses() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    javascript = (FRONTEND / "assets" / "app.js").read_text(encoding="utf-8")
    assert 'id="ai-badge"' in html
    assert "Hecho con IA" in html
    assert 'const aiGenerated = data.mode === "llm"' in javascript
    assert "aiBadge.hidden = !aiGenerated" in javascript


def test_shared_proxy_and_frontend_accept_six_file_batch_uploads() -> None:
    proxy = REPOSITORY / "front" / "nginx.conf.template"
    javascript = (FRONTEND / "assets" / "app.js").read_text(encoding="utf-8")
    assert "client_max_body_size 26m;" in proxy.read_text(encoding="utf-8")
    assert 'form.append("files", file)' in javascript
    assert "files.length > 6" in javascript
