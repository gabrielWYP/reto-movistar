"""Local, dependency-free web UI for the SON-IA collections agent.

The app binds only to localhost. Financial calculations remain inside
CollectionsService; the browser receives its structured, JSON-safe outputs.
"""

from __future__ import annotations

import argparse
import json
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .service import CollectionsService


PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SON-IA | Cobranzas y Recaudación</title><style>
:root{--blue:#019df4;--ink:#10233d;--muted:#607087;--bg:#f4f7fb;--card:#fff;--line:#dce4ee;--green:#12795a;--amber:#a85b00;--red:#bd303e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 Inter,Segoe UI,Arial,sans-serif}.shell{max-width:1280px;margin:auto;padding:28px 22px 48px}.hero{background:linear-gradient(125deg,#06376b,#009de0);color:white;border-radius:22px;padding:28px 30px;box-shadow:0 14px 32px #0c518029}.eyebrow{font-size:12px;letter-spacing:.12em;font-weight:700;opacity:.8}.hero h1{margin:4px 0;font-size:31px}.hero p{margin:0;max-width:760px;opacity:.92}.nav{display:flex;flex-wrap:wrap;gap:9px;margin:22px 0}.nav button,.primary{border:0;border-radius:10px;padding:10px 14px;background:#e5edf6;color:#25415e;font:inherit;font-weight:650;cursor:pointer}.nav button.active,.primary{background:var(--blue);color:white}.panel{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:0 4px 14px #1b3a5b0b}.controls{display:flex;gap:12px;align-items:end;flex-wrap:wrap;margin-bottom:18px}.field{display:grid;gap:5px;min-width:220px}.field label{font-size:12px;font-weight:700;color:var(--muted)}input{border:1px solid #bbc8d6;border-radius:9px;padding:10px;font:inherit}.primary{min-width:130px}.notice{border-left:4px solid var(--blue);background:#eaf7ff;padding:11px 13px;border-radius:5px;margin:0 0 18px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:16px 0}.card{border:1px solid var(--line);border-radius:13px;padding:14px}.card span{display:block;color:var(--muted);font-size:12px;font-weight:700}.card strong{font-size:23px;display:block;margin-top:4px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.section h2{font-size:17px;margin:0 0 10px}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:12px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:9px 10px;border-bottom:1px solid #edf1f5;vertical-align:top}th{background:#f8fafc;color:#51647c;white-space:nowrap}tr:last-child td{border-bottom:0}.badge{display:inline-block;border-radius:99px;padding:2px 8px;font-size:11px;font-weight:700;background:#e6eef8;color:#2c517a}.HIGH,.CRITICA{background:#fee9eb;color:var(--red)}.MEDIUM,.VENCIDA{background:#fff0dc;color:var(--amber)}.LOW,.PAGADA,.CONCILIADA{background:#e5f5ee;color:var(--green)}.empty{color:var(--muted);padding:20px}.error{border-left-color:var(--red);background:#fff0f1}details{margin-top:14px}summary{cursor:pointer;font-weight:650}.hidden{display:none}@media(max-width:760px){.shell{padding:16px}.hero{padding:22px}.hero h1{font-size:25px}.grid{grid-template-columns:1fr}}
</style></head><body><main class="shell"><header class="hero"><div class="eyebrow">SON-IA · INTEGRATEL AGÉNTICA</div><h1>Cobranzas y Recaudación</h1><p>Consulta cartera, documentos, prioridades y excepciones con cálculos verificables. No es una conciliación bancaria: usa aplicaciones documentales del dataset.</p></header>
<nav class="nav" aria-label="Módulos"><button class="active" data-view="portfolio">Cartera</button><button data-view="customer">Cliente</button><button data-view="invoice">Factura</button><button data-view="priorities">Prioridades</button><button data-view="exceptions">Conciliación</button></nav>
<section class="panel"><div id="controls"></div><div id="feedback" class="notice">Cargando cartera…</div><div id="content"></div></section></main><script>
const state={view:'portfolio',asOf:'2026-08-07'};const content=document.querySelector('#content'),controls=document.querySelector('#controls'),feedback=document.querySelector('#feedback');
const labels={total_billed:'Facturado',total_paid_linked:'Pagado vinculado',credit_notes_linked:'Notas de crédito',outstanding_balance:'Saldo pendiente',overdue_balance:'Saldo vencido',collection_ratio:'Ratio cobrado/facturado',invoice_count:'Facturas',open_invoice_count:'Facturas abiertas',priority_score:'Score de prioridad',unmatched_payment_amount:'Pagos fuera de corte',unmatched_payment_count:'Pagos fuera de corte'};
const money=v=>typeof v==='number'?new Intl.NumberFormat('es-PE',{style:'currency',currency:'PEN'}).format(v):v??'—';const value=(key,v)=>key.includes('ratio')&&typeof v==='number'?(v*100).toFixed(1)+'%':/(amount|balance|billed|paid|credit)/.test(key)?money(v):String(v??'—');
function esc(v){return String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}function badge(v){return `<span class="badge ${esc(v)}">${esc(v)}</span>`}
function dateField(){return `<div class="field"><label>Fecha de corte</label><input id="asof" type="date" value="${state.asOf}"></div>`}function button(label='Consultar'){return `<button class="primary" id="run">${label}</button>`}
function renderControls(){let form=dateField();if(state.view==='customer')form+=`<div class="field"><label>Cliente</label><input id="entity" value="CLIENT_00385" placeholder="CLIENT_XXXXX"></div>`;if(state.view==='invoice')form+=`<div class="field"><label>Factura</label><input id="entity" value="S1AA-0052403449" placeholder="NRO_DOC_FISCAL"></div>`;if(['priorities','exceptions'].includes(state.view))form+=`<div class="field"><label>Máximo de casos</label><input id="limit" type="number" min="1" max="50" value="10"></div>`;controls.innerHTML=`<div class="controls">${form}${button()}</div>`;document.querySelector('#run').onclick=load;}
function table(rows){if(!rows?.length)return '<div class="empty">No hay registros para mostrar.</div>';const keys=[...new Set(rows.flatMap(Object.keys))].filter(k=>!['score_components','payments','credit_note_documents'].includes(k));return `<div class="table-wrap"><table><thead><tr>${keys.map(k=>`<th>${esc(k.replaceAll('_',' '))}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${keys.map(k=>`<td>${k.includes('state')||k==='severity'||k==='priority'?badge(row[k]):esc(typeof row[k]==='object'?JSON.stringify(row[k]):value(k,row[k]))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;}
function cards(metrics){const preferred=['total_billed','total_paid_linked','outstanding_balance','overdue_balance','collection_ratio','priority_score','exception_count'];const shown=preferred.filter(k=>k in metrics);return `<div class="cards">${shown.map(k=>`<div class="card"><span>${labels[k]||k.replaceAll('_',' ')}</span><strong>${value(k,metrics[k])}</strong></div>`).join('')}</div>`;}
function render(data){feedback.className='notice';feedback.textContent=`Resultado calculado al ${data.as_of_date}. ${data.data_quality?.known_limitations?.[0]||''}`;let html=cards(data.metrics||{});if(data.status&&Object.keys(data.status).length)html+=`<p><b>Estado:</b> ${Object.entries(data.status).map(([k,v])=>`${esc(k)} ${badge(v)}`).join(' · ')}</p>`;if(data.aging?.length)html+=`<section class="section"><h2>Ageing de cartera</h2>${table(data.aging)}</section>`;if(data.findings?.length)html+=`<section class="section"><h2>Hallazgos</h2>${table(data.findings)}</section>`;if(data.alerts?.length)html+=`<section class="section"><h2>Alertas</h2>${table(data.alerts)}</section>`;if(data.evidence?.length)html+=`<section class="section"><h2>Evidencia</h2>${table(data.evidence)}</section>`;if(data.recommended_actions?.length)html+=`<section class="section"><h2>Acciones recomendadas</h2>${table(data.recommended_actions)}</section>`;html+=`<details><summary>Ver resultado estructurado (JSON)</summary><pre>${esc(JSON.stringify(data,null,2))}</pre></details>`;content.innerHTML=html;}
async function load(){state.asOf=document.querySelector('#asof').value;let path='/api/'+state.view+'?as_of_date='+encodeURIComponent(state.asOf);const entity=document.querySelector('#entity');const limit=document.querySelector('#limit');if(entity)path+='&id='+encodeURIComponent(entity.value.trim());if(limit)path+='&limit='+encodeURIComponent(limit.value);feedback.className='notice';feedback.textContent='Calculando resultado…';content.innerHTML='';try{const response=await fetch(path);const data=await response.json();if(!response.ok)throw new Error(data.error||'No se pudo completar la consulta.');render(data)}catch(error){feedback.className='notice error';feedback.textContent=error.message||'Ocurrió un error inesperado.'}}
document.querySelectorAll('.nav button').forEach(button=>button.onclick=()=>{state.view=button.dataset.view;document.querySelectorAll('.nav button').forEach(x=>x.classList.toggle('active',x===button));renderControls();load()});renderControls();load();
</script></body></html>"""


def route_payload(service: CollectionsService, path: str) -> tuple[int, dict]:
    """Map a safe, fixed UI route to one deterministic service operation."""
    request = urlparse(path)
    params = parse_qs(request.query)
    as_of = params.get("as_of_date", [None])[0]
    entity = params.get("id", [""])[0]
    try:
        limit = max(1, min(50, int(params.get("limit", [10])[0])))
    except ValueError:
        return HTTPStatus.BAD_REQUEST, {"error": "El máximo de casos debe ser un número entre 1 y 50."}
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
    except (KeyError, ValueError) as error:
        return HTTPStatus.BAD_REQUEST, {"error": str(error)}


def create_server(service: CollectionsService, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/" or self.path.startswith("/?"):
                body = PAGE.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
            elif self.path.startswith("/api/"):
                status, payload = route_payload(service, self.path)
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
            else:
                body = b"Not found"
                self.send_response(HTTPStatus.NOT_FOUND)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def default_dataset() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "source" / "SONIA_DESAFIO_03.zip"


def main() -> None:
    parser = argparse.ArgumentParser(description="Interfaz local del agente SON-IA Cobranzas")
    parser.add_argument("--dataset", type=Path, default=default_dataset())
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--open", action="store_true", help="Abrir navegador al iniciar.")
    args = parser.parse_args()
    if not args.dataset.is_file():
        raise SystemExit(f"No se encontró el dataset: {args.dataset}")
    server = create_server(CollectionsService(args.dataset), args.port)
    url = f"http://127.0.0.1:{args.port}"
    print(f"SON-IA Cobranzas disponible en {url}")
    print("Presiona Ctrl+C para detener el servidor.")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

