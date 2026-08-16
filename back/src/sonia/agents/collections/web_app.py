"""Backward-compatible route adapter for the pre-integration local UI.

The production interface now lives in ``front/agents/collections`` and is
served by the shared frontend pod.  This module retains only the old route
mapping so existing deterministic callers can migrate without a second server.
"""

from __future__ import annotations

from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

from .service import CollectionsService


def route_payload(service: CollectionsService, path: str) -> tuple[int, dict]:
    """Map legacy local routes to the current deterministic service."""
    request = urlparse(path)
    params = parse_qs(request.query)
    as_of = params.get("as_of_date", [None])[0]
    entity = params.get("id", [""])[0]
    try:
        limit = max(1, min(50, int(params.get("limit", [10])[0])))
    except ValueError:
        return HTTPStatus.BAD_REQUEST, {
            "error": "La cantidad de casos debe ser un número entre 1 y 50."
        }
    try:
        routes = {
            "/api/portfolio": lambda: service.portfolio_snapshot(as_of),
            "/api/customer": lambda: service.customer_snapshot(entity, as_of),
            "/api/invoice": lambda: service.invoice_trace(entity, as_of),
            "/api/priorities": lambda: service.collection_priorities(limit, as_of),
            "/api/exceptions": lambda: service.reconciliation_exceptions(limit, as_of),
        }
        if request.path not in routes:
            return HTTPStatus.NOT_FOUND, {"error": "Ruta no encontrada."}
        return HTTPStatus.OK, routes[request.path]()
    except KeyError as error:
        return HTTPStatus.NOT_FOUND, {"error": str(error)}
    except ValueError as error:
        return HTTPStatus.BAD_REQUEST, {"error": str(error)}
