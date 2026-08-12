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
:root{--blue:#019df4;--ink:#10233d;--muted:#607087;--bg:#f4f7fb;--card:#fff;--line:#dce4ee;--green:#12795a;--amber:#a85b00;--red:#bd303e;--soft-blue:#eaf7ff}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 Inter,Segoe UI,Arial,sans-serif}.shell{max-width:1280px;margin:auto;padding:28px 22px 48px}.hero{background:linear-gradient(125deg,#06376b,#009de0);color:#fff;border-radius:22px;padding:28px 30px;box-shadow:0 14px 32px #0c518029}.eyebrow{font-size:12px;letter-spacing:.12em;font-weight:700;opacity:.8}.hero h1{margin:4px 0;font-size:31px}.hero p{margin:0;max-width:760px;opacity:.94}.nav{display:flex;flex-wrap:wrap;gap:9px;margin:22px 0}.nav button,.primary{border:0;border-radius:10px;padding:10px 14px;background:#e5edf6;color:#25415e;font:inherit;font-weight:650;cursor:pointer}.nav button.active,.primary{background:var(--blue);color:#fff}.nav button:focus-visible,.primary:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid #125ea9;outline-offset:2px}.panel{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:0 4px 14px #1b3a5b0b}.controls{display:flex;gap:12px;align-items:end;flex-wrap:wrap;margin-bottom:18px}.field{display:grid;gap:5px;min-width:220px}.field label{font-size:12px;font-weight:700;color:var(--muted)}input{border:1px solid #bbc8d6;border-radius:9px;padding:10px;font:inherit}.primary{min-width:130px}.notice{border-left:4px solid var(--blue);background:var(--soft-blue);padding:11px 13px;border-radius:5px;margin:0 0 18px}.narrative{margin:0 0 16px;padding:13px 15px;background:#f8fafc;border:1px solid var(--line);border-radius:11px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:16px 0}.card{border:1px solid var(--line);border-radius:13px;padding:14px;min-height:82px}.card span{display:block;color:var(--muted);font-size:12px;font-weight:700}.card strong{font-size:23px;display:block;margin-top:4px}.status-line{margin:14px 0 18px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}.status-label{font-weight:700}.section{margin-top:24px}.section h2{font-size:17px;margin:0 0 5px}.section-intro{margin:0 0 10px;color:var(--muted);font-size:13px}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:12px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:9px 10px;border-bottom:1px solid #edf1f5;vertical-align:top}th{background:#f8fafc;color:#51647c;white-space:nowrap}tr:last-child td{border-bottom:0}.badge{display:inline-block;border-radius:99px;padding:2px 8px;font-size:11px;font-weight:700;background:#e6eef8;color:#2c517a}.HIGH,.CRITICA{background:#fee9eb;color:var(--red)}.MEDIUM,.VENCIDA{background:#fff0dc;color:var(--amber)}.LOW,.PAGADA,.CONCILIADA{background:#e5f5ee;color:var(--green)}.action-list{display:grid;gap:10px}.action{border:1px solid var(--line);border-radius:11px;padding:12px 14px}.action strong{display:block}.action span{color:var(--muted);font-size:13px}.empty{color:var(--muted);padding:20px}.error{border-left-color:var(--red);background:#fff0f1}details{margin-top:20px;border-top:1px solid var(--line);padding-top:14px}summary{cursor:pointer;font-weight:650}pre{overflow:auto;background:#10233d;color:#eff6ff;padding:14px;border-radius:10px;font-size:12px}.help{color:var(--muted);font-size:12px;margin:4px 0 0}@media(max-width:760px){.shell{padding:16px}.hero{padding:22px}.hero h1{font-size:25px}.panel{padding:16px}}
</style></head><body><main class="shell"><header class="hero"><div class="eyebrow">SON-IA · INTEGRATEL AGÉNTICA</div><h1>Cobranzas y Recaudación</h1><p>Consulta el estado de la cartera, facturas, prioridades de gestión y casos que requieren validación.</p></header>
<nav class="nav" aria-label="Módulos"><button class="active" data-view="portfolio">Cartera</button><button data-view="customer">Cliente</button><button data-view="invoice">Factura</button><button data-view="priorities">Prioridades</button><button data-view="exceptions">Conciliación documental</button></nav>
<section class="panel"><div id="controls"></div><div id="feedback" class="notice">Cargando cartera…</div><div id="content"></div></section></main><script>
const state={view:'portfolio',asOf:'2026-08-07',customer:'CLIENT_00385',invoice:'S1AA-0052403449',limit:'10'};const content=document.querySelector('#content'),controls=document.querySelector('#controls'),feedback=document.querySelector('#feedback');
const labels={total_billed:'Facturado',total_paid_linked:'Pagos aplicados a facturas',credit_notes_linked:'Notas de crédito aplicadas',outstanding_balance:'Saldo pendiente',overdue_balance:'Saldo vencido',collection_ratio:'Cobranza aplicada / facturación',invoice_count:'Facturas emitidas',open_invoice_count:'Facturas con saldo',priority_score:'Índice de prioridad',exception_count:'Casos que requieren validación'};
const tips={total_billed:'Importe total de las facturas analizadas.',total_paid_linked:'Incluye únicamente pagos relacionados con una factura disponible en el corte.',outstanding_balance:'Importe que permanece por cobrar después de pagos y notas de crédito aplicados.',overdue_balance:'Parte del saldo pendiente cuya fecha de vencimiento ya pasó.',collection_ratio:'Pagos aplicados a facturas divididos entre el importe facturado.',priority_score:'Índice de 0 a 100. Alta: 60 a 100; Media: 30 a 59.9; Baja: menor a 30.',exception_count:'Casos que requieren contraste con el corte o sistema de origen; no son errores confirmados.'};
const statusLabels={priority:'Prioridad de gestión',collection_state:'Situación de cobranza',settlement:'Estado de pago',delinquency:'Situación de cobranza',reconciliation:'Aplicación de pagos'};
const statusText={HIGH:'Alta',MEDIUM:'Media',LOW:'Baja',PAGADA:'Pagada',PAGO_PARCIAL:'Pago parcial',PENDIENTE:'Pendiente de pago',SALDO_A_FAVOR:'Saldo a favor por validar',VENCIDA:'Vencida',CRITICA:'Vencida por más de 90 días',NO_VENCIDA:'Pendiente, aún no vencida',NO_APLICA:'Sin saldo pendiente',CONCILIADA:'Pago aplicado completamente',PARCIALMENTE_CONCILIADA:'Pago aplicado parcialmente',PENDIENTE_DE_PAGO:'Sin pago aplicado',REQUIERE_REVISION:'Requiere validación'};
const findingText={UNMATCHED_PAYMENT_CUTOFF:'Pago sin factura dentro del corte analizado',OVERDUE_EXPOSURE:'Saldo vencido que requiere gestión',OPEN_BALANCE:'Factura con saldo pendiente',OVERAPPLICATION:'Saldo a favor por validar',TEMPORAL_ANOMALY:'Fecha de pago por validar',PAYMENT_OUTSIDE_INVOICE_CUTOFF:'Pago sin factura dentro del corte',PAYMENT_BEFORE_ISSUANCE:'Fecha de pago por validar',SCORING_RULE:'Criterios de priorización',DOCUMENT_SETTLED:'Documento sin incidencias detectadas'};
const actionText={review_collection_priorities:'Revisar clientes prioritarios',review_unmatched_payments:'Validar pagos fuera del corte',contact_customer:'Contactar al cliente',monitor:'Mantener seguimiento',review_overapplication:'Validar saldo a favor',start_collection:'Iniciar gestión de cobranza',monitor_due_date:'Dar seguimiento al vencimiento',close_case:'No requiere gestión adicional',assign_collection_queue:'Asignar clientes prioritarios a gestión',review_exceptions:'Revisar casos de aplicación'};
const findingMessage={UNMATCHED_PAYMENT_CUTOFF:'Se identificaron pagos relacionados con facturas que no están disponibles dentro del corte analizado.',OVERDUE_EXPOSURE:'El cliente tiene saldo vencido y debe priorizarse según el índice calculado.',OPEN_BALANCE:'La factura aún tiene un importe pendiente de pago.',TEMPORAL_ANOMALY:'Hay un pago fechado antes de la emisión; valida el corte o la aplicación.'};
const reasonText={"Atender primero prioridades HIGH y documentar resultados de gestión.":'Atender primero a los clientes de prioridad alta y registrar el resultado de la gestión.'};
const limitationText={'El dataset no contiene extractos bancarios ni comunicaciones.':'La fuente analizada no contiene extractos bancarios ni comunicaciones.'};
const bucketText={NO_VENCIDA:'Aún no vencida','1_30':'De 1 a 30 días vencida','31_60':'De 31 a 60 días vencida','61_90':'De 61 a 90 días vencida','90_PLUS':'Más de 90 días vencida',SIN_FECHA_VENCIMIENTO:'Sin fecha de vencimiento'};
function esc(v){return String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}function money(v){return typeof v==='number'?new Intl.NumberFormat('es-PE',{style:'currency',currency:'PEN'}).format(v):'—'}function date(v){if(!v)return 'No disponible';const p=String(v).split('-');return p.length===3?`${p[2]}/${p[1]}/${p[0]}`:String(v)}function percent(v){return typeof v==='number'?`${(v*100).toFixed(1)}%`:'—'}function whole(v){return typeof v==='number'?new Intl.NumberFormat('es-PE').format(v):'—'}function status(v){return `<span class="badge ${esc(v)}" title="Estado interno: ${esc(v)}">${esc(statusText[v]||v)}</span>`}function severity(v){return status(v)}function priority(v){return status(v)}
function dateField(){return `<div class="field"><label for="asof">Fecha de corte</label><input id="asof" type="date" value="${esc(state.asOf)}"><p class="help">Los resultados no se actualizan en tiempo real.</p></div>`}function button(){return '<button class="primary" id="run">Consultar</button>'}
function renderControls(){let form=dateField();if(state.view==='customer')form+=`<div class="field"><label for="entity">Código de cliente</label><input id="entity" value="${esc(state.customer)}" placeholder="Ej.: CLIENT_00385"></div>`;if(state.view==='invoice')form+=`<div class="field"><label for="entity">N.° de factura</label><input id="entity" value="${esc(state.invoice)}" placeholder="Ej.: S1AA-0052403449"></div>`;if(['priorities','exceptions'].includes(state.view))form+=`<div class="field"><label for="limit">Cantidad de casos a mostrar</label><input id="limit" type="number" min="1" max="50" value="${esc(state.limit)}"><p class="help">Máximo 50 casos, ordenados por prioridad.</p></div>`;controls.innerHTML=`<div class="controls">${form}${button()}</div>`;document.querySelector('#run').onclick=load;}
function card(key,val){let text=key==='priority_score'?`${Number(val).toFixed(1)} / 100`:key==='collection_ratio'?percent(val):key==='exception_count'?whole(val):money(val);return `<div class="card" title="${esc(tips[key]||'')}"><span>${esc(labels[key]||key)}</span><strong>${text}</strong></div>`}function cards(metrics){let preferred=['total_billed','total_paid_linked','outstanding_balance','overdue_balance','collection_ratio','priority_score','exception_count'];return `<div class="cards">${preferred.filter(k=>k in metrics).map(k=>card(k,metrics[k])).join('')}</div>`}
function table(headers,rows){if(!rows.length)return '<div class="empty">No hay registros para mostrar.</div>';return `<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th${h.tip?` title="${esc(h.tip)}"`:''}>${esc(h.label)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(cell=>`<td>${cell}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}
function aging(rows){return `<section class="section"><h2>Antigüedad de la deuda</h2><p class="section-intro">Agrupa el saldo pendiente según los días transcurridos desde el vencimiento.</p>${table([{label:'Tramo de vencimiento'},{label:'Facturas'},{label:'Saldo pendiente'}],rows.map(r=>[esc(bucketText[r.bucket]||r.bucket),whole(r.documents),money(r.outstanding_balance)]))}</section>`}
function findings(rows){return `<section class="section"><h2>Situaciones identificadas</h2><p class="section-intro">Son hallazgos respaldados por el corte analizado; no reemplazan la validación operativa.</p>${table([{label:'Situación'},{label:'Nivel'},{label:'Qué significa'},{label:'Importe'},{label:'Casos'}],rows.map(r=>[esc(findingText[r.type]||r.type),severity(r.severity),esc(findingMessage[r.type]||r.message),r.amount==null?'—':money(r.amount),r.count==null?'—':whole(r.count)]))}</section>`}
function actions(rows){return `<section class="section"><h2>Siguientes acciones recomendadas</h2><div class="action-list">${rows.map(r=>`<div class="action"><strong>${esc(actionText[r.action]||r.action)}</strong><span>${esc(reasonText[r.reason]||r.reason||'')}</span>${r.priority?`<br>${priority(r.priority)}`:''}</div>`).join('')}</div></section>`}
function customerInvoices(rows){let open=rows.filter(r=>r.outstanding_balance>0);return `<section class="section"><h2>Facturas por gestionar</h2><p class="section-intro">Se muestran únicamente documentos con saldo pendiente. El detalle técnico conserva el historial completo.</p>${table([{label:'Factura'},{label:'Vencimiento'},{label:'Días de atraso'},{label:'Importe facturado'},{label:'Pagos aplicados'},{label:'Saldo pendiente'},{label:'Estado de pago'},{label:'Aplicación de pagos'}],open.map(r=>[esc(r.document),date(r.due_at),r.days_past_due==null?'—':whole(r.days_past_due),money(r.invoice_total),money(r.paid),money(r.outstanding_balance),status(r.settlement_state),status(r.reconciliation_state)]))}</section>`}
function invoiceDetail(r){let payments=r.payments||[],credits=r.credit_note_documents||[];let summary=`<section class="section"><h2>Resumen de la factura</h2>${table([{label:'Cliente'},{label:'Cuenta'},{label:'Fecha de emisión'},{label:'Fecha de vencimiento'},{label:'Días de atraso'},{label:'Importe facturado'},{label:'Notas de crédito'},{label:'Pagos aplicados'},{label:'Saldo pendiente'}],[[esc(r.customer),esc(r.account_code),date(r.issued_at),date(r.due_at),whole(r.days_past_due),money(r.invoice_total),money(r.credit_notes),money(r.paid),money(r.outstanding_balance)]])}</section>`;let paymentSection=`<section class="section"><h2>Pagos aplicados a esta factura</h2><p class="section-intro">Pagos relacionados con este documento en el dataset analizado.</p>${table([{label:'Fecha de pago'},{label:'Importe aplicado'},{label:'Cuenta'}],payments.map(p=>[date(p.paid_at),money(p.amount),esc(p.account_code)]))}</section>`;let creditSection=credits.length?`<section class="section"><h2>Notas de crédito aplicadas</h2>${table([{label:'Documento'},{label:'Fecha de emisión'},{label:'Importe'}],credits.map(c=>[esc(c.document),date(c.issued_at),money(c.amount)]))}</section>`:'';return summary+paymentSection+creditSection}
function priorities(rows,data){return `<section class="section"><h2>Clientes a priorizar</h2><p class="section-intro">${whole(data.metrics.customers_ranked)} clientes tienen saldo pendiente. Se muestran ${whole(data.metrics.returned)} en orden de prioridad.</p>${table([{label:'Posición'},{label:'Cliente'},{label:'Saldo pendiente'},{label:'Saldo vencido'},{label:'Mayor atraso',tip:'Máximo número de días de atraso entre sus facturas pendientes.'},{label:'% del saldo vencido',tip:'Porcentaje del saldo pendiente que ya venció.'},{label:'Índice / 100',tip:tips.priority_score},{label:'Prioridad'}],rows.map((r,i)=>[whole(i+1),esc(r.customer),money(r.outstanding_balance),money(r.overdue_balance),whole(r.max_days_past_due),percent(r.overdue_share),`${Number(r.priority_score).toFixed(1)} / 100`,priority(r.priority)]))}</section>`}
function exceptionSummary(rows,data){let grouped=Object.entries(rows.reduce((a,r)=>{a[r.type]=(a[r.type]||0)+1;return a},{}));return `<section class="section"><h2>Resumen de casos mostrados</h2><p class="section-intro">Se identificaron ${whole(data.metrics.exception_count)} casos que requieren validación; se muestran los ${whole(data.metrics.returned)} de mayor prioridad.</p>${table([{label:'Situación'},{label:'Casos mostrados'}],grouped.map(([type,count])=>[esc(findingText[type]||type),whole(count)]))}</section>`}
function exceptions(rows){return `<section class="section"><h2>Casos para validar</h2><p class="section-intro">Estos casos no son errores confirmados: deben contrastarse con el corte o sistema de origen.</p>${table([{label:'Situación'},{label:'Prioridad'},{label:'Factura'},{label:'Cliente'},{label:'Importe'},{label:'Fecha de pago'},{label:'Siguiente acción recomendada'}],rows.map(r=>[esc(findingText[r.type]||r.type),severity(r.severity),esc(r.document),esc(r.customer),r.amount==null?'—':money(r.amount),r.paid_at?date(r.paid_at):'—',esc(r.recommended_action)]))}</section>`}
function statusLine(items){let shown=Object.entries(items).filter(([k])=>statusLabels[k]);if(!shown.length)return '';return `<div class="status-line"><span class="status-label">Estado:</span>${shown.map(([k,v])=>`<span>${esc(statusLabels[k])}: ${status(v)}</span>`).join('<span>·</span>')}</div>`}
function narrative(data){let m=data.metrics||{},asOf=date(data.as_of_date);if(data.operation==='portfolio_snapshot')return `Al ${asOf}, la cartera mantiene ${money(m.outstanding_balance)} pendiente de cobro; ${money(m.overdue_balance)} ya está vencido.`;if(data.operation==='customer_snapshot')return m.overdue_balance>0?`Al ${asOf}, este cliente tiene ${money(m.overdue_balance)} vencido. Su atención sugerida es de prioridad ${statusText[data.status.priority]||data.status.priority}.`:`Al ${asOf}, este cliente no tiene saldo vencido.`;if(data.operation==='invoice_trace')return `Al ${asOf}, esta factura conserva ${money(m.outstanding_balance)} pendiente. Revisa el detalle de pagos aplicados antes de gestionar.`;if(data.operation==='collection_priorities')return `El ranking usa una fórmula reproducible de importe vencido, atraso, porcentaje vencido y concentración de la deuda.`;return `La conciliación disponible es documental: relaciona pagos, facturas y notas de crédito del corte analizado; no es una conciliación bancaria.`}
function render(data){feedback.className='notice';let limit=data.data_quality?.known_limitations?.[0];feedback.textContent=`Información calculada al ${date(data.as_of_date)}.${limit?` ${limitationText[limit]||limit}`:''}`;let html=`<p class="narrative">${esc(narrative(data))}</p>${cards(data.metrics||{})}${statusLine(data.status||{})}`;if(data.operation==='portfolio_snapshot'){if(data.aging?.length)html+=aging(data.aging);if(data.findings?.length)html+=findings(data.findings)}if(data.operation==='customer_snapshot'){if(data.aging?.length)html+=aging(data.aging);if(data.findings?.length)html+=findings(data.findings);html+=customerInvoices(data.evidence||[])}if(data.operation==='invoice_trace'){if(data.findings?.length)html+=findings(data.findings);html+=invoiceDetail(data.evidence?.[0]||{})}if(data.operation==='collection_priorities'){html+=priorities(data.evidence||[],data);if(data.findings?.length)html+=`<details><summary>Cómo se calcula la prioridad</summary><p>El índice considera importe vencido, atraso, porcentaje vencido y concentración. Va de 0 a 100: Alta desde 60, Media desde 30 y Baja por debajo de 30.</p></details>`}if(data.operation==='reconciliation_exceptions'){html+=exceptionSummary(data.evidence||[],data);html+=exceptions(data.evidence||[])}if(data.recommended_actions?.length)html+=actions(data.recommended_actions);html+=`<details><summary>Detalle técnico e integración (JSON)</summary><pre>${esc(JSON.stringify(data,null,2))}</pre></details>`;content.innerHTML=html;}
async function load(){state.asOf=document.querySelector('#asof').value;let path='/api/'+state.view+'?as_of_date='+encodeURIComponent(state.asOf);const entity=document.querySelector('#entity');const limit=document.querySelector('#limit');if(entity){if(state.view==='customer')state.customer=entity.value.trim();else state.invoice=entity.value.trim();path+='&id='+encodeURIComponent(entity.value.trim())}if(limit){state.limit=limit.value;path+='&limit='+encodeURIComponent(limit.value)}feedback.className='notice';feedback.textContent='Calculando resultado…';content.innerHTML='';try{const response=await fetch(path);const data=await response.json();if(!response.ok)throw new Error(data.error||'No se pudo completar la consulta.');render(data)}catch(error){feedback.className='notice error';feedback.textContent=error.message||'Ocurrió un error inesperado.'}}
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
