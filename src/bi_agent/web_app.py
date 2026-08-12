"""Local, dependency-free and business-facing web UI for SON-IA BI."""

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
from .presentation import presentation_for
from .service import BIService
from .visuals import dashboard_spec


PAGE = r"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SON-IA | Inteligencia de Negocio</title><style>
:root{--blue:#019df4;--navy:#072d56;--ink:#10233d;--muted:#63728a;--bg:#f4f7fb;--line:#dce5ef;--green:#087f5b;--amber:#a85b00;--red:#bd303e}*{box-sizing:border-box}body{margin:0;background:var(--bg);font:15px/1.48 Inter,Segoe UI,Arial,sans-serif;color:var(--ink)}.shell{max-width:1320px;margin:auto;padding:25px 20px 48px}.hero{padding:28px 30px;border-radius:22px;background:linear-gradient(125deg,#062f5d,#019df4);color:#fff;box-shadow:0 14px 35px #0b477535}.eyebrow{font-size:12px;font-weight:800;letter-spacing:.12em;opacity:.8}.hero h1{font-size:31px;margin:4px 0}.hero p{margin:0;opacity:.93}.panel{background:#fff;border:1px solid var(--line);border-radius:18px;padding:21px;margin-top:18px;box-shadow:0 3px 15px #17365b0b}.controls{display:grid;grid-template-columns:210px 1fr auto;gap:12px;align-items:end}.field{display:grid;gap:5px}.field label{font-size:12px;font-weight:800;color:var(--muted)}input,textarea{font:inherit;border:1px solid #b9c7d7;border-radius:10px;padding:11px;min-height:43px}textarea{resize:vertical;min-height:50px}.primary,.chip{border:0;border-radius:10px;padding:11px 15px;background:var(--blue);color:#fff;font:inherit;font-weight:750;cursor:pointer}.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:13px}.chip{background:#e7f4fc;color:#075a93;padding:8px 11px;font-size:13px}.notice{margin-top:14px;background:#eaf7ff;border-left:4px solid var(--blue);padding:10px 13px;border-radius:5px}.notice.warn{background:#fff4e8;border-left-color:var(--amber)}.analysis{display:flex;justify-content:space-between;gap:15px;align-items:flex-start}.analysis h2{margin:0;font-size:22px}.analysis p{margin:4px 0 0;color:var(--muted)}.meta{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px}.badge{background:#e6eef8;border-radius:99px;padding:3px 9px;font-size:12px;font-weight:800}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:12px}.card{border:1px solid var(--line);border-radius:13px;padding:14px;background:#fff}.card span{color:var(--muted);font-size:12px;font-weight:800;display:block}.card strong{font-size:22px;display:block;margin-top:3px}.help{font-size:12px;color:var(--muted);margin:5px 0 0}.section{margin-top:23px}.section h2{font-size:17px;margin:0 0 3px}.section>p{margin:0 0 10px;color:var(--muted);font-size:13px}.insight,.alert,.action{border:1px solid var(--line);border-left:4px solid var(--blue);border-radius:10px;padding:12px 13px;margin:8px 0;background:#fff}.insight b,.alert b,.action b{display:block;margin-bottom:4px}.HIGH{border-left-color:var(--red)}.MEDIUM{border-left-color:var(--amber)}.LOW,.INFO{border-left-color:var(--green)}.alert{background:#fff7ef}.impact{color:var(--muted);margin-top:4px}.bars{display:grid;gap:9px}.barrow{display:grid;grid-template-columns:minmax(100px,210px) 1fr 150px;gap:8px;align-items:center;font-size:13px}.track{height:20px;background:#eaf0f6;border-radius:9px;overflow:hidden}.fill{height:100%;background:linear-gradient(90deg,#0c70bb,#019df4);border-radius:9px}.amount{font-weight:800;text-align:right}.amount small{font-weight:600;color:var(--muted)}.table{overflow:auto;border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;border-bottom:1px solid #edf1f5;padding:8px 9px;vertical-align:top}th{background:#f8fafc;color:#53647b;white-space:nowrap}details{margin-top:20px;border-top:1px solid var(--line);padding-top:14px}summary{font-weight:800;cursor:pointer}pre{white-space:pre-wrap;word-break:break-word;background:#10233d;color:#eef6ff;border-radius:10px;padding:13px;font-size:12px;max-height:460px;overflow:auto}.hidden{display:none}@media(max-width:760px){.shell{padding:14px}.hero{padding:21px}.hero h1{font-size:26px}.controls{grid-template-columns:1fr}.primary{width:100%}.analysis{display:block}.meta{justify-content:flex-start;margin-top:12px}.barrow{grid-template-columns:90px 1fr 90px}}
</style></head><body><main class="shell"><header class="hero"><div class="eyebrow">SON-IA · INTEGRATEL AGÉNTICA</div><h1>Inteligencia de Negocio</h1><p>Convierte la operación de ingresos en decisiones accionables.</p></header><section class="panel"><div class="controls"><div class="field"><label for="asof">Fecha de corte</label><input id="asof" type="date" value="2026-07-31"></div><div class="field"><label for="question">¿Qué quieres analizar?</label><textarea id="question" placeholder="Escribe una consulta de negocio…"></textarea></div><button class="primary" id="run">Analizar</button></div><div class="chips" id="chips"></div><div id="mode" class="notice">Cargando modo de análisis…</div></section><section class="panel hidden" id="result"><div class="analysis"><div><h2 id="analysis-title"></h2><p id="analysis-description"></p></div><div class="meta" id="meta"></div></div><div id="answer" class="notice"></div><div id="dashboard"></div><details><summary>Ver evidencia y trazabilidad técnica</summary><div id="trace"></div></details></section></main><script>
const demos=['¿Cómo está el ciclo de ingresos al 31 de julio?','¿Dónde está concentrado el saldo vencido?','¿Qué oportunidades de recupero tenemos?','¿Qué debería priorizar la gerencia?','¿Qué limitaciones tiene la información?'];const $=s=>document.querySelector(s);const esc=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function setup(){ $('#chips').innerHTML=demos.map(q=>`<button class="chip">${esc(q)}</button>`).join('');document.querySelectorAll('.chip').forEach((b,i)=>b.onclick=()=>{$('#question').value=demos[i];run()});$('#run').onclick=run;fetch('/api/status').then(r=>r.json()).then(x=>{$('#mode').textContent=x.llm_available?'Modo conversacional disponible: la IA selecciona un análisis verificable.':'Análisis basado en reglas verificables: la aplicación funciona sin configurar IA.';if(!x.llm_available)$('#mode').classList.add('warn')})}
function cards(kpis){if(!kpis?.length)return '';return `<section class="section"><h2>Indicadores clave</h2><p>Qué está ocurriendo al corte seleccionado.</p><div class="grid">${kpis.map(k=>`<div class="card"><span>${esc(k.label)}</span><strong>${esc(k.display_value)}</strong><p class="help">${esc(k.help)}</p></div>`).join('')}</div></section>`}
function chart(c){if(!c.data?.length)return '';let max=Math.max(...c.data.map(x=>Number(x.amount||0)),1);return `<section class="section"><h2>${esc(c.title)}</h2><p>${esc(c.description)}</p><div class="bars">${c.data.map(x=>`<div class="barrow"><span>${esc(x.label)}</span><div class="track"><div class="fill" style="width:${100*Number(x.amount||0)/max}%"></div></div><span class="amount">${esc(x.display_amount)}${x.display_share?` <small>· ${esc(x.display_share)}</small>`:''}</span></div>`).join('')}</div></section>`}
function table(c){if(!c.rows?.length)return '';return `<section class="section"><h2>${esc(c.title)}</h2><p>${esc(c.description)}</p><div class="table"><table><thead><tr>${c.columns.map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${c.rows.map(row=>`<tr>${row.map(x=>`<td>${esc(x)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></section>`}
function stories(items,title,kind){if(!items?.length)return '';return `<section class="section"><h2>${title}</h2><p>${kind==='insight'?'Qué significa para el negocio.':kind==='action'?'Qué recomendamos considerar.':'Qué limitación debe tenerse presente.'}</p>${items.map(x=>`<div class="${kind} ${esc(x.severity||'INFO')}"><b>${esc(x.title)}</b><div>${esc(x.detail)}</div>${x.impact?`<div class="impact">${esc(x.impact)}</div>`:''}</div>`).join('')}</section>`}
function dashboard(view){let out=cards(view.kpis);for(const c of view.components||[])out+=c.type==='table'?table(c):chart(c);out+=stories(view.findings,'Hallazgos','insight')+stories(view.recommended_actions,'Acciones recomendadas','action')+stories(view.alerts,'Alertas sobre la información','alert');return out}
async function run(){let question=$('#question').value.trim();if(!question){$('#question').focus();return}$('#run').disabled=true;$('#run').textContent='Analizando…';try{let r=await fetch('/api/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,as_of_date:$('#asof').value})});let data=await r.json();if(!r.ok)throw Error(data.error||'No se pudo completar la consulta.');let response=data.agent_response,view=data.presentation;$('#result').classList.remove('hidden');$('#analysis-title').textContent=view.analysis.title;$('#analysis-description').textContent=view.analysis.description;$('#meta').innerHTML=`<span class="badge">Corte: ${esc(view.analysis.as_of_date)}</span><span class="badge">Análisis basado en reglas verificables</span>`;$('#answer').textContent=data.answer;$('#dashboard').innerHTML=dashboard(view);$('#trace').innerHTML=`<p><b>Tool:</b> ${esc(data.tool_used)}</p><p><b>Modo:</b> ${esc(data.mode)}</p><p><b>Parámetros:</b> ${esc(JSON.stringify(data.tool_arguments))}</p><p><b>Metodología:</b> ${esc(JSON.stringify(response.methodology))}</p><p><b>Inputs:</b> ${esc(JSON.stringify(response.upstream_inputs))}</p><pre>${esc(JSON.stringify(response,null,2))}</pre>`}catch(e){$('#result').classList.remove('hidden');$('#answer').textContent=e.message;$('#dashboard').innerHTML=''}finally{$('#run').disabled=false;$('#run').textContent='Analizar'}}setup();
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
                result = ask(service, question, as_of, None)
                result["mode"] = "deterministic_fallback"
                result["runtime_warning"] = str(error)
            result["dashboard"] = dashboard_spec(result["agent_response"])
            result["presentation"] = presentation_for(result["agent_response"], result["dashboard"])
            return HTTPStatus.OK, result
        if request.path == "/api/tool":
            operation = params.get("operation", [""])[0]
            as_of = params.get("as_of_date", [""])[0]
            if operation not in TOOL_NAMES:
                return HTTPStatus.BAD_REQUEST, {"error": "Operación BI no autorizada."}
            payload = dispatch(service, operation, {}, as_of)
            dashboard = dashboard_spec(payload)
            result = {"answer": "Resultado determinístico solicitado.", "tool_used": operation, "tool_arguments": {"as_of_date": as_of}, "agent_response": payload, "mode": "deterministic", "dashboard": dashboard, "presentation": presentation_for(payload, dashboard)}
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
    parser = argparse.ArgumentParser(description="Interfaz local SON-IA BI Agent")
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
