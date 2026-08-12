"""Local dependency-free demo UI for SON-IA BI Agent v1.0."""

from __future__ import annotations

import argparse
import json
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .agent import TOOL_NAMES, ask, dispatch
from .llm_runtime import OpenAIRuntime
from .service import BIService
from .visuals import dashboard_spec

PAGE = r"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SON-IA | Business Intelligence</title><style>
:root{--blue:#019df4;--navy:#072d56;--ink:#10233d;--muted:#63728a;--bg:#f4f7fb;--card:#fff;--line:#dce5ef;--green:#087f5b;--amber:#a85b00;--red:#bd303e}*{box-sizing:border-box}body{margin:0;background:var(--bg);font:15px/1.45 Inter,Segoe UI,Arial,sans-serif;color:var(--ink)}.shell{max-width:1320px;margin:auto;padding:25px 20px 48px}.hero{padding:28px 30px;border-radius:22px;background:linear-gradient(125deg,#062f5d,#019df4);color:#fff;box-shadow:0 14px 35px #0b477535}.eyebrow{font-size:12px;font-weight:800;letter-spacing:.12em;opacity:.8}.hero h1{font-size:31px;margin:4px 0}.hero p{margin:0;opacity:.93}.panel{background:#fff;border:1px solid var(--line);border-radius:18px;padding:21px;margin-top:18px;box-shadow:0 3px 15px #17365b0b}.controls{display:grid;grid-template-columns:210px 1fr auto;gap:12px;align-items:end}.field{display:grid;gap:5px}.field label{font-size:12px;font-weight:800;color:var(--muted)}input,textarea{font:inherit;border:1px solid #b9c7d7;border-radius:10px;padding:11px;min-height:43px}textarea{resize:vertical;min-height:50px}.primary,.chip{border:0;border-radius:10px;padding:11px 15px;background:var(--blue);color:#fff;font:inherit;font-weight:750;cursor:pointer}.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:13px}.chip{background:#e7f4fc;color:#075a93;padding:8px 11px;font-size:13px}.notice{margin-top:14px;background:#eaf7ff;border-left:4px solid var(--blue);padding:10px 13px;border-radius:5px}.notice.warn{background:#fff4e8;border-left-color:var(--amber)}.meta{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.badge{background:#e6eef8;border-radius:99px;padding:3px 9px;font-size:12px;font-weight:800}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(178px,1fr));gap:12px}.card{border:1px solid var(--line);border-radius:13px;padding:14px;background:#fff}.card span{color:var(--muted);font-size:12px;font-weight:800;display:block}.card strong{font-size:22px;display:block;margin-top:3px}.section{margin-top:20px}.section h2{font-size:17px;margin:0 0 8px}.insight,.alert,.action{border:1px solid var(--line);border-left:4px solid var(--blue);border-radius:10px;padding:12px 13px;margin:8px 0;background:#fff}.HIGH{border-left-color:var(--red)}.MEDIUM{border-left-color:var(--amber)}.LOW,.INFO{border-left-color:var(--green)}.alert{background:#fff7ef}.bars{display:grid;gap:8px}.barrow{display:grid;grid-template-columns:minmax(90px,180px) 1fr 75px;gap:8px;align-items:center;font-size:13px}.track{height:18px;background:#eaf0f6;border-radius:9px;overflow:hidden}.fill{height:100%;background:linear-gradient(90deg,#0c70bb,#019df4);border-radius:9px}.table{overflow:auto;border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;border-bottom:1px solid #edf1f5;padding:8px 9px;vertical-align:top}th{background:#f8fafc;color:#53647b;white-space:nowrap}details{margin-top:20px;border-top:1px solid var(--line);padding-top:14px}summary{font-weight:800;cursor:pointer}pre{white-space:pre-wrap;word-break:break-word;background:#10233d;color:#eef6ff;border-radius:10px;padding:13px;font-size:12px;max-height:460px;overflow:auto}.empty{color:var(--muted);padding:16px}.hidden{display:none}@media(max-width:760px){.shell{padding:14px}.hero{padding:21px}.hero h1{font-size:26px}.controls{grid-template-columns:1fr}.primary{width:100%}.barrow{grid-template-columns:90px 1fr 60px}}
</style></head><body><main class="shell"><header class="hero"><div class="eyebrow">SON-IA · INTEGRATEL AGÉNTICA</div><h1>Business Intelligence</h1><p>Convierte la operación de ingresos en decisiones accionables.</p></header><section class="panel"><div class="controls"><div class="field"><label for="asof">Fecha de corte</label><input id="asof" type="date" value="2026-07-31"></div><div class="field"><label for="question">¿Qué quieres analizar?</label><textarea id="question" placeholder="Escribe una consulta de negocio…"></textarea></div><button class="primary" id="run">Analizar</button></div><div class="chips" id="chips"></div><div id="mode" class="notice">Cargando modo de análisis…</div></section><section class="panel hidden" id="result"><div class="meta" id="meta"></div><div id="answer" class="notice"></div><div id="dashboard"></div><details><summary>Ver evidencia y trazabilidad</summary><div id="trace"></div></details></section></main><script>
const demos=['¿Cómo está el ciclo de ingresos al 31 de julio?','¿Dónde está concentrado el saldo vencido?','¿Qué oportunidades de recupero tenemos?','¿Qué debería priorizar la gerencia?','¿Qué limitaciones tiene la información?'];const $=s=>document.querySelector(s);const money=v=>typeof v==='number'?new Intl.NumberFormat('es-PE',{style:'currency',currency:'PEN'}).format(v):String(v??'—');const pct=v=>typeof v==='number'?(v*100).toFixed(1)+'%':'—';const esc=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function setup(){ $('#chips').innerHTML=demos.map(q=>`<button class="chip">${esc(q)}</button>`).join('');document.querySelectorAll('.chip').forEach((b,i)=>b.onclick=()=>{$('#question').value=demos[i];run()});$('#run').onclick=run;fetch('/api/status').then(r=>r.json()).then(x=>{$('#mode').textContent=x.llm_available?'Modo conversacional IA disponible: el modelo seleccionará una tool cerrada.':'Modo determinístico activo: las cinco tools y el dashboard funcionan sin API key.';if(!x.llm_available)$('#mode').classList.add('warn')})}
function cards(metrics){let keys=Object.keys(metrics).filter(k=>['total_billed','outstanding_balance','overdue_balance','collection_ratio','metric_total','exposure_total','addressable_exposure','top_n_customer_coverage','unmatched_payment_count','payments_after_as_of_count'].includes(k));return `<section class="section"><h2>Indicadores</h2><div class="grid">${keys.map(k=>`<div class="card"><span>${esc(k.replaceAll('_',' '))}</span><strong>${k.includes('share')||k.includes('coverage')||k.includes('ratio')?pct(metrics[k]):k.includes('count')?esc(metrics[k]):money(metrics[k])}</strong></div>`).join('')}</div></section>`}
function evidence(response,id){return (response.evidence||[]).find(x=>x.id===id)?.value||null}
function bars(data,amountKey){if(!Array.isArray(data)||!data.length)return '';let max=Math.max(...data.map(x=>Number(x[amountKey]||0)),1);return `<div class="bars">${data.map(x=>`<div class="barrow"><span>${esc(x.value||x.customer||x.bucket)}</span><div class="track"><div class="fill" style="width:${100*Number(x[amountKey]||0)/max}%"></div></div><b>${money(x[amountKey])}</b></div>`).join('')}</div>`}
function rows(data){if(!Array.isArray(data)||!data.length)return '<div class="empty">No hay detalle para mostrar.</div>';let keys=Object.keys(data[0]).filter(k=>!['dimension'].includes(k));return `<div class="table"><table><thead><tr>${keys.map(k=>`<th>${esc(k.replaceAll('_',' '))}</th>`).join('')}</tr></thead><tbody>${data.map(row=>`<tr>${keys.map(k=>`<td>${typeof row[k]==='number'&&(k.includes('balance')||k.includes('amount')||k==='metric_total')?money(row[k]):typeof row[k]==='number'&&k.includes('share')?pct(row[k]):esc(row[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}
function findings(items,title,kind){if(!items?.length)return '';return `<section class="section"><h2>${title}</h2>${items.map(x=>`<div class="${kind} ${esc(x.severity||'INFO')}"><b>${esc(x.finding||x.type||x.action)}</b><div>${esc(x.impact||x.message||x.reason||'')}</div>${x.evidence_refs?`<small>Evidencia: ${esc(x.evidence_refs.join(', '))}</small>`:''}</div>`).join('')}</section>`}
function dashboard(response,spec){let out=cards(response.metrics||{});for(const c of spec.components||[]){let data=c.data;if(c.type==='aging_bar'){out+=`<section class="section"><h2>Ageing de cartera</h2>${bars(data,'outstanding_balance')}</section>`}else if(c.type==='bar_chart'||c.type==='pareto_chart'){out+=`<section class="section"><h2>${c.type==='pareto_chart'?'Pareto de exposición':'Concentración'}</h2>${bars(data,'overdue_balance')}</section>`}else if(['ranking_table','opportunity_table','evidence_table'].includes(c.type)){out+=`<section class="section"><h2>${c.type==='opportunity_table'?'Oportunidades':'Detalle'}</h2>${rows(data)}</section>`}}out+=findings(response.findings,'Hallazgos','insight')+findings(response.recommended_actions,'Acciones recomendadas','action')+findings(response.alerts,'Alertas de calidad','alert');return out}
async function run(){let question=$('#question').value.trim();if(!question){$('#question').focus();return}$('#run').disabled=true;$('#run').textContent='Analizando…';try{let r=await fetch('/api/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,as_of_date:$('#asof').value})});let data=await r.json();if(!r.ok)throw Error(data.error||'No se pudo completar la consulta.');let response=data.agent_response;$('#result').classList.remove('hidden');$('#meta').innerHTML=`<span class="badge">Tool: ${esc(data.tool_used)}</span><span class="badge">Corte: ${esc(response.as_of_date)}</span><span class="badge">Modo: ${esc(data.mode)}</span>`;$('#answer').textContent=data.answer;$('#dashboard').innerHTML=dashboard(response,data.dashboard);$('#trace').innerHTML=`<p><b>Parámetros:</b> ${esc(JSON.stringify(data.tool_arguments))}</p><p><b>Metodología:</b> ${esc(JSON.stringify(response.methodology))}</p><p><b>Inputs:</b> ${esc(JSON.stringify(response.upstream_inputs))}</p><pre>${esc(JSON.stringify(response,null,2))}</pre>`}catch(e){$('#result').classList.remove('hidden');$('#answer').textContent=e.message;$('#dashboard').innerHTML='';}finally{$('#run').disabled=false;$('#run').textContent='Analizar'}}setup();
</script></body></html>"""


def route_payload(service: BIService, runtime: OpenAIRuntime, path: str, body: dict | None = None) -> tuple[int, dict]:
    request = urlparse(path)
    params = parse_qs(request.query)
    try:
        if request.path == "/api/status":
            return HTTPStatus.OK, {"llm_available": runtime.available, "mode": "llm" if runtime.available else "deterministic"}
        if request.path == "/api/query":
            payload = body or {}
            question, as_of = payload.get("question", ""), payload.get("as_of_date", "")
            try:
                result = ask(service, question, as_of, runtime)
            except RuntimeError as error:
                # A transient API failure does not prevent the deterministic demo.
                result = ask(service, question, as_of, None)
                result["mode"] = "deterministic_fallback"
                result["runtime_warning"] = str(error)
            result["dashboard"] = dashboard_spec(result["agent_response"])
            return HTTPStatus.OK, result
        if request.path == "/api/tool":
            operation = params.get("operation", [""])[0]
            as_of = params.get("as_of_date", [""])[0]
            if operation not in TOOL_NAMES:
                return HTTPStatus.BAD_REQUEST, {"error": "Operación BI no autorizada."}
            payload = dispatch(service, operation, {}, as_of)
            result = {"answer": "Resultado determinístico solicitado.", "tool_used": operation, "tool_arguments": {"as_of_date": as_of}, "agent_response": payload, "mode": "deterministic", "dashboard": dashboard_spec(payload)}
            return HTTPStatus.OK, result
        return HTTPStatus.NOT_FOUND, {"error": "Ruta no encontrada."}
    except (ValueError, KeyError, json.JSONDecodeError) as error:
        return HTTPStatus.BAD_REQUEST, {"error": str(error)}


def create_server(service: BIService, runtime: OpenAIRuntime, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: bytes, content_type: str) -> None:
            self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/" or self.path.startswith("/?"):
                self._send(HTTPStatus.OK, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            else:
                status, payload = route_payload(service, runtime, self.path)
                self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/query":
                self._send(HTTPStatus.NOT_FOUND, b'{"error":"Ruta no encontrada."}', "application/json; charset=utf-8"); return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 10_000:
                    raise ValueError("La solicitud es demasiado grande.")
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(body, dict):
                    raise ValueError("La solicitud debe ser JSON objeto.")
                status, payload = route_payload(service, runtime, self.path, body)
            except (ValueError, json.JSONDecodeError) as error:
                status, payload = HTTPStatus.BAD_REQUEST, {"error": str(error)}
            self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def log_message(self, format: str, *args: object) -> None:
            return
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Interfaz local SON-IA BI Agent v1.0")
    parser.add_argument("--dataset", type=Path, required=True, help="Directorio de los seis CSV o ZIP oficial")
    parser.add_argument("--port", type=int, default=8502)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    server = create_server(BIService(args.dataset), OpenAIRuntime(), args.port)
    url = f"http://127.0.0.1:{args.port}"
    print(f"SON-IA BI disponible en {url}")
    print("Modo IA opcional: configura OPENAI_API_KEY. Ctrl+C para detener.")
    if args.open: webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nServidor detenido.")
    finally: server.server_close()


if __name__ == "__main__":
    main()
