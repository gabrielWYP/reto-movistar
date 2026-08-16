from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from dataset_fixtures import source_bytes, write_sources, zip_sources
from billing_agent.app import create_app
from billing_agent.config import Settings


class DatasetUploadAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.default = write_sources(self.root / "default", 1, "DEFAULT")
        settings = Settings(dataset_path=self.default, upload_root=self.root / "uploads")
        self.app = create_app(settings)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def multipart(sources: dict[str, bytes]) -> list[tuple[str, tuple[str, bytes, str]]]:
        return [("files", (name, content, "text/csv")) for name, content in sources.items()]

    def upload_csv(self, invoice_count: int = 1, marker: str = "UPLOADED") -> dict:
        response = self.client.post("/api/datasets", files=self.multipart(source_bytes(invoice_count, marker)))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_ac11_upload_five_valid_csvs(self) -> None:
        result = self.upload_csv()
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["source_counts"]["invoices"], 1)

    def test_ac11_upload_valid_zip(self) -> None:
        response = self.client.post("/api/datasets", files={"files": ("billing.zip", zip_sources(2), "application/zip")})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["source_counts"]["invoices"], 2)

    def test_ac11_missing_required_source_is_rejected(self) -> None:
        sources = source_bytes()
        sources.pop(next(iter(sources)))
        response = self.client.post("/api/datasets", files=self.multipart(sources))
        self.assertEqual(response.status_code, 422)
        self.assertIn("cinco", json.dumps(response.json(), ensure_ascii=False).lower())

    def test_ac11_missing_required_column_is_rejected(self) -> None:
        sources = source_bytes()
        invoice_name = next(name for name in sources if name.startswith("005_"))
        sources[invoice_name] = sources[invoice_name].replace(b"|CHARGE_TOTAL_AMOUNT", b"")
        response = self.client.post("/api/datasets", files=self.multipart(sources))
        self.assertEqual(response.status_code, 422)
        self.assertIn("CHARGE_TOTAL_AMOUNT", response.text)

    def test_ac11_empty_file_is_rejected(self) -> None:
        sources = source_bytes()
        sources[next(iter(sources))] = b""
        response = self.client.post("/api/datasets", files=self.multipart(sources))
        self.assertEqual(response.status_code, 422)
        self.assertIn("vacío", response.text)

    def test_ac11_invalid_extension_is_rejected(self) -> None:
        response = self.client.post("/api/datasets", files={"files": ("datos.exe", b"not executable", "application/octet-stream")})
        self.assertEqual(response.status_code, 422)
        self.assertIn("Solo se permiten", response.text)

    def test_ac11_zip_path_traversal_is_rejected(self) -> None:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("../escape.csv", b"bad")
            for name, content in source_bytes().items():
                archive.writestr(name, content)
        response = self.client.post("/api/datasets", files={"files": ("billing.zip", output.getvalue(), "application/zip")})
        self.assertEqual(response.status_code, 422)
        self.assertIn("ruta no permitida", response.text)

    def test_ac11_dataset_id_is_isolated(self) -> None:
        first, second = self.upload_csv(1, "ONE"), self.upload_csv(1, "TWO")
        self.assertNotEqual(first["dataset_id"], second["dataset_id"])
        self.assertNotIn("ONE", json.dumps(second))

    def test_ac11_two_datasets_do_not_mix_results(self) -> None:
        first, second = self.upload_csv(1), self.upload_csv(2)
        one = self.client.get("/api/health", params={"dataset_id": first["dataset_id"]}).json()
        two = self.client.get("/api/health", params={"dataset_id": second["dataset_id"]}).json()
        self.assertEqual(one["agent_response"]["metrics"]["invoice_documents"], 1)
        self.assertEqual(two["agent_response"]["metrics"]["invoice_documents"], 2)

    def test_ac11_uploaded_dataset_changes_metrics(self) -> None:
        uploaded = self.upload_csv(2)
        default = self.client.get("/api/health").json()["agent_response"]["metrics"]["invoice_documents"]
        changed = self.client.get("/api/health", params={"dataset_id": uploaded["dataset_id"]}).json()["agent_response"]["metrics"]["invoice_documents"]
        self.assertEqual((default, changed), (1, 2))

    def test_ac11_default_dataset_still_works(self) -> None:
        self.upload_csv(2)
        status = self.client.get("/api/status", params={"dataset_id": "default"}).json()
        self.assertEqual((status["origin"], status["source_counts"]["invoices"]), ("Dataset predeterminado", 1))

    def test_ac11_frontend_never_receives_raw_path(self) -> None:
        uploaded = self.upload_csv()
        status = self.client.get(f"/api/datasets/{uploaded['dataset_id']}/status").json()
        self.assertNotIn(str(self.root), json.dumps(status))
        self.assertNotIn("workspace", status)

    def test_ac11_uploaded_csv_is_not_sent_to_llm(self) -> None:
        uploaded = self.upload_csv(marker="SECRET_CSV_ROW")
        received: list[str] = []

        class FakeLLM:
            available = True
            def select_tool(self, question: str) -> dict:
                return {"tool_name": "billing_health_snapshot", "arguments": {}}
            def interpret(self, question: str, compact: dict) -> str:
                received.append(json.dumps(compact, ensure_ascii=False))
                return "Explicación grounded mock."

        with patch("billing_agent.app.OpenAIRuntime", return_value=FakeLLM()), patch.dict(os.environ, {"OPENAI_API_KEY": "mock"}):
            response = self.client.post("/api/conversation", json={
                "question": "¿Qué debería revisar hoy?", "dataset_id": uploaded["dataset_id"], "context": {}
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "Explicación grounded mock.")
        self.assertNotIn("SECRET_CSV_ROW", "".join(received))
        self.assertNotIn(str(self.root), "".join(received))

    def test_ac11_delete_dataset_removes_workspace(self) -> None:
        uploaded = self.upload_csv()
        record = self.app.state.dataset_registry.resolve(uploaded["dataset_id"])
        workspace = record.workspace
        self.assertTrue(workspace and workspace.exists())
        response = self.client.delete(f"/api/datasets/{uploaded['dataset_id']}")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(workspace.exists())
        self.assertEqual(self.client.get(f"/api/datasets/{uploaded['dataset_id']}/status").status_code, 404)


if __name__ == "__main__":
    unittest.main()
