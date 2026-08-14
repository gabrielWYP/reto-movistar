�r�^�f��ئ{N�y�'vî���const state={
  view:'portfolio',asOf:'2026-08-07',customer:'CLIENT_00385',invoice:'S1AA-0052403449',limit:'10'
};
const content=document.querySelector('#content'),controls=document.querySelector('#controls'),feedback=document.querySelector('#feedback');
 const labels={
  total_billed:'Facturado',total_paid_linked:'Pagos aplicados a facturas',credit_notes_linked:'Notas de crédito aplicadas',outstanding_balance:'Saldo pendiente',overdue_balance:'Saldo vencido',collection_ratio:'Cobranza aplicada / facturación',priority_score:'Índice de prioridad',exception_count:'Casos que requieren validación'
};
 const tips={
  total_billed:'Importe total de las facturas analizadas.',total_paid_linked:'Incluye únicamente pagos relacionados con una factura disponible en el corte.',outstanding_balance:'Importe por cobrar después de pagos y notas de crédito aplicados.',overdue_balance:'Parte del saldo pendiente cuya fecha de vencimiento ya pasó.',collection_ratio:'Pagos aplicados a facturas divididos entre el importe facturado.',priority_score:'Índice de 0 a 100. Alta: 60 a 100; Media: 30 a 59.9; Baja: menor a 30.',exception_count:'Casos para contrastar con el corte o sistema de origen; no son errores confirmados.'
};
 const statusLabels={
  priority:'Prioridad de gestión',collection_state:'Situación de cobranza',settlement:'Estado de pago',delinquency:'Situación de cobranza',reconciliation:'Aplicación de pagos'
};
const statusText={
  HIGH:'Alta',MEDIUM:'Media',LOW:'Baja',PAGADA:'Pagada',PAGO_PARCIAL:'Pago parcial',PENDIENTE:'Pendiente de pago',SALDO_A_FAVOR:'Saldo a favor por validar',VENCIDA:'Vencida',CRITICA:'Vencida por más de 90 días',NO_VENCIDA:'Pendiente, aún no vencida',NO_APLICA:'Sin saldo pendiente',CONCILIADA:'Pago aplicado completamente',PARCIALMENTE_CONCILIADA:'Pago aplicado parcialmente',PENDIENTE_DE_PAGO:'Sin pago aplicado',REQUIERE_REVISION:'Requiere validación'
};
const findingText={
  UNMATCHED_PAYMENT_CUTOFF:'Pago sin factura dentro del corte analizado',OVERDUE_EXPOSURE:'Saldo vencido que requiere gestión',OPEN_BALANCE:'Factura con saldo pendiente',OVERAPPLICATION:'Saldo a favor por validar',TEMPORAL_ANOMALY:'Fecha de pago por validar',PAYMENT_OUTSIDE_INVOICE_CUTOFF:'Pago sin factura dentro del corte',PAYMENT_BEFORE_ISSUANCE:'Fecha de pago por validar',DOCUMENT_SETTLED:'Documento sin incidencias detectadas'
};
const actionText={
  review_collection_priorities:'Revisar clientes prioritarios',review_unmatched_payments:'Validar pagos fuera del corte',contact_customer:'Contactar al cliente',monitor:'Mantener seguimiento',review_overapplication:'Validar saldo a favor',start_collection:'Iniciar gestión de cobranza',monitor_due_date:'Dar seguimiento al vencimiento',close_case:'No requiere gestión adicional',assign_collection_queue:'Asignar clientes prioritarios a gestión',review_exceptions:'Revisar casos de aplicación'
};
const bucketText={
  NO_VENCIDA:'Aún no vencida','1_30':'De 1 a 30 días vencida','31_60':'De 31 a 60 días vencida','61_90':'De 61 a 90 días vencida','90_PLUS':'Más de 90 días vencida',SIN_FECHA_VENCIMIENTO:'Sin fecha de vencimiento'
};
 function esc(v){
  return String(v??'—').replace(/[&<>"']/g,c=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}
function money(v){
  return typeof v==='number'?new Intl.NumberFormat('es-PE',{
    style:'currency',currency:'PEN'
  }).format(v):'—'
}
function date(v){
  if(!v)return 'No disponible';
  let p=String(v).split('-');
  return p.length===3?`${p[2]}/${p[1]}/${p[0]}`:String(v)
}
function percent(v){
  return typeof v==='number'?`${(v*100).toFixed(1)}%`:'—'
}
function whole(v){
  return typeof v==='number'?new Intl.NumberFormat('es-PE').format(v):'—'
}
function status(v){
  return `<span class="badge ${esc(v)}">${esc(statusText[v]||v)}</span>`
} function dateField(){
  return `<div class="field"><label for="asof">Fecha de corte</label><input id="asof" type="date" value="${esc(state.asOf)}"><p class="help">Los resultados no se actualizan en tiempo real.</p></div>`
}
function renderControls(){
  let form=dateField();
  if(state.view==='customer')form+=`<div class="field"><label for="entity">Código de cliente</label><input id="entity" value="${esc(state.customer)}" placeholder="Ej.: CLIENT_00385"></div>`;
  if(state.view==='invoice')form+=`<div class="field"><label for="entity">N.° de factura</label><input id="entity" value="${esc(state.invoice)}" placeholder="Ej.: S1AA-0052403449"></div>`;
  if(['priorities','exceptions'].includes(state.view))form+=`<div class="field"><label for="limit">Cantidad de casos a mostrar</label><input id="limit" type="number" min="1" max="50" value="${esc(state.limit)}"></div>`;
  controls.innerHTML=`<div class="controls">${form}<button class="primary" id="run">Consultar</button></div>`;
  document.querySelector('#run').onclick=load;
} function card(key,val){
  let text=key==='priority_score'?`${Number(val).toFixed(1)} / 100`:key==='collection_ratio'?percent(val):key==='exception_count'?whole(val):money(val);
  return `<div class="card" title="${esc(tips[key]||'')}"><span>${esc(labels[key]||key)}</span><strong>${text}</strong></div>`
}
function cards(metrics){
  let preferred=['total_billed','total_paid_linked','outstanding_balance','overdue_balance','collection_ratio','priority_score','exception_count'];
  return `<div class="cards">${preferred.filter(k=>k in metrics).map(k=>card(k,metrics[k])).join('')}</div>`
}
function table(headers,rows){
  if(!rows.length)return '<div class="empty">No hay registros para mostrar.</div>';
  return `<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th>${
    esc(h)
  }</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${
    row.map(cell=>`<td>${cell}</td>`).join('')
  }</tr>`).join('')}</tbody></table></div>`
} function aging(rows){
  return `<section class="section"><h2>Antigüedad de la deuda</h2><p class="section-intro">Agrupa el saldo pendiente según los días transcurridos desde el vencimiento.</p>${table(['Tramo de vencimiento','Facturas','Saldo pendiente'],rows.map(r=>[esc(bucketText[r.bucket]||r.bucket),whole(r.documents),money(r.outstanding_balance)]))}</section>`
}
function findings(rows){
  return `<section class="section"><h2>Situaciones identificadas</h2><p class="section-intro">Son hallazgos respaldados por el corte analizado; no reemplazan la validación operativa.</p>${table(['Situación','Nivel','Qué significa','Importe','Casos'],rows.map(r=>[esc(findingText[r.type]||r.type),status(r.severity),esc(r.message),r.amount==null?'—':money(r.amount),r.count==null?'—':whole(r.count)]))}</section>`
}
function actions(rows){
  return `<section class="section"><h2>Siguientes acciones recomendadas</h2><div class="action-list">${rows.map(r=>`<div class="action"><strong>${
    esc(actionText[r.action]||r.action)
  }</strong><span>${
    esc(r.reason||'')
  }</span>${
    r.priority?`<br>${status(r.priority)}`:''
  }</div>`).join('')}</div></section>`
} function customerInvoices(rows){
  let open=rows.filter(r=>r.outstanding_balance>0);
  return `<section class="section"><h2>Facturas por gestionar</h2><p class="section-intro">Se muestran únicamente documentos con saldo pendiente.</p>${table(['Factura','Vencimiento','Días de atraso','Importe facturado','Pagos aplicados','Saldo pendiente','Estado de pago','Aplicación de pagos'],open.map(r=>[esc(r.document),date(r.due_at),whole(r.days_past_due),money(r.invoice_total),money(r.paid),money(r.outstanding_balance),status(r.settlement_state),status(r.reconciliation_state)]))}</section>`
}
function invoiceDetail(r){
  let payments=r.payments||[],credits=r.credit_note_documents||[];
  let summary=`<section class="section"><h2>Resumen de la factura</h2>${table(['Cliente','Cuenta','Emisión','Vencimiento','Días de atraso','Importe facturado','Notas de crédito','Pagos aplicados','Saldo pendiente'],[[esc(r.customer),esc(r.account_code),date(r.issued_at),date(r.due_at),whole(r.days_past_due),money(r.invoice_total),money(r.credit_notes),money(r.paid),money(r.outstanding_balance)]])}</section>`;
  let pays=`<section class="section"><h2>Pagos aplicados a esta factura</h2>${table(['Fecha de pago','Importe aplicado','Cuenta'],payments.map(p=>[date(p.paid_at),money(p.amount),esc(p.account_code)]))}</section>`;
  let notes=credits.length?`<section class="section"><h2>Notas de crédito aplicadas</h2>${table(['Documento','Fecha de emisión','Importe'],credits.map(c=>[esc(c.document),date(c.issued_at),money(c.amount)]))}</section>`:'';
  return summary+pays+notes
}
function priorities(rows,data){
  return `<section class="section"><h2>Clientes a priorizar</h2><p class="section-intro">${whole(data.metrics.customers_ranked)} clientes tienen saldo pendiente. Se muestran ${whole(data.metrics.returned)} en orden de prioridad.</p>${table(['Posición','Cliente','Saldo pendiente','Saldo vencido','Mayor atraso','% del saldo vencido','Índice / 100','Prioridad'],rows.map((r,i)=>[whole(i+1),esc(r.customer),money(r.outstanding_balance),money(r.overdue_balance),whole(r.max_days_past_due),percent(r.overdue_share),`${
    Number(r.priority_score).toFixed(1)
  } / 100`,status(r.priority)]))}</section>`
}
function exceptions(rows,data){
  return `<section class="section"><h2>Casos para validar</h2><p class="section-intro">Se identificaron ${whole(data.metrics.exception_count)} casos; estos no son errores confirmados.</p>${table(['Situación','Prioridad','Factura','Cliente','Importe','Fecha de pago','Siguiente acción recomendada'],rows.map(r=>[esc(findingText[r.type]||r.type),status(r.severity),esc(r.document),esc(r.customer),r.amount==null?'—':money(r.amount),r.paid_at?date(r.paid_at):'—',esc(r.recommended_action)]))}</section>`
}
function statusLine(items){
  let shown=Object.entries(items).filter(([k])=>statusLabels[k]);
  return shown.length?`<div class="status-line"><span class="status-label">Estado:</span>${shown.map(([k,v])=>`<span>${
    esc(statusLabels[k])
  }: ${
    status(v)
  }</span>`).join('<span>·</span>')}</div>`:''
}
function narrative(data){
  let m=data.metrics||{
  },cut=date(data.as_of_date);
  if(data.operation==='portfolio_snapshot')return `Al ${cut}, la cartera mantiene ${money(m.outstanding_balance)} pendiente de cobro; ${money(m.overdue_balance)} ya está vencido.`;
  if(data.operation==='customer_snapshot')return m.overdue_balance>0?`Al ${cut}, este cliente tiene ${money(m.overdue_balance)} vencido.`:`Al ${cut}, este cliente no tiene saldo vencido.`;
  if(data.operation==='invoice_trace')return `Al ${cut}, esta factura conserva ${money(m.outstanding_balance)} pendiente.`;
  if(data.operation==='collection_priorities')return 'El ranking considera importe vencido, atraso, porcentaje vencido y concentración de deuda.';
  return 'La conciliación disponible es documental; no corresponde a una conciliación bancaria.'
} function render(data){
  feedback.className='notice';
  feedback.textContent=`Información calculada al ${date(data.as_of_date)}.`;
  let html=`<p class="narrative">${esc(narrative(data))}</p>${cards(data.metrics||{})}${statusLine(data.status||{})}`;
  if(data.operation==='portfolio_snapshot'){
    if(data.aging?.length)html+=aging(data.aging);
    if(data.findings?.length)html+=findings(data.findings)
  }if(data.operation==='customer_snapshot'){
    if(data.aging?.length)html+=aging(data.aging);
    if(data.findings?.length)html+=findings(data.findings);
    html+=customerInvoices(data.evidence||[])
  }if(data.operation==='invoice_trace'){
    if(data.findings?.length)html+=findings(data.findings);
    html+=invoiceDetail(data.evidence?.[0]||{
    })
  }if(data.operation==='collection_priorities'){
    html+=priorities(data.evidence||[],data);
    html+=`<details><summary>Cómo se calcula la prioridad</summary><p>El índice va de 0 a 100: Alta desde 60, Media desde 30 y Baja por debajo de 30.</p></details>`
  }if(data.operation==='reconciliation_exceptions')html+=exceptions(data.evidence||[],data);
  if(data.recommended_actions?.length)html+=actions(data.recommended_actions);
  html+=`<details><summary>Detalle técnico e integración (JSON)</summary><pre>${esc(JSON.stringify(data,null,2))}</pre></details>`;
  content.innerHTML=html;
} async function load(){
  state.asOf=document.querySelector('#asof').value;
  let path='/api/'+state.view+'?as_of_date='+encodeURIComponent(state.asOf);
  let entity=document.querySelector('#entity'),limit=document.querySelector('#limit');
  if(entity){
    if(state.view==='customer')state.customer=entity.value.trim();
    else state.invoice=entity.value.trim();
    path+='&id='+encodeURIComponent(entity.value.trim())
  }if(limit){
    state.limit=limit.value;
    path+='&limit='+encodeURIComponent(limit.value)
  }feedback.className='notice';
  feedback.textContent='Calculando resultado…';
  content.innerHTML='';
  try{
    let res=await fetch(path),data=await res.json();
    if(!res.ok)throw new Error(data.error||'No se pudo completar la consulta.');
    render(data)
  }catch(error){
    feedback.className='notice error';
    feedback.textContent=error.message||'Ocurrió un error inesperado.'
  }
} async function refreshConfig(){
  let data=await (await fetch('/api/config')).json(),badge=document.querySelector('#ai-status');
  badge.textContent=data.openai_enabled?`IA disponible (${data.model})`:'IA requiere OPENAI_API_KEY';
  badge.className='status '+(data.openai_enabled?'ready':'warn')
}
async function upload(){
  let files=document.querySelector('#files').files,result=document.querySelector('#upload-result');
  let form=new FormData();
  for(let file of files)form.append('files',file);
  result.className='notice';
  result.textContent='Validando archivos…';
  try{
    let res=await fetch('/api/uploads',{
      method:'POST',body:form
    }),data=await res.json();
    result.className='notice '+(res.ok?'success':'error');
    let accepted=(data.accepted_tables||[]).map(x=>`${x.file}: ${x.records} registros`).join(' · ');
    result.textContent=`${data.message||''}${accepted?` ${
      accepted
    }`:''}${data.errors?.length?` ${
      data.errors.join(' ')
    }`:''}`;
    if(res.ok){
      document.querySelector('#data-status').textContent='Archivos CSV temporales';
      document.querySelector('#data-status').className='status ready';
      load()
    }
  }catch(error){
    result.className='notice error';
    result.textContent='No se pudieron validar los archivos.'
  }
}
async function askAgent(){
  let question=document.querySelector('#question').value.trim(),answer=document.querySelector('#answer');
  if(!question){
    answer.className='answer';
    answer.textContent='Escribe una pregunta para el agente.';
    return
  }answer.className='answer';
  answer.textContent='Analizando consulta…';
  try{
    let res=await fetch('/api/ask',{
      method:'POST',headers:{
        'Content-Type':'application/json'
      },body:JSON.stringify({
        question
      })
    }),data=await res.json();
    if(!res.ok)throw new Error(data.error||'No se pudo completar la consulta con IA.');
    answer.textContent=data.answer||'La IA no devolvió una respuesta.'
  }catch(error){
    answer.textContent=error.message||'No fue posible usar la IA.'
  }
} document.querySelectorAll('.nav button').forEach(button=>button.onclick=()=>{
  state.view=button.dataset.view;
  document.querySelectorAll('.nav button').forEach(x=>x.classList.toggle('active',x===button));
  renderControls();
  load()
});
document.querySelector('#upload').onclick=upload;
document.querySelector('#ask').onclick=askAgent;
renderControls();
refreshConfig();
load();
