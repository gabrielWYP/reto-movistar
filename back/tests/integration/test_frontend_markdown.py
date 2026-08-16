"""Static safety contract for provider-generated Markdown rendering."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_markdown_renderer_builds_safe_dom_without_provider_inner_html() -> None:
    source = (ROOT / "front" / "assets" / "safe-markdown.js").read_text(encoding="utf-8")

    assert "createTextNode" in source
    assert "textContent" in source
    assert "replaceChildren" in source
    assert "innerHTML" not in source
    assert "eval(" not in source


def test_bi_and_collections_load_and_use_the_shared_renderer() -> None:
    frontends = (
        ROOT / "Agente BI" / "FRONT",
        ROOT / "Agente Cobranzas" / "FRONT",
    )

    for frontend in frontends:
        html = (frontend / "index.html").read_text(encoding="utf-8")
        javascript = next((frontend / "assets").glob("app.js")).read_text(encoding="utf-8")
        assert "/assets/safe-markdown.js?v=__ASSET_VERSION__" in html
        assert "SoniaMarkdown.render" in javascript
