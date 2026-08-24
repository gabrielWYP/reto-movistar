"""Deployment caller must forward the required analyst authentication roster."""

from pathlib import Path


def test_reusable_deploy_receives_required_analyst_htpasswd() -> None:
    workflow = (
        Path(__file__).resolve().parents[3] / ".github/workflows/deploy-k3s.yml"
    ).read_text()
    deploy = workflow.split("\n  deploy:\n", maxsplit=1)[1]
    mapping = "ANALYST_HTPASSWD: ${{ secrets.ANALYST_HTPASSWD }}"

    assert "uses: gabrielwyp/K3S_Infra/.github/workflows/deploy-movistar.yml@main" in deploy
    assert deploy.count(mapping) == 1
