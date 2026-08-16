"""Versioned prompt loader for the Collections agent."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PromptDefinition:
    """Immutable prompt content and public version metadata."""

    prompt_id: str
    version: str
    content: str

    def metadata(self) -> dict[str, str]:
        """Return metadata suitable for API responses and logs."""
        return {"prompt_id": self.prompt_id, "prompt_version": self.version}


def _front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise RuntimeError("El prompt de Cobranzas debe incluir metadata YAML simple.")
    raw_metadata, content = text[4:].split("\n---\n", 1)
    metadata: dict[str, str] = {}
    for line in raw_metadata.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip().strip('"')
    return metadata, content.strip()


def load_system_prompt() -> PromptDefinition:
    """Load and validate the packaged system prompt."""
    try:
        text = (
            files("collections_agent_prompts").joinpath("system_v1.md").read_text(encoding="utf-8")
        )
    except ModuleNotFoundError:
        development_prompt = Path(__file__).resolve().parents[2] / "prompts" / "system_v1.md"
        text = development_prompt.read_text(encoding="utf-8")
    metadata, content = _front_matter(text)
    prompt_id = metadata.get("prompt_id")
    version = metadata.get("prompt_version")
    if not prompt_id or not version or not content:
        raise RuntimeError("El prompt de Cobranzas versionado está incompleto.")
    return PromptDefinition(prompt_id, version, content)


SYSTEM_PROMPT_DEFINITION = load_system_prompt()
SYSTEM_PROMPT = SYSTEM_PROMPT_DEFINITION.content


def prompt_metadata() -> dict[str, str]:
    """Expose non-sensitive prompt lineage."""
    return SYSTEM_PROMPT_DEFINITION.metadata()
