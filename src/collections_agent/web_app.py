"""Local web UI for deterministic collections analysis and optional OpenAI tool calling."""

from __future__ import annotations

import argparse
import cgi
import json
import os
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import Settings
from .openai_runtime import ask
from .service import CollectionsService
from .uploads import load_uploaded_csvs


PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SON-IA | Cobranzas y Recaudación</title><style>
:root{--blue:#019df4;--ink:#10233d;--muted:#607087;--bg:#f4f7fb;--card:#fff;--line:#dce4ee;--green:#12795a;--amber:#a85b00;--red:#bd303e;--soft:#eaf7ff}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 Inter,Segoe UI,Arial,sans-serif}.shell{max-width:1280px;margin:auto;padding:28px 22px 48px}.hero{background:linear-gradient(125deg,#06376b,#009de0);color:#fff;border-radius:22px;padding:28px 30px;box-shadow:0 14px 32px #0c518029}.eyebrow{font-size:12px;letter-spacing:.12em;font-weight:700;opacity:.8}.hero h1{margin:4px 0;font-size:31px}.hero p{margin:0;max-width:760px;opacity:.94}.nav{display:flex;flex-wrap:wrap;gap:9px;margin:22px 0}.nav button,.primary,.secondary{border:0;border-radius:10px;padding:10px 14px;background:#e5edf6;color:#25415e;font:inherit;font-weight:650;cursor:pointer}.nav button.active,.primary{background:var(--blue);color:#fff}.nav button:focus-visible,.primary:focus-visible,.secondary:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid #125ea9;outline-offset:2px}.panel,.assistant,.upload{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:0 4px 14px #1b3a5b0b}.assistant,.upload{margin-bottom:16px}.assistant h2,.upload h2{font-size:18px;margin:0 0 4px}.section-note,.help{color:var(--muted);font-size:13px;margin:0 0 12px}.controls,.chat-row{display:flex;gap:12px;align-items:end;flex-wrap:wrap}.field{display:grid;gap:5px;min-width:220px}.field label{font-size:12px;font-weight:700;color:var(--muted)}input{border:1px solid #bbc8d6;border-radius:9px;padding:10px;font:inherit}.chat-row input{flex:1;min-width:260px}.primary{min-width:130px}.notice{border-left:4px solid var(--blue);background:var(--soft);padding:11px 13px;border-radius:5px;margin:18px 0}.notice.error{border-left-color:var(--red);background:#fff0f1}.notice.success{border-left-color:var(--green);background:#edf9f4}.status{display:inline-block;border-radius:99px;padding:3px 9px;font-size:12px;font-weight:700;background:#e6eef8;color:#2c517a}.status.ready{background:#e5f5ee;color:var(--green)}.status.warn{background:#fff0dc;color:var(--amber)}.narrative{margin:0 0 16px;padding:13px 15px;background:#f8fafc;border:1px solid var(--line);border-radius:11px}.answer{white-space:pre-wrap;margin:14px 0 0;padding:14px;border-radius:11px;background:#f8fafc;border:1px solid var(--line)}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:16px 0}.card{border:1px solid var(--line);border-radius:13px;padding:14px;min-height:82px}.card span{display:block;color:var(--muted);font-size:12px;font-weight:700}.card strong{font-size:23px;display:block;margin-top:4px}.status-line{margin:14px 0 18px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}.status-label{font-weight:700}.section{margin-top:24px}.section h2{font-size:17px;margin:0 0 5px}.section-intro{margin:0 0 10px;color:var(--muted);font-size:13px}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:12px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:9px 10px;border-bottom:1px solid #edf1f5;vertical-align:top}th{background:#f8fafc;color:#51647c;white-space:nowrap}tr:last-child td{border-bottom:0}.badge{display:inline-block;border-radius:99px;padding:2px 8px;font-size:11px;font-weight:700;background:#e6eef8;color:#2c517a}.HIGH,.CRITICA{background:#fee9eb;color:var(--red)}.MEDIUM,.VENCIDA{background:#fff0dc;color:var(--amber)}.LOW,.PAGADA,.CONCILIADA{background:#e5f5ee;color:var(--green)}.action-list{display:grid;gap:10px}.action{border:1px solid var(--line);border-radius:11px;padding:12px 14px}.action strong{display:block}.action span{color:var(--muted);font-size:13px}.empty{color:var(--muted);padding:20px}details{margin-top:20px;border-top:1px solid var(--line);padding-top:14px}summary{cursor:pointer;font-weight:650}pre{overflow:auto;background:#10233d;color:#eff6ff;padding:14px;border-radius:10px;font-size:12px}.hidden{display:none}@media(max-width:760px){.shell{padding:16px}.hero{padding:22px}.hero h1{font-size:25px}.panel,.assistant,.upload{padding:16px}}
</style></head><body><main class="shell"><header class="hero"><div class="eyebrow">SON-IA · INTEGRATEL AGÉNTICA</div><h1>Cobranzas y Recaudación</h1><p>Consulta cartera, facturas, prioridades de gestión y casos que requieren validación.</p></header>
<section class="assistant"><h2>Consulta con IA</h2><p class="section-note">Formula tu pregunta en lenguaje natural. La IA selecciona herramientas de análisis; los montos y estados se calculan con reglas verificables.</p><div class="chat-row"><input id="question" aria-label="Pregunta para el agente" placeholder="Ej.: ¿Qué clientes deberían priorizarse hoy?"><button class="primary" id="ask">Consultar con IA</button><span id="ai-status" class="status">Verificando IA…</span></div><div id="answer" class="answer hidden" aria-live="polite"></div></section>
<section class="upload"><h2>Analizar archivos CSV</h2><p class="section-note">Selecciona uno o varios CSV. Se validan columnas, tipos y compatibilidad antes de reemplazar temporalmente los datos de análisis. La carga no se guarda en disco.</p><div class="controls"><div class="field"><label for="files">Archivos CSV</label><input id="files" type="file" accept=".csv,text/csv" multiple></div><button class="secondary" id="upload">Validar y usar archivos</button><span id="data-status" class="status">Dataset oficial</span></div><div id="upload-result" class="hidden" aria-live="polite"></div></section>
<nav class="nav" aria-label="Módulos"><button class="active" data-view="portfolio">Cartera</button><button data-view="customer">Cliente</button><button data-view="invoice">Factura</button><button data-view="priorities">Prioridades</button><button data-view="exceptions">Conciliación documental</button></nav>
<section class="panel"><div id="controls"></div><div id="feedback" class="notice">Cargando cartera…</div><div id="content"></div></section></main><script>
const state={view:'portfolio',asOf:'2026-08-07',customer:'CLIENT_00385',invoice:'S1AA-0052403449',limit:'10'};const content=document.querySelector('#content'),controls=document.querySelector('#controls'),feedback=document.querySelector('#feedback');
const labels={total_billed:'Facturado',total_paid_linked:'Pagos aplicados a facturas',credit_notes_linked:'Notas de crédito aplicadas',outstanding_balance:'Saldo pendiente',overdue_balance:'Saldo vencido',collection_ratio:'Cobranza aplicada / facturación',priority_score:'Índice de prioridad',exception_count:'Casos que requieren validación'};
const tips={total_billed:'Importe total de las facturas analizadas.',total_paid_linked:'Incluye únicamente pagos relacionados con una factura disponible en el corte.',outstanding_balance:'Importe por cobrar después de pagos y notas de crédito aplicados.',overdue_balance:'Parte del saldo pendiente cuya fecha de vencimiento ya pasó.',collection_ratio:'Pagos aplicados a facturas divididos entre el importe facturado.',priority_score:'Índice de 0 a 100. Alta: 60 a 100; Media: 30 a 59.9; Baja: menor a 30.',exception_count:'Casos para contrastar con el corte o sistema de origen; no son errores confirmados.'};
const statusLabels={priority:'Prioridad de gestión',collection_state:'Situación de cobranza',settlement:'Estado de pago',delinquency:'Situación de cobranza',reconciliation:'Aplicación de pagos'};const statusText={HIGH:'Alta',MEDIUM:'Media',LOW:'Baja',PAGADA:'Pagada',PAGO_PARCIAL:'Pago parcial',PENDIENTE:'Pendiente de pago',SALDO_A_FAVOR:'Saldo a favor por validar',VENCIDA:'Vencida',CRITICA:'Vencida por más de 90 días',NO_VENCIDA:'Pendiente, aún no vencida',NO_APLICA:'Sin saldo pendiente',CONCILIADA:'Pago aplicado completamente',PARCIALMENTE_CONCILIADA:'Pago aplicado parcialmente',PENDIENTE_DE_PAGO:'Sin pago aplicado',REQUIERE_REVISION:'Requiere validación'};const findingText={UNMATCHED_PAYMENT_CUTOFF:'Pago sin factura dentro del corte analizado',OVERDUE_EXPOSURE:'Saldo vencido que requiere gestión',OPEN_BALANCE:'Factura con saldo pendiente',OVERAPPLICATION:'Saldo a favor por validar',TEMPORAL_ANOMALY:'Fecha de pago por validar',PAYMENT_OUTSIDE_INVOICE_CUTOFF:'Pago sin factura dentro del corte',PAYMENT_BEFORE_ISSUANCE:'Fecha de pago por validar',DOCUMENT_SETTLED:'Documento sin incidencias detectadas'};const actionText={review_collection_priorities:'Revisar clientes prioritarios',review_unmatched_payments:'Validar pagos fuera del corte',contact_customer:'Contactar al cliente',monitor:'Mantener seguimiento',review_overapplication:'Validar saldo a favor',start_collection:'Iniciar gestión de cobranza',monitor_due_date:'Dar seguimiento al vencimiento',close_case:'No requiere gestión adicional',assign_collection_queue:'Asignar clientes prioritarios a gestión',review_exceptions:'Revisar casos de aplicación'};const bucketText={NO_VENCIDA:'Aún no vencida','1_30':'De 1 a 30 días vencida','31_60':'De 31 a 60 días vencida','61_90':'De 61 a 90 días vencida','90_PLUS':'Más de 90 días vencida',SIN_FECHA_VENCIMIENTO:'Sin fecha de vencimiento'};
function esc(v){return String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}function money(v){return typeof v==='number'?new Intl.NumberFormat('es-PE',{style:'currency',currency:'PEN'}).format(v):'—'}function date(v){if(!v)return 'No disponible';let p=String(v).split('-');return p.length===3?`${p[2]}/${p[1]}/${p[0]}`:String(v)}function percent(v){return typeof v==='number'?`${(v*100).toFixed(1)}%`:'—'}function whole(v){return typeof v==='number'?new Intl.NumberFormat('es-PE').format(v):'—'}function status(v){return `<span class="badge ${esc(v)}">${esc(statusText[v]||v)}</span>`}
function dateField(){return `<div class="field"><label for="asof">Fecha de corte</label><input id="asof" type="date" value="${esc(state.asOf)}"><p class="help">Los resultados no se actualizan en tiempo real.</p></div>`}function renderControls(){let form=dateField();if(state.view==='customer')form+=`<div class="field"><label for="entity">Código de cliente</label><input id="entity" value="${esc(state.customer)}" placeholder="Ej.: CLIENT_00385"></div>`;if(state.view==='invoice')form+=`<div class="field"><label for="entity">N.° de factura</label><input id="entity" value="${esc(state.invoice)}" placeholder="Ej.: S1AA-0052403449"></div>`;if(['priorities','exceptions'].includes(state.view))form+=`<div class="field"><label for="limit">Cantidad de casos a mostrar</label><input id="limit" type="number" min="1" max="50" value="${esc(state.limit)}"></div>`;controls.innerHTML=`<div class="controls">${form}<button class="primary" id="run">Consultar</button></div>`;document.querySelector('#run').onclick=load;}
function card(key,val){let text=key==='priority_score'?`${Number(val).toFixed(1)} / 100`:key==='collection_ratio'?percent(val):key==='exception_count'?whole(val):money(val);return `<div class="card" title="${esc(tips[key]||'')}"><span>${esc(labels[key]||key)}</span><strong>${text}</strong></div>`}function cards(metrics){let preferred=['total_billed','total_paid_linked','outstanding_balance','overdue_balance','collection_ratio','priority_score','exception_count'];return `<div class="cards">${preferred.filter(k=>k in metrics).map(k=>card(k,metrics[k])).join('')}</div>`}function table(headers,rows){if(!rows.length)return '<div class="empty">No hay registros para mostrar.</div>';return `<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(cell=>`<td>${cell}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}
function aging(rows){return `<section class="section"><h2>Antigüedad de la deuda</h2><p class="section-intro">Agrupa el saldo pendiente según los días transcurridos desde el vencimiento.</p>${table(['Tramo de vencimiento','Facturas','Saldo pendiente'],rows.map(r=>[esc(bucketText[r.bucket]||r.bucket),whole(r.documents),money(r.outstanding_balance)]))}</section>`}function findings(rows){return `<section class="section"><h2>Situaciones identificadas</h2><p class="section-intro">Son hallazgos respaldados por el corte analizado; no reemplazan la validación operativa.</p>${table(['Situación','Nivel','Qué significa','Importe','Casos'],rows.map(r=>[esc(findingText[r.type]||r.type),status(r.severity),esc(r.message),r.amount==null?'—':money(r.amount),r.count==null?'—':whole(r.count)]))}</section>`}function actions(rows){return `<section class="section"><h2>Siguientes acciones recomendadas</h2><div class="action-list">${rows.map(r=>`<div class="action"><strong>${esc(actionText[r.action]||r.action)}</strong><span>${esc(r.reason||'')}</span>${r.priority?`<br>${status(r.priority)}`:''}</div>`).join('')}</div></section>`}
function customerInvoices(rows){let open=rows.filter(r=>r.outstanding_balance>0);return `<section class="section"><h2>Facturas por gestionar</h2><p class="section-intro">Se muestran únicamente documentos con saldo pendiente.</p>${table(['Factura','Vencimiento','Días de atraso','Importe facturado','Pagos aplicados','Saldo pendiente','Estado de pago','Aplicación de pagos'],open.map(r=>[esc(r.document),date(r.due_at),whole(r.days_past_due),money(r.invoice_total),money(r.paid),money(r.outstanding_balance),status(r.settlement_state),status(r.reconciliation_state)]))}</section>`}function invoiceDetail(r){let payments=r.payments||[],credits=r.credit_note_documents||[];let summary=`<section class="section"><h2>Resumen de la factura</h2>${table(['Cliente','Cuenta','Emisión','Vencimiento','Días de atraso','Importe facturado','Notas de crédito','Pagos aplicados','Saldo pendiente'],[[esc(r.customer),esc(r.account_code),date(r.issued_at),date(r.due_at),whole(r.days_past_due),money(r.invoice_total),money(r.credit_notes),money(r.paid),money(r.outstanding_balance)]])}</section>`;let pays=`<section class="section"><h2>Pagos aplicados a esta factura</h2>${table(['Fecha de pago','Importe aplicado','Cuenta'],payments.map(p=>[date(p.paid_at),money(p.amount),esc(p.account_code)]))}</section>`;let notes=credits.length?`<section class="section"><h2>Notas de crédito aplicadas</h2>${table(['Documento','Fecha de emisión','Importe'],credits.map(c=>[esc(c.document),date(c.issued_at),money(c.amount)]))}</section>`:'';return summary+pays+notes}function priorities(rows,data){return `<section class="section"><h2>Clientes a priorizar</h2><p class="section-intro">${whole(data.metrics.customers_ranked)} clientes tienen saldo pendiente. Se muestran ${whole(data.metrics.returned)} en orden de prioridad.</p>${table(['Posición','Cliente','Saldo pendiente','Saldo vencido','Mayor atraso','% del saldo vencido','Índice / 100','Prioridad'],rows.map((r,i)=>[whole(i+1),esc(r.customer),money(r.outstanding_balance),money(r.overdue_balance),whole(r.max_days_past_due),percent(r.overdue_share),`${Number(r.priority_score).toFixed(1)} / 100`,status(r.priority)]))}</section>`}function exceptions(rows,data){return `<section class="section"><h2>Casos para validar</h2><p class="section-intro">Se identificaron ${whole(data.metrics.exception_count)} casos; estos no son errores confirmados.</p>${table(['Situación','Prioridad','Factura','Cliente','Importe','Fecha de pago','Siguiente acción recomendada'],rows.map(r=>[esc(findingText[r.type]||r.type),status(r.severity),esc(r.document),esc(r.customer),r.amount==null?'—':money(r.amount),r.paid_at?date(r.paid_at):'—',esc(r.recommended_action)]))}</section>`}function statusLine(items){let shown=Object.entries(items).filter(([k])=>statusLabels[k]);return shown.length?`<div class="status-line"><span class="status-label">Estado:</span>${shown.map(([k,v])=>`<span>${esc(statusLabels[k])}: ${status(v)}</span>`).join('<span>·</span>')}</div>`:''}function narrative(data){let m=data.metrics||{},cut=date(data.as_of_date);if(data.operation==='portfolio_snapshot')return `Al ${cut}, la cartera mantiene ${money(m.outstanding_balance)} pendiente de cobro; ${money(m.overdue_balance)} ya está vencido.`;if(data.operation==='customer_snapshot')return m.overdue_balance>0?`Al ${cut}, este cliente tiene ${money(m.overdue_balance)} vencido.`:`Al ${cut}, este cliente no tiene saldo vencido.`;if(data.operation==='invoice_trace')return `Al ${cut}, esta factura conserva ${money(m.outstanding_balance)} pendiente.`;if(data.operation==='collection_priorities')return 'El ranking considera importe vencido, atraso, porcentaje vencido y concentración de deuda.';return 'La conciliación disponible es documental; no corresponde a una conciliación bancaria.'}
function render(data){feedback.className='notice';feedback.textContent=`Información calculada al ${date(data.as_of_date)}.`;let html=`<p class="narrative">${esc(narrative(data))}</p>${cards(data.metrics||{})}${statusLine(data.status||{})}`;if(data.operation==='portfolio_snapshot'){if(data.aging?.length)html+=aging(data.aging);if(data.findings?.length)html+=findings(data.findings)}if(data.operation==='customer_snapshot'){if(data.aging?.length)html+=aging(data.aging);if(data.findings?.length)html+=findings(data.findings);html+=customerInvoices(data.evidence||[])}if(data.operation==='invoice_trace'){if(data.findings?.length)html+=findings(data.findings);html+=invoiceDetail(data.evidence?.[0]||{})}if(data.operation==='collection_priorities'){html+=priorities(data.evidence||[],data);html+=`<details><summary>Cómo se calcula la prioridad</summary><p>El índice va de 0 a 100: Alta desde 60, Media desde 30 y Baja por debajo de 30.</p></details>`}if(data.operation==='reconciliation_exceptions')html+=exceptions(data.evidence||[],data);if(data.recommended_actions?.length)html+=actions(data.recommended_actions);html+=`<details><summary>Detalle técnico e integración (JSON)</summary><pre>${esc(JSON.stringify(data,null,2))}</pre></details>`;content.innerHTML=html;}
async function load(){state.asOf=document.querySelector('#asof').value;let path='/api/'+state.view+'?as_of_date='+encodeURIComponent(state.asOf);let entity=document.querySelector('#entity'),limit=document.querySelector('#limit');if(entity){if(state.view==='customer')state.customer=entity.value.trim();else state.invoice=entity.value.trim();path+='&id='+encodeURIComponent(entity.value.trim())}if(limit){state.limit=limit.value;path+='&limit='+encodeURIComponent(limit.value)}feedback.className='notice';feedback.textContent='Calculando resultado…';content.innerHTML='';try{let res=await fetch(path),data=await res.json();if(!res.ok)throw new Error(data.error||'No se pudo completar la consulta.');render(data)}catch(error){feedback.className='notice error';feedback.textContent=error.message||'Ocurrió un error inesperado.'}}
async function refreshConfig(){let data=await (await fetch('/api/config')).json(),badge=document.querySelector('#ai-status');badge.textContent=data.openai_enabled?`IA disponible (${data.model})`:'IA requiere OPENAI_API_KEY';badge.className='status '+(data.openai_enabled?'ready':'warn')}async function upload(){let files=document.querySelector('#files').files,result=document.querySelector('#upload-result');let form=new FormData();for(let file of files)form.append('files',file);result.className='notice';result.textContent='Validando archivos…';try{let res=await fetch('/api/uploads',{method:'POST',body:form}),data=await res.json();result.className='notice '+(res.ok?'success':'error');let accepted=(data.accepted_tables||[]).map(x=>`${x.file}: ${x.records} registros`).join(' · ');result.textContent=`${data.message||''}${accepted?` ${accepted}`:''}${data.errors?.length?` ${data.errors.join(' ')}`:''}`;if(res.ok){document.querySelector('#data-status').textContent='Archivos CSV temporales';document.querySelector('#data-status').className='status ready';load()}}catch(error){result.className='notice error';result.textContent='No se pudieron validar los archivos.'}}async function askAgent(){let question=document.querySelector('#question').value.trim(),answer=document.querySelector('#answer');if(!question){answer.className='answer';answer.textContent='Escribe una pregunta para el agente.';return}answer.className='answer';answer.textContent='Analizando consulta…';try{let res=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question})}),data=await res.json();if(!res.ok)throw new Error(data.error||'No se pudo completar la consulta con IA.');answer.textContent=data.answer||'La IA no devolvió una respuesta.'}catch(error){answer.textContent=error.message||'No fue posible usar la IA.'}}
document.querySelectorAll('.nav button').forEach(button=>button.onclick=()=>{state.view=button.dataset.view;document.querySelectorAll('.nav button').forEach(x=>x.classList.toggle('active',x===button));renderControls();load()});document.querySelector('#upload').onclick=upload;document.querySelector('#ask').onclick=askAgent;renderControls();refreshConfig();load();
</script></body></html>"""


class AppState:
    """Keeps the active in-memory dataset isolated to this local server process."""

    def __init__(self, service: CollectionsService):
        self._service = service
        self._lock = threading.RLock()

    def service(self) -> CollectionsService:
        with self._lock:
            return self._service

    def replace_service(self, service: CollectionsService) -> None:
        with self._lock:
            self._service = service


def route_payload(service: CollectionsService, path: str) -> tuple[int, dict]:
    """Map safe, fixed UI routes to deterministic service operations."""
    request = urlparse(path)
    params = parse_qs(request.query)
    as_of = params.get("as_of_date", [None])[0]
    entity = params.get("id", [""])[0]
    try:
        limit = max(1, min(50, int(params.get("limit", [10])[0])))
    except ValueError:
        return HTTPStatus.BAD_REQUEST, {"error": "La cantidad de casos debe ser un número entre 1 y 50."}
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
    state = AppState(service)

    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/" or self.path.startswith("/?"):
                body = PAGE.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.startswith("/api/config"):
                settings = Settings.from_env()
                return self._send_json(HTTPStatus.OK, {"openai_enabled": bool(os.environ.get("OPENAI_API_KEY")), "model": settings.model})
            if self.path.startswith("/api/"):
                status, payload = route_payload(state.service(), self.path)
                return self._send_json(status, payload)
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Ruta no encontrada."})

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/api/uploads":
                return self._upload()
            if self.path == "/api/ask":
                return self._ask()
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Ruta no encontrada."})

        def _upload(self) -> None:
            if not self.headers.get("Content-Type", "").startswith("multipart/form-data"):
                return self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Usa el selector de archivos CSV."})
            settings = Settings.from_env()
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length <= 0 or content_length > settings.max_upload_bytes + 64_000:
                    raise ValueError("La carga excede el tamaño máximo permitido.")
                form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers["Content-Type"]})
                values = form["files"] if "files" in form else []
                fields = values if isinstance(values, list) else [values]
                files = [(field.filename or "", field.file.read()) for field in fields if getattr(field, "filename", None)]
                dataset, report = load_uploaded_csvs(files, settings.max_upload_files, settings.max_upload_bytes)
            except (ValueError, OSError, KeyError) as error:
                return self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"No se pudieron leer los archivos: {error}"})
            payload = report.to_dict()
            if dataset is None:
                return self._send_json(HTTPStatus.BAD_REQUEST, payload)
            state.replace_service(CollectionsService.from_dataset(dataset))
            self._send_json(HTTPStatus.OK, payload)

        def _ask(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 20_000:
                    raise ValueError("La consulta debe tener entre 1 y 20 000 caracteres.")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                question = str(payload.get("question", ""))
                result = ask(state.service(), question)
                self._send_json(HTTPStatus.OK, result)
            except (ValueError, RuntimeError, json.JSONDecodeError) as error:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

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
