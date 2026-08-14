from __future__ import annotations

import json
import importlib.util
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from fastapi.testclient import TestClient

from dataset_fixtures import write_sources
from sonia.agents.billing import BillingAgentRuntime, BillingService, SessionContext
from sonia.agents.billing.openai_runtime import OpenAIRuntime
from sonia.app import create_app
from sonia.config import Settings


REPO = Path(__file__).resolve().parents[2]


class BillingArchitectureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dataset = write_sources(self.root / "default", 2)
        self.settings = Settings(dataset_path=self.dataset, upload_root=self.root / "uploads")
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_get_health_is_stable_json_without_dataset(self) -> None:
        app = create_app(Settings(dataset_path=None, upload_root=self.root / "empty-uploads"))
        response = TestClient(app).get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_api_five_views_return_agent_response_v1(self) -> None:
        paths = (
            "/api/health", "/api/customer?customer_id=CLIENT_00001",
            "/api/invoice?invoice_id=F001-000001", "/api/gaps",
            "/api/credit-notes",
        )
        for path in paths:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            payload = response.json()["agent_response"]
            self.assertEqual((payload["contract_version"], payload["agent"]), ("1.0", "billing"))

    def test_unknown_customer_and_invoice_are_safe_404(self) -> None:
        self.assertEqual(self.client.get("/api/customer?customer_id=UNKNOWN").status_code, 404)
        self.assertEqual(self.client.get("/api/invoice?invoice_id=UNKNOWN").status_code, 404)
        malformed = self.client.get("/api/health?as_of_date=fecha-invalida")
        self.assertEqual(malformed.status_code, 400)
        self.assertNotIn("Traceback", malformed.text)

    def test_front_and_back_are_physically_separate(self) -> None:
        self.assertTrue((REPO / "front" / "index.html").is_file())
        self.assertTrue((REPO / "back" / "src" / "sonia" / "app.py").is_file())
        self.assertFalse((REPO / "src" / "billing_agent" / "web_app.py").exists())
        python_sources = "\n".join(path.read_text("utf-8") for path in (REPO / "back" / "src").rglob("*.py"))
        self.assertNotIn("PAGE =", python_sources)

    def test_frontend_contains_no_business_rules_secrets_or_backend_address(self) -> None:
        frontend = "\n".join(
            path.read_text("utf-8") for path in (REPO / "front").rglob("*")
            if path.is_file() and path.suffix.lower() in {".html", ".css", ".js", ".py", ".md", ".template"}
        )
        for forbidden in ("OPENAI_API_KEY", "MATERIAL_MEDIUM", "TOLERANCE =", "Decimal(", "http://127.0.0.1:8503", "C:/Users/", "C:\\Users\\"):
            self.assertNotIn(forbidden, frontend)
        app_js = (REPO / "front" / "src" / "app.js").read_text("utf-8")
        self.assertNotIn("0.01", app_js)
        self.assertNotIn("0.25", app_js)
        self.assertIn('"/api/', app_js)

    def test_backend_runtime_is_independent_from_frontend(self) -> None:
        runtime = BillingAgentRuntime(BillingService(self.dataset))
        result = runtime.ask("¿Qué debería revisar hoy?", SessionContext())
        self.assertEqual(result["tool"], "billing_health_snapshot")

    def test_context_is_explicit_and_two_sessions_do_not_mix(self) -> None:
        first = self.client.post("/api/conversation", json={
            "question": "Revisa la factura F001-000001", "context": {}
        }).json()
        second = self.client.post("/api/conversation", json={
            "question": "¿Por qué requiere validación?", "context": {}
        }).json()
        follow_up = self.client.post("/api/conversation", json={
            "question": "¿Por qué requiere validación?", "context": first["context"]
        }).json()
        self.assertEqual(first["context"]["invoice_id"], "F001-000001")
        self.assertEqual(second["status"], "CLARIFICATION_REQUIRED")
        self.assertEqual(follow_up["tool"], "invoice_quality_check")

    def test_backend_configuration_comes_from_environment(self) -> None:
        with patch.dict(os.environ, {
            "SONIA_DATASET": str(self.dataset), "SONIA_HOST": "0.0.0.0", "SONIA_PORT": "9090",
            "SONIA_UPLOAD_ROOT": str(self.root / "configured")
        }, clear=True):
            settings = Settings.from_environment()
        self.assertEqual((settings.host, settings.port), ("0.0.0.0", 9090))
        self.assertEqual(settings.dataset_path, self.dataset.resolve())

    def test_no_key_uses_deterministic_fallback(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            runtime = BillingAgentRuntime(BillingService(self.dataset), OpenAIRuntime())
            result = runtime.ask("¿Qué debería revisar hoy?")
        self.assertEqual(result["route"], "deterministic")
        self.assertIn("Conclusión", result["answer"])

    def test_status_and_responses_never_expose_raw_path(self) -> None:
        status = self.client.get("/api/status").json()
        response = self.client.get("/api/health").json()
        serialized = json.dumps([status, response])
        self.assertNotIn(str(self.dataset), serialized)
        self.assertNotIn("workspace", serialized)

    def test_nginx_proxy_uses_runtime_backend_variables(self) -> None:
        nginx = (REPO / "front" / "nginx.conf.template").read_text("utf-8")
        self.assertIn("${BACKEND_HOST}:${BACKEND_PORT}", nginx)
        self.assertIn("location /api/", nginx)
        self.assertIn("location = /health", nginx)

    def test_local_front_proxy_reaches_independent_backend(self) -> None:
        class BackendHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                payload = b'{"proxy":"ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            def log_message(self, fmt: str, *args: object) -> None:
                return

        spec = importlib.util.spec_from_file_location("billing_front_dev_server", REPO / "front" / "dev_server.py")
        self.assertIsNotNone(spec and spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        backend = ThreadingHTTPServer(("127.0.0.1", 0), BackendHandler)
        front = module.create_server(REPO / "front", "127.0.0.1", 0, "127.0.0.1", backend.server_port)
        threads = [
            threading.Thread(target=backend.serve_forever, daemon=True),
            threading.Thread(target=front.serve_forever, daemon=True),
        ]
        for thread in threads:
            thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{front.server_port}/api/probe", timeout=5) as response:
                self.assertEqual(json.loads(response.read())["proxy"], "ok")
            with urlopen(f"http://127.0.0.1:{front.server_port}/", timeout=5) as response:
                self.assertIn(b"Billing Assurance", response.read())
            self.assertEqual(front.server_address[0], "127.0.0.1")
        finally:
            front.shutdown()
            backend.shutdown()
            front.server_close()
            backend.server_close()

    def test_containers_are_independent_and_non_root(self) -> None:
        back = (REPO / "back" / "Dockerfile").read_text("utf-8")
        front = (REPO / "front" / "Dockerfile").read_text("utf-8")
        compose = (REPO / "compose.yaml").read_text("utf-8")
        self.assertIn("USER 1001:1001", back)
        self.assertIn("USER 101", front)
        self.assertIn("BACKEND_HOST: back", compose)
        self.assertEqual(compose.count("ports:"), 1)


if __name__ == "__main__":
    unittest.main()
