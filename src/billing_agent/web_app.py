"""Local, dependency-free web MVP for the deterministic Billing Assurance Agent."""

from __future__ import annotations

import argparse
import json
import logging
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .openai_runtime import OpenAIRuntime
from .presentation import presentation_for
from .runtime import BillingAgentRuntime, SessionContext
from .service import BillingService

LOG = logging.getLogger(__name__)

PAGE = r'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SON-IA | Billing Assurance</title><style>
:root{--blue:#019df4;--navy:#062f5d;--ink:#10233d;--muted:#607087;--bg:#f4f7fb;--line:#dce5ef;--green:#087f5b;--amber:#a85b00;--red:#bd303e;--soft:#e9f5fc}*{box-sizing:border-box}body{margin:0;background:var(--bg);font:15px/1.48 Inter,Segoe UI,Arial,sans-serif;color:var(--ink)}.shell{max-width:1360px;margin:auto;padding:24px 20px 48px}.hero{padding:27px 30px;border-radius:22px;background:linear-gradient(125deg,#062f5d,#019df4);color:#fff;box-shadow:0 14px 35px #0b477535}.eyebrow{font-size:12px;font-weight:800;letter-spacing:.12em;opacity:.85}.hero h1{font-size:31px;margin:4px 0}.hero p{margin:0;opacity:.94}.nav{display:flex;gap:6px;flex-wrap:wrap;margin:18px 0}.nav button,.chip{border:0;border-radius:10px;padding:9px 13px;background:#e3ebf5;color:#27415f;font:inherit;font-weight:800;cursor:pointer}.nav button.active{background:var(--navy);color:#fff}.panel{background:#fff;border:1px solid var(--line);border-radius:18px;padding:20px;margin-top:16px;box-shadow:0 3px 15px #17365b0b}.controls{display:grid;grid-template-columns:190px 1fr 1fr auto;gap:12px;align-items:end}.field{display:grid;gap:5px}.field label{font-size:12px;font-weight:800;color:var(--muted)}input{font:inherit;border:1px solid #b9c7d7;border-radius:10px;padding:10px;min-height:42px}.primary{border:0;border-radius:10px;padding:11px 15px;background:var(--blue);color:#fff;font:inherit;font-weight:800;cursor:pointer;min-height:42px}.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.chip{background:#e7f4fc;color:#075a93;font-size:12px}.notice{margin-top:14px;background:#eaf7ff;border-left:4px solid var(--blue);padding:10px 13px;border-radius:5px}.notice.error{background:#fff0f1;border-left-color:var(--red)}.notice.warn{background:#fff4e8;border-left-color:var(--amber)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:12px}.card{border:1px solid var(--line);border-radius:13px;padding:14px;background:#fff}.card span{color:var(--muted);font-size:12px;font-weight:800;display:block}.card strong{font-size:24px;display:block;margin-top:3px}.section{margin-top:23px}.section h2{font-size:18px;margin:0 0 3px}.section>p{margin:0 0 10px;color:var(--muted);font-size:13px}.finding{border:1px solid var(--line);border-left:4px solid var(--blue);border-radius:11px;padding:13px;margin:9px 0;background:#fff}.finding.HIGH{border-left-color:var(--red)}.finding.MEDIUM{border-left-color:var(--amber)}.finding.LOW,.finding.INFO{border-left-color:var(--green)}.finding h3{font-size:15px;margin:0 0 4px}.finding p{margin:0 0 7px;color:#465a74}.badge{display:inline-block;border-radius:99px;padding:3px 9px;font-size:12px;font-weight:800;background:#e6eef8}.badge.HIGH{color:#8c1722;background:#ffe7e9}.badge.MEDIUM{color:#8a4a00;background:#fff0d9}.badge.LOW,.badge.INFO{color:#076042;background:#e1f5ed}.table{overflow:auto;border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;border-bottom:1px solid #edf1f5;padding:9px;vertical-align:top}th{background:#f8fafc;color:#53647b;white-space:nowrap}.calc{display:grid;grid-template-columns:1fr 30px 1fr 30px 1fr;gap:8px;align-items:center;max-width:760px}.calc .value{border:1px solid var(--line);border-radius:12px;padding:13px}.calc .value span{display:block;font-size:12px;color:var(--muted);font-weight:800}.calc .value strong{font-size:21px}.operator{font-size:23px;text-align:center;color:var(--muted)}.flow{display:flex;align-items:stretch;gap:10px;flex-wrap:wrap}.flow .step{border:1px solid var(--line);border-radius:12px;padding:12px;min-width:170px;flex:1}.flow .arrow{align-self:center;font-size:22px;color:var(--blue)}details{margin-top:9px;border-top:1px solid var(--line);padding-top:9px}summary{font-weight:800;cursor:pointer;color:#1c527e}pre{white-space:pre-wrap;word-break:break-word;background:#10233d;color:#eef6ff;border-radius:10px;padding:13px;font-size:12px;max-height:440px;overflow:auto}.hidden{display:none}.meta{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}.account{margin:8px 0;padding:12px;border:1px solid var(--line);border-radius:11px;background:#fbfdff}.empty{border:1px dashed #b9c7d7;border-radius:12px;padding:17px;color:var(--muted)}@media(max-width:800px){.shell{padding:14px}.hero{padding:21px}.hero h1{font-size:26px}.controls{grid-template-columns:1fr}.primary{width:100%}.calc{grid-template-columns:1fr}.operator{display:none}}
</style></head><body><main class="shell"><header class="hero"><div class="eyebrow">SON-IA · INTEGRATEL AGÉNTICA</div><h1>Billing Assurance</h1><p>Gestión inteligente de excepciones de facturación, con evidencia y trazabilidad.</p></header><nav class="nav" aria-label="Módulos"><button class="active" data-view="summary">Resumen</button><button data-view="customer">Cliente</button><button data-view="invoice">Factura</button><button data-view="gaps">Quiebres de ciclo</button><button data-view="notes">Notas de crédito</button><button data-view="agent">Asistente SON-IA</button></nav><section class="panel"><div id="controls"></div><div id="suggestions" class="chips"></div><div id="feedback" class="notice">Cargando resumen…</div></section><section class="panel" id="result"><div id="content"></div></section></main><script>
const state={view:'summary',asOf:'',customer:'CLIENT_00434',account:'993722637',invoice:'S300-0256413',threshold:'0.25',question:'¿Qué debería revisar hoy?',mode:'Modo local determinístico'};const $=s=>document.querySelector(s),esc=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const money=v=>typeof v==='number'?new Intl.NumberFormat('es-PE',{style:'currency',currency:'PEN'}).format(v):'—';const whole=v=>typeof v==='number'?new Intl.NumberFormat('es-PE').format(v):'—';const pct=v=>typeof v==='number'?`${(v*100).toFixed(1)}%`:'—';const date=v=>v?String(v).split('-').reverse().join('/'):'—';
const demos={summary:[],customer:['CLIENT_00434 · cuenta 993722637'],invoice:['S300-0256413 · diferencia aritmética','FOBF-00121753 · moneda ausente','S7AA-0067926518 · importe cero'],gaps:['CLIENT_00434 · cuenta 993722637'],notes:['S1AA-0052649961 · NC material'],agent:['¿Qué debería revisar hoy?','Revisa la factura S300-0256413','Analiza CLIENT_00434','Busca quiebres de CLIENT_00434','Revisa las notas de crédito materiales']};
function controls(){let base=`<div class="field"><label>Fecha de corte</label><input id="asof" type="date" value="${esc(state.asOf)}"></div>`;if(state.view==='agent')base+=`<div class="field" style="grid-column:span 2"><label>Consulta al agente <small>(${esc(state.mode)})</small></label><input id="question" value="${esc(state.question)}" placeholder="Ej. Revisa la factura S300-0256413"></div>`;else if(state.view==='customer')base+=`<div class="field"><label>Cliente</label><input id="customer" value="${esc(state.customer)}"></div><div class="field"><label>Cuenta (opcional)</label><input id="account" value="${esc(state.account)}"></div>`;else if(state.view==='invoice')base+=`<div class="field"><label>N.º de factura</label><input id="invoice" value="${esc(state.invoice)}"></div>`;else if(state.view==='gaps')base+=`<div class="field"><label>Cliente (opcional)</label><input id="customer" value="${esc(state.customer)}"></div><div class="field"><label>Cuenta (opcional)</label><input id="account" value="${esc(state.account)}"></div>`;else if(state.view==='notes')base+=`<div class="field"><label>Factura (opcional)</label><input id="invoice" value="${esc(state.invoice==='S300-0256413'?'S1AA-0052649961':state.invoice)}"></div><div class="field"><label>Umbral de materialidad</label><input id="threshold" type="number" min="0" max="1" step="0.01" value="${esc(state.threshold)}"></div>`;base+=`<button class="primary" id="run">${state.view==='agent'?'Enviar consulta':'Consultar'}</button>`;$('#controls').innerHTML=`<div class="controls">${base}</div>`;$('#run').onclick=load;$('#suggestions').innerHTML=(demos[state.view]||[]).map((x,i)=>`<button class="chip" data-demo="${i}">${esc(x)}</button>`).join('');document.querySelectorAll('[data-demo]').forEach(b=>b.onclick=()=>applyDemo(demos[state.view][Number(b.dataset.demo)]));}
function applyDemo(text){if(state.view==='agent'){state.question=text}else{let id=text.split(' · ')[0];if(state.view==='invoice'){state.invoice=id}else if(state.view==='notes'){state.invoice=id}else{state.customer='CLIENT_00434';state.account='993722637'}};controls();load()}
function badge(severity,label){return `<span class="badge ${esc(severity||'INFO')}">${esc(label||severity||'Informativo')}</span>`}function kpi(label,value,help=''){return `<div class="card"><span>${esc(label)}</span><strong>${esc(value)}</strong>${help?`<small>${esc(help)}</small>`:''}</div>`}function findings(items){if(!items?.length)return '<div class="empty">No hay hallazgos en el alcance seleccionado.</div>';return items.map(x=>`<article class="finding ${esc(x.severity)}"><div class="meta">${badge(x.severity,x.severity_label)}<span class="badge">${esc(x.rule_category||'')}</span></div><h3>${esc(x.business_label||x.type)}</h3><p>${esc(x.message)}</p><p><b>Siguiente validación:</b> ${esc(x.recommended_validation||'Revisar evidencia disponible.')}</p><details><summary>Ver evidencia</summary><p><b>Regla:</b> ${esc(x.validation_rule||'—')}</p><p><b>Valor observado:</b> ${esc(JSON.stringify(x.observed_value??{}))}</p><p><b>Referencias:</b> ${esc((x.evidence_refs||[]).join(', '))}</p><p><b>Código técnico:</b> ${esc(x.technical_code||x.type)}</p></details></article>`).join('')}
function quality(q,p){if(!q)return '';let c=q.join_coverage||{};return `<section class="section"><h2>Calidad y alcance de los datos</h2><p>${esc(p.data_quality_message)}</p><div class="grid">${kpi('Identidad temporal',q.canonical_customer_key||'RAZON_SOCIAL')}${kpi('Cobertura factura ↔ planta',c.matched_share==null?'—':pct(c.matched_share))}${kpi('Cuentas sin planta enlazada',whole(c.unmatched_to_plant))}</div><details><summary>Ver limitaciones y trazabilidad de fuentes</summary><ul>${(q.known_limitations||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul><pre>${esc(JSON.stringify(q,null,2))}</pre></details></section>`}
function summary(data,p){let m=data.metrics||{}, e=m.exception_counts||{};return `<h2>Estado general de Facturación</h2><p>${esc(p.narrative)}</p><div class="grid">${kpi('Facturas analizadas',whole(m.invoice_documents))}${kpi('Notas de crédito',whole(m.credit_note_documents))}${kpi('NC materiales',whole(m.material_credit_note_count))}${kpi('Validaciones aritméticas',whole(e.ARITHMETIC_MISMATCH||0))}${kpi('Posibles quiebres',whole(m.cycle_gap_candidates))}${kpi('Planta sin evidencia de factura',whole(m.active_plant_without_invoice_candidates),'Señal exploratoria')}</div><section class="section"><h2>¿Qué requiere atención?</h2><p>Priorización basada en las reglas ya ejecutadas por el agente.</p>${findings(p.findings)}</section>${quality(data.data_quality,p)}`}
function customer(data,p){let m=data.metrics||{}, plants=(data.evidence||[]).filter(x=>x.type==='plant'), invoices=(data.evidence||[]).filter(x=>x.type==='invoice'), notes=(data.evidence||[]).filter(x=>x.type==='credit_note');return `<h2>Billing 360 · ${esc(data.entity.id)}</h2><div class="meta">${badge(data.status.billing_assurance,p.status_labels.billing_assurance)}</div><p>${esc(p.narrative)}</p><div class="grid">${kpi('Cuentas en alcance',whole(m.account_count))}${kpi('Facturas',whole(m.invoice_count))}${kpi('Notas de crédito',whole(m.credit_note_count))}${kpi('Hallazgos',whole(p.findings.length))}</div><section class="section"><h2>Cuentas y planta</h2>${plants.map(x=>{let rows=x.value||[];return `<div class="account"><b>Cuenta ${esc(String(x.id).replace('plant:',''))}</b><p>${rows.length?rows.map(r=>`${esc(r.plant_type==='fixed'?'Planta fija':'Planta móvil')} · ${esc(r.fixed_status||r.mobile_status||'Estado no informado')} · ${esc(r.plan||'Plan no informado')}`).join('<br>'):'Sin planta enlazada en el extracto.'}</p></div>`}).join('')||'<div class="empty">No hay cuentas de planta en el alcance.</div>'}</section><section class="section"><h2>Documentos</h2><div class="table"><table><thead><tr><th>Factura</th><th>Cuenta</th><th>Emisión</th><th>Sistema</th><th>Total</th></tr></thead><tbody>${invoices.map(x=>{let r=x.value;return `<tr><td>${esc(r.document)}</td><td>${esc(r.account)}</td><td>${date(r.issued_at)}</td><td>${esc(r.system)}</td><td>${money(r.total)}</td></tr>`}).join('')||'<tr><td colspan="5">Sin facturas en el alcance.</td></tr>'}</tbody></table></div></section><section class="section"><h2>Hallazgos y acciones</h2>${findings(p.findings)}</section>${quality(data.data_quality,p)}`}
function invoice(data,p){let inv=(data.evidence||[]).find(x=>x.type==='invoice')?.value||{},m=data.metrics||{}, notes=(data.evidence||[]).filter(x=>x.type==='credit_note');let mismatch=p.findings.find(x=>x.type==='ARITHMETIC_MISMATCH');return `<h2>Factura ${esc(inv.document||data.entity.id)}</h2><div class="meta">${badge(data.status.billing_assurance,p.status_labels.billing_assurance)}</div><div class="table"><table><tbody><tr><th>Cliente</th><td>${esc(inv.customer)}</td><th>Cuenta</th><td>${esc(inv.account)}</td></tr><tr><th>Sistema</th><td>${esc(inv.system)}</td><th>Fuente</th><td>${esc(inv.source)}</td></tr><tr><th>Emisión</th><td>${date(inv.issued_at)}</td><th>Vencimiento</th><td>${date(inv.due_at)}</td></tr><tr><th>Moneda</th><td>${esc(inv.currency)}</td><th>Total registrado</th><td>${money(inv.total)}</td></tr></tbody></table></div><section class="section"><h2>Control del cálculo</h2><div class="calc"><div class="value"><span>Neto</span><strong>${money(m.net)}</strong></div><div class="operator">+</div><div class="value"><span>IGV</span><strong>${money(m.tax)}</strong></div><div class="operator">=</div><div class="value"><span>Total derivado</span><strong>${money(m.derived_total)}</strong></div></div><p><b>Total registrado:</b> ${money(m.reported_total)} · <b>Diferencia:</b> ${money(Math.abs(m.difference||0))} · <b>Tolerancia:</b> S/ 0.01</p>${mismatch?`<div class="notice warn">El total registrado difiere del total derivado por encima de la tolerancia. Se recomienda validar la regla de redondeo o cálculo en el sistema de origen.</div>`:''}</section>${notes.length?`<section class="section"><h2>Ajustes post-emisión</h2><div class="flow"><div class="step"><b>Factura original</b><br>${money(inv.total)}</div><div class="arrow">→</div>${notes.map(x=>`<div class="step"><b>Nota de crédito ${esc(x.value.document)}</b><br>${money(x.value.total)}<br>${date(x.value.issued_at)}</div>`).join('')}</div></section>`:''}<section class="section"><h2>Hallazgos y evidencia</h2>${findings(p.findings)}</section>${quality(data.data_quality,p)}`}
function gaps(data,p){let records=(data.evidence||[]).filter(x=>x.type==='cycle_gap');return `<h2>Posibles quiebres documentales</h2><p>${esc(p.narrative)}</p><div class="table"><table><thead><tr><th>Cliente</th><th>Cuenta</th><th>Anterior</th><th>Periodo sin documento</th><th>Posterior</th><th>Acción</th></tr></thead><tbody>${records.map(x=>{let r=x.value;return `<tr><td>${esc(r.customer)}</td><td>${esc(r.account)}</td><td>${esc(r.before_period)}<br><small>${esc(r.before_document)}</small></td><td><b>${esc(r.missing_period)}</b><br><small>Sin evidencia de factura</small></td><td>${esc(r.after_period)}<br><small>${esc(r.after_document)}</small></td><td>Requiere validación</td></tr>`}).join('')||'<tr><td colspan="6">No hay candidatos en este alcance.</td></tr>'}</tbody></table></div><section class="section"><h2>Hallazgos y acciones</h2>${findings(p.findings)}</section>${quality(data.data_quality,p)}`}
function notes(data,p){let pairs=[];for(let n of (data.evidence||[]).filter(x=>x.type==='credit_note')){let invoice=(data.evidence||[]).find(x=>x.id===`invoice:${n.value.affected_invoice}`)?.value||{};let material=p.findings.find(x=>x.type==='MATERIAL_CREDIT_NOTE'&&x.evidence_refs?.includes(n.id));pairs.push({n:n.value,i:invoice,material})}return `<h2>Ajustes post-emisión</h2><p>${esc(p.narrative)}</p><div class="table"><table><thead><tr><th>Cliente</th><th>Cuenta</th><th>Factura</th><th>Monto factura</th><th>Nota de crédito</th><th>Monto NC</th><th>Ratio</th><th>Revisión</th></tr></thead><tbody>${pairs.map(x=>`<tr><td>${esc(x.i.customer||x.n.customer)}</td><td>${esc(x.i.account||x.n.account)}</td><td>${esc(x.i.document||x.n.affected_invoice)}</td><td>${money(x.i.total)}</td><td>${esc(x.n.document)}</td><td>${money(x.n.total)}</td><td>${pct(x.material?.observed_value?.ratio)}</td><td>${x.material?badge(x.material.severity,x.material.severity_label):'Por debajo del umbral'}</td></tr>`).join('')||'<tr><td colspan="8">No hay notas de crédito en el alcance.</td></tr>'}</tbody></table></div><p class="notice">El umbral de materialidad es un criterio heurístico del MVP: 25% para revisión media y 50% para revisión alta.</p><section class="section"><h2>Hallazgos y evidencia</h2>${findings(p.findings)}</section>${quality(data.data_quality,p)}`}
function conversation(result){let trace=result.trace||{},refs=(trace.evidence_refs||[]).join(', ')||'Sin referencias para esta respuesta';return `<h2>Asistente SON-IA · Facturación</h2><p class="notice"><b>Tu consulta:</b> ${esc(state.question)}</p><section class="section"><h2>Respuesta</h2><p style="white-space:pre-line">${esc(result.answer)}</p></section><section class="section"><h2>Resultado de la orquestación</h2><div class="meta">${badge(result.status,result.status?.replaceAll('_',' '))}${result.tool?`<span class="badge">Tool ejecutada: ${esc(result.tool)}</span>`:''}${result.target_agent?`<span class="badge">Derivación: ${esc(result.target_agent)}</span>`:''}</div><details><summary>Ver razonamiento operativo</summary><p><b>Intent:</b> ${esc(trace.intent||result.intent)}</p><p><b>Router:</b> ${esc(trace.router||result.route)}</p><p><b>Tool:</b> ${esc(trace.tool||result.tool||'No ejecutada')}</p><p><b>Argumentos:</b> ${esc(JSON.stringify(trace.arguments||result.arguments||{}))}</p><p><b>Resultado:</b> ${esc(trace.status||result.status)}</p><p><b>Evidence refs:</b> ${esc(refs)}</p><p><b>Tiempo:</b> ${esc(trace.elapsed_ms??'—')} ms</p></details></section>${result.agent_response?`<details><summary>Ver trazabilidad técnica de la tool</summary><pre>${esc(JSON.stringify(result.agent_response,null,2))}</pre></details>`:''}`}
function render(response){let data=response.agent_response,p=response.presentation;$('#feedback').className='notice';$('#feedback').textContent=`Corte: ${date(data.as_of_date)} · ${p.status_labels.billing_assurance||'Resultado disponible'}`;let view={summary,customer,invoice,gaps,notes}[state.view];$('#content').innerHTML=view(data,p)+`<details><summary>Ver trazabilidad técnica completa</summary><pre>${esc(JSON.stringify(data,null,2))}</pre></details>`}
function path(){let q=new URLSearchParams({as_of_date:state.asOf});if(state.view==='summary')return '/api/health?'+q;if(state.view==='customer'){q.set('customer_id',state.customer);if(state.account)q.set('account_id',state.account);return '/api/customer?'+q}if(state.view==='invoice'){q.set('invoice_id',state.invoice);return '/api/invoice?'+q}if(state.view==='gaps'){if(state.customer)q.set('customer_id',state.customer);if(state.account)q.set('account_id',state.account);return '/api/gaps?'+q}if(state.invoice)q.set('invoice_id',state.invoice);q.set('materiality_threshold',state.threshold);return '/api/credit-notes?'+q}
async function askAgent(){state.question=$('#question').value.trim();$('#feedback').className='notice';$('#feedback').textContent='El agente está seleccionando una validación autorizada…';try{let r=await fetch('/api/conversation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:state.question,as_of_date:state.asOf})});let j=await r.json();if(!r.ok)throw Error(j.error||'No se pudo completar la consulta.');$('#feedback').textContent=`${state.mode} · ${j.tool?`Tool: ${j.tool}`:'Sin tool ejecutada'}`;$('#content').innerHTML=conversation(j)}catch(e){$('#feedback').className='notice error';$('#feedback').textContent=e.message||'Ocurrió un error inesperado.';$('#content').innerHTML='<div class="empty">Revisa la pregunta o intenta nuevamente.</div>'}}
async function load(){state.asOf=$('#asof').value;if(state.view==='agent')return askAgent();for(let k of ['customer','account','invoice','threshold']){let e=$('#'+k);if(e)state[k]=e.value.trim()}$('#feedback').className='notice';$('#feedback').textContent='Analizando evidencia disponible…';try{let r=await fetch(path());let j=await r.json();if(!r.ok)throw Error(j.error||'No se pudo completar la consulta.');render(j)}catch(e){$('#feedback').className='notice error';$('#feedback').textContent=e.message||'Ocurrió un error inesperado.';$('#content').innerHTML='<div class="empty">Revisa los datos ingresados o intenta nuevamente.</div>'}}
document.querySelectorAll('.nav button').forEach(b=>b.onclick=()=>{state.view=b.dataset.view;document.querySelectorAll('.nav button').forEach(x=>x.classList.toggle('active',x===b));controls();load()});async function initialize(){try{let r=await fetch('/api/status'),j=await r.json();if(r.ok&&j.default_as_of_date)state.asOf=j.default_as_of_date;if(r.ok&&j.llm_available)state.mode='Modo IA: LLM + tools'}catch(e){}controls();load()}initialize();
</script></body></html>'''


def _query_value(params: dict[str, list[str]], name: str) -> str | None:
    value = params.get(name, [None])[0]
    return value.strip() if isinstance(value, str) and value.strip() else None


def route_payload(service: BillingService, path: str) -> tuple[int, dict]:
    request = urlparse(path)
    params = parse_qs(request.query)
    as_of = _query_value(params, "as_of_date")
    try:
        routes = {
            "/api/status": lambda: {"status": "ok", "agent": "billing", "llm_available": False, "default_as_of_date": service.default_as_of_date().isoformat()},
            "/api/health": lambda: service.billing_health_snapshot(as_of),
            "/api/customer": lambda: service.customer_billing_check(_query_value(params, "customer_id") or "", _query_value(params, "account_id"), as_of),
            "/api/invoice": lambda: service.invoice_quality_check(_query_value(params, "invoice_id") or "", as_of),
            "/api/gaps": lambda: service.billing_cycle_gaps(as_of, _query_value(params, "customer_id"), _query_value(params, "account_id")),
            "/api/credit-notes": lambda: service.credit_note_review(as_of, _query_value(params, "customer_id"), _query_value(params, "account_id"), _query_value(params, "invoice_id"), _query_value(params, "materiality_threshold") or "0.25"),
        }
        if request.path not in routes:
            return HTTPStatus.NOT_FOUND, {"error": "Ruta no encontrada."}
        payload = routes[request.path]()
        if request.path == "/api/status":
            return HTTPStatus.OK, payload
        return HTTPStatus.OK, {"agent_response": payload, "presentation": presentation_for(payload)}
    except (KeyError, ValueError) as error:
        return HTTPStatus.BAD_REQUEST, {"error": str(error)}
    except Exception:
        LOG.exception("Unexpected billing web error")
        return HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "No se pudo completar la consulta. Revisa el dataset o intenta nuevamente."}


def create_server(service: BillingService, port: int = 8503) -> ThreadingHTTPServer:
    """Bind only to localhost to keep the demonstration local."""
    runtime = BillingAgentRuntime(service, OpenAIRuntime())
    session = SessionContext()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/" or self.path.startswith("/?"):
                self._send(HTTPStatus.OK, PAGE.encode("utf-8"), "text/html; charset=utf-8")
                return
            if self.path == "/api/status":
                body = {
                    "status": "ok", "agent": "billing", "llm_available": runtime.llm.available if runtime.llm else False,
                    "default_as_of_date": service.default_as_of_date().isoformat(),
                }
                self._send(HTTPStatus.OK, json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                return
            status, payload = route_payload(service, self.path)
            self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/conversation":
                self._send(HTTPStatus.NOT_FOUND, b'{"error":"Ruta no encontrada."}', "application/json; charset=utf-8")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ValueError("La consulta debe ser un JSON de hasta 4096 bytes.")
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(body, dict):
                    raise ValueError("El cuerpo debe ser un objeto JSON.")
                result = runtime.ask(body.get("question", ""), session, body.get("as_of_date"))
                self._send(HTTPStatus.OK, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                self._send(HTTPStatus.BAD_REQUEST, json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception:
                LOG.exception("Unexpected billing conversation error")
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, b'{"error":"No se pudo completar la consulta. Intenta nuevamente."}', "application/json; charset=utf-8")

        def log_message(self, format: str, *args: object) -> None:
            LOG.info("%s - %s", self.address_string(), format % args)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Interfaz local SON-IA Billing Assurance")
    parser.add_argument("--dataset", required=True, type=Path, help="Directorio de los cinco CSV o ZIP oficial")
    parser.add_argument("--port", type=int, default=8503)
    parser.add_argument("--open", action="store_true", help="Abrir el navegador al iniciar")
    args = parser.parse_args()
    try:
        service = BillingService(args.dataset)
    except (ValueError, OSError) as error:
        raise SystemExit(f"No se pudo cargar el dataset: {error}") from error
    server = create_server(service, args.port)
    url = f"http://127.0.0.1:{args.port}"
    print(f"SON-IA Billing Assurance disponible en {url}")
    print("Aplicación local; el router determinístico está disponible con o sin LLM. Presiona Ctrl+C para detener.")
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
