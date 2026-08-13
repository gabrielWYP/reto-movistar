"""Unit tests for runtime configuration."""

import pytest

from sonia.config import Settings


def test_settings_use_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defaults must match the local and K3S container contract."""
    for name in (
        "SONIA_APP_NAME",
        "SONIA_APP_VERSION",
        "SONIA_ENVIRONMENT",
        "SONIA_HOST",
        "SONIA_PORT",
        "SONIA_LOG_LEVEL",
        "SONIA_FRONTEND_DIR",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_environment()

    assert settings.app_name == "SON-IA"
    assert settings.host == "0.0.0.0"
    assert settings.port == 8080
    assert settings.log_level == "INFO"
    assert settings.frontend_dir.name == "front"


@pytest.mark.parametrize("port", ["0", "65536"])
def test_settings_reject_invalid_ports(
    monkeypatch: pytest.MonkeyPatch,
    port: str,
) -> None:
    """Invalid network ports must fail before the server starts."""
    monkeypatch.setenv("SONIA_PORT", port)

    with pytest.raises(ValueError, match="SONIA_PORT"):
        Settings.from_environment()
