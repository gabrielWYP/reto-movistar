"""Versioned prompt loader backed by an installed package resource."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files


@dataclass(frozen=True, slots=True)
class PromptDefinition:
    prompt_id: str
    version: str
    content: str

    def metadata(self) -> dict[str, str]:
        return {"prompt_id": self.prompt_id, "prompt_version": self.version}


def _front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise RuntimeError("El prompt BI debe incluir metadata YAML simple.")
    raw_metadata, content = text[4:].split("\n---\n", 1)
    metadata: dict[str, str] = {}
    for line in raw_metadata.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip().strip('"')
    return metadata, content.strip()


def load_system_prompt() -> PromptDefinition:
    resource = files("bi_agent_prompts").joinpath("system_v1.md")
    metadata, content = _front_matter(resource.read_text(encoding="utf-8"))
    prompt_id = metadata.get("prompt_id")
    version = metadata.get("prompt_version")
    if not prompt_id or not version or not content:
        raise RuntimeError("El prompt BI versionado está incompleto.")
    return PromptDefinition(prompt_id, version, content)


SYSTEM_PROMPT_DEFINITION = load_system_prompt()
SYSTEM_PROMPT = SYSTEM_PROMPT_DEFINITION.content


def prompt_metadata() -> dict[str, str]:
    return SYSTEM_PROMPT_DEFINITION.metadata()
