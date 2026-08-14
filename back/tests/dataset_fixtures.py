from __future__ import annotations

import io
import zipfile
from pathlib import Path

from sonia.agents.billing.data import TABLE_FILES


def source_bytes(invoice_count: int = 1, marker: str = "SAFE_MARKER") -> dict[str, bytes]:
    customer = (
        "NUMERO_IDENTIFICACION_FISCAL|RAZON_SOCIAL\n"
        f"RUC-{marker}|CLIENT_00001\n"
    )
    fixed = "RAZON_SOCIAL|COD_CUENTA|STATUS_DESC\nCLIENT_00001|100001|Active\n"
    mobile = "RAZON_SOCIAL|COD_CUENTA|ESTADO_LINEA\n"
    invoice_header = (
        "NUMERO_IDENTIFICACION_FISCAL|RAZON_SOCIAL|COD_CLIENTE|COD_CUENTA|"
        "NRO_DOC_FISCAL|FUENTE|SISTEMA|FECHA_EMISION|FECHA_VTO|MONEDA|"
        "CHARGE_NET_AMOUNT|CHARGE_IGV_INVOICE|CHARGE_TOTAL_AMOUNT\n"
    )
    rows = []
    for index in range(invoice_count):
        rows.append(
            f"RUC-{marker}|CLIENT_00001|C001|100001|F001-{index + 1:06d}|SRC|ISIS|"
            f"20260{index + 1}01|20260{index + 1}15|PEN|100.00|18.00|118.00"
        )
    invoices = invoice_header + "\n".join(rows) + "\n"
    notes = (
        "NUMERO_IDENTIFICACION_FISCAL|RAZON_SOCIAL|COD_CUENTA|NRO_DOC_FISCAL|"
        "FACTURA_AFECTADA|FECHAEMISION|MONEDA|MONTO_SIN_IGV|SUBTOTAL|MONTO\n"
    )
    values = {
        "customers": customer,
        "fixed_plant": fixed,
        "mobile_plant": mobile,
        "invoices": invoices,
        "credit_notes": notes,
    }
    return {TABLE_FILES[key]: value.encode("utf-8") for key, value in values.items()}


def write_sources(root: Path, invoice_count: int = 1, marker: str = "SAFE_MARKER") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for filename, content in source_bytes(invoice_count, marker).items():
        (root / filename).write_bytes(content)
    return root


def zip_sources(invoice_count: int = 1, marker: str = "SAFE_MARKER") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, content in source_bytes(invoice_count, marker).items():
            archive.writestr(filename, content)
    return output.getvalue()
