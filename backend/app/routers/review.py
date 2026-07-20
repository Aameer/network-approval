"""Single-page review: one run, all its fields under one id — the human-friendly view of
the RunAnswer rows. Renders them as ONE form (edit inline, revert/pull, see 'changed from X'),
then Approve / Execute. Styled to match the C3 Admin (starlette-admin) light theme."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_ADMIN = "/admin/site/list?page=1&amp;page_size=50&amp;search=&amp;order=id"

# Shared look — matches the admin's light content area (navy sidebar accent, white cards).
_CSS = """
*{box-sizing:border-box}
body{font:14.5px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
 background:#f3f4f6;color:#1f2937;margin:0}
.shell{display:flex;min-height:100vh}
.side{width:230px;background:#0f172a;color:#cbd5e1;flex:0 0 230px;padding:22px 0}
.side .brand{font-weight:700;color:#fff;font-size:16px;padding:0 22px 18px}
.side a{display:block;color:#cbd5e1;text-decoration:none;padding:9px 22px;font-size:14px}
.side a:hover{background:#1e293b;color:#fff}.side a.on{background:#1e293b;color:#fff;font-weight:600}
.main{flex:1;min-width:0;padding:26px 34px}
.top{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:20px}
h1{font-size:20px;margin:0;color:#111827}
.pill{font-size:11px;padding:3px 10px;border-radius:999px;background:#eef2ff;color:#3730a3;text-transform:uppercase;letter-spacing:.04em;font-weight:600}
.pill.st{background:#ecfdf5;color:#065f46}
a.link{color:#2563eb;text-decoration:none;font-size:13.5px}a.link:hover{text-decoration:underline}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.row{display:grid;grid-template-columns:200px 1fr 130px;gap:16px;padding:13px 18px;border-top:1px solid #f0f1f3;align-items:start}
.row:first-child{border-top:0}
.lab{font-weight:600;font-size:14px;color:#111827}
.key{color:#9ca3af;font-size:11px;font-family:ui-monospace,monospace;margin-top:2px;word-break:break-all;overflow-wrap:anywhere}
input{width:100%;font:inherit;padding:8px 11px;border:1px solid #d1d5db;border-radius:8px;background:#fff;color:#111827}
input:focus{outline:2px solid #93c5fd;border-color:#93c5fd}input:disabled{background:#f9fafb;color:#9ca3af}
.note{font-size:12px;margin-top:5px}.warn{color:#c2410c}.ok{color:#15803d}.mut{color:#9ca3af}.bad{color:#b91c1c}
.acts{display:inline-flex;gap:6px;margin-top:6px}
.mini{padding:3px 9px;font-size:12px;border:1px solid #d1d5db;border-radius:7px;background:#f9fafb;color:#374151;cursor:pointer}
.mini:hover{background:#f3f4f6}
.st{font-size:11px;text-align:right;padding-top:9px;font-weight:600}
.bar{position:sticky;bottom:0;background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:12px 16px;
 margin-top:18px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;box-shadow:0 -2px 8px rgba(0,0,0,.04)}
button.act{font:inherit;font-weight:600;padding:8px 16px;border-radius:9px;border:1px solid #d1d5db;background:#fff;color:#374151;cursor:pointer}
button.act:hover{background:#f9fafb}
button.act:disabled{opacity:.4;cursor:not-allowed}button.act:disabled:hover{background:#fff}
.mini:disabled{opacity:.4;cursor:not-allowed}
button.pri{background:#2563eb;border-color:#2563eb;color:#fff}button.pri:hover{background:#1d4ed8}
button.danger{border-color:#ef4444;color:#b91c1c}button.danger:hover{background:#fef2f2}
#msg{font-size:13px;color:#6b7280}
#out{white-space:pre-wrap;font-family:ui-monospace,monospace;font-size:12px;background:#0f172a;color:#e2e8f0;
 border-radius:10px;padding:14px;margin-top:14px;display:none;overflow:auto}
#feed{margin-top:14px;background:#0f172a;color:#cbd5e1;border-radius:10px;padding:12px 14px;max-height:280px;overflow:auto;font-size:12.5px;display:none}
.feedhd{color:#fca5a5;font-weight:700;margin-bottom:8px;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase}
.feedrow{padding:4px 0;border-top:1px solid #1e293b}
.fst{font-weight:700;margin-right:6px}.fst.ok{color:#4ade80}.fst.mut{color:#fbbf24}
.mut{color:#9ca3af}.card2{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px 18px;margin-bottom:10px;display:flex;gap:14px;align-items:center}
"""

_SIDE = """<div class="side">
 <div class="brand">C3 Admin</div>
 <a href="__ADMIN__">Sites</a>
 <a href="/admin/network/list">Networks</a>
 <a href="/admin/network-application/list">Network Applications</a>
 <a class="on" href="/review">✔ Approval Review</a>
 <a href="/reliability">📊 Reliability</a>
 <a href="/admin/workflow-run/list">Workflow Runs</a>
 <a href="/admin/billing-profile/list">Billing Profiles</a>
 <a href="/admin/network-credential/list">Network Credentials</a>
 <a href="/admin/site-secret/list">Site Secrets</a>
 <a href="/admin/audit-log/list">Audit Logs</a>
</div>""".replace("__ADMIN__", _ADMIN)

_INDEX = ("<!doctype html><html><head><meta charset='utf-8'><title>Approval Review</title>"
          "<meta name='viewport' content='width=device-width, initial-scale=1'><style>" + _CSS +
          "</style></head><body><div class='shell'>" + _SIDE +
          "<div class='main'><div class='top'><h1>Approval Review</h1></div>"
          "<div id='list' class='mut'>loading…</div></div></div>"
          "<script>"
          "fetch('/api/workflows').then(r=>r.json()).then(d=>{"
          " const el=document.getElementById('list');"
          " const runs=(d.runs||[]).filter(r=>r.kind==='apply');"
          " if(!runs.length){el.textContent='No sheets yet — Prepare one from Network Applications.';return}"
          # (JS) most recent successful (done) run per site/network is the re-run entry point
          " const latest={};"
          " runs.forEach(r=>{if(r.state==='done'){const k=(r.site+'|'+(r.network||'').toLowerCase());"
          "   if(!latest[k]||r.id>latest[k])latest[k]=r.id;}});"
          " const isLatest=r=>latest[r.site+'|'+(r.network||'').toLowerCase()]===r.id;"
          " el.innerHTML=runs.map(r=>`<div class='card2'${isLatest(r)?\" style='border-color:#86efac;background:#f0fdf4'\":''}><a class='link' href='/review/${r.id}'>"
          "  <b>#${r.id}</b> ${r.site} → ${r.network}</a>"
          "  <span class='pill'>${r.plan?.operation||r.kind}</span>"
          "  <span class='pill st'>${r.state}</span>"
          "  ${isLatest(r)?\"<span class='pill' style='background:#dcfce7;color:#166534'>★ latest success</span>\":''}"
          "  <a class='link' href='/reliability' style='margin-left:auto'>reliability ↗</a></div>`).join('');"
          "});</script></body></html>")

_PAGE = ("<!doctype html><html><head><meta charset='utf-8'><title>Review run __RID__</title>"
         "<meta name='viewport' content='width=device-width, initial-scale=1'><style>" + _CSS +
         "</style></head><body><div class='shell'>" + _SIDE + """<div class="main">
 <div style="margin-bottom:14px"><a class="link" href="/review">← All approval sheets</a></div>
 <div class="top"><h1 id="title">Run __RID__</h1><span class="pill" id="op"></span><span class="pill st" id="state"></span><span class="pill" id="latest" style="display:none;background:#dcfce7;color:#166534">★ latest successful run</span></div>
 <div id="feed"></div>
 <div class="card" id="rows"></div>
 <div class="bar">
  <button class="act pri" id="b_save" onclick="save()">Save edits</button>
  <button class="act" id="b_approve" onclick="approve()">✅ Approve</button>
  <button class="act danger" id="ex_live" onclick="execLive()">Execute LIVE</button>
  <button class="act pri" id="b_new" onclick="prepareNew()" style="display:none" title="Opens a fresh editable sheet pre-filled from the current state — your last changes carry forward. Keeps this run as the record of what was submitted.">✏️ Edit &amp; re-run</button>
  <span id="hint"></span>
  <span id="msg"></span>
 </div>
 <div id="out"></div>
</div></div>
<script>
const RID=__RID__; let ANS=[]; let RUN={};
const q=s=>document.querySelector(s);
function esc(s){return (s??'').toString().replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function noteHtml(a){
 const isPw=a.field_key.startsWith('password');
 if(isPw)return '<span class="note mut">from credential store (leased at submit)</span>';
 const v=(a.value??'').toString().trim(), live=(a.current_value??'').toString().trim();
 if(!v)return `<span class="note mut">not submitted${live?` · live: ${esc(live)}`:''}</span>`;
 if(v===live)return '<span class="note ok">✓ same as live</span>';
 return `<span class="note warn">changed from “${esc(a.current_value)||'—'}”</span>`;
}
async function load(){
 await fetch('/api/auth/dev-login',{method:'POST'}).catch(()=>{});
 const d=await (await fetch('/api/workflows/'+RID+'/answers')).json();
 q('#title').textContent=`#${d.run.id}  ${d.run.site} → ${d.run.network}`;
 q('#op').textContent=d.run.operation||d.run.kind; q('#state').textContent=d.run.state;
 RUN=d.run; ANS=d.answers;
 q('#rows').innerHTML=ANS.map(a=>{
  const isPw=a.field_key.startsWith('password');
  const inp=isPw?`<input disabled value="•••• (leased at execute)">`
    :`<input data-id="${a.id}" data-orig="${esc(a.value)}" data-default="${esc(a.default)}" data-live="${esc(a.current_value)}" value="${esc(a.value)}" placeholder="(empty)" oninput="upd(${a.id})">`;
  const acts=isPw?'':`<span class="acts"><button class="mini" onclick="setv(${a.id},'default')" title="Use the Billing Profile default value">use default</button><button class="mini" onclick="setv(${a.id},'live')" title="Use the value currently on the network">use live value</button></span>`;
  const stcls=a.status==='ready'?'ok':(a.status==='MISSING'||a.status==='INVALID')?'bad':'mut';
  return `<div class="row"><div><div class="lab">${esc(a.label)}${a.required?' *':''}</div><div class="key">${esc(a.field_key)}</div></div>
   <div>${inp}<div id="note-${a.id}">${noteHtml(a)}</div>${acts}</div><div class="st ${stcls}">${a.status}</div></div>`;
 }).join('');
 const st=d.run.state;
 const busy=['executing','running'].includes(st);
 const term=['done','failed','rejected','unverified'].includes(st);
 const editable=!busy&&!term;  // a done/unverified run is a read-only receipt
 const amber=(st==='unverified');
 const stp=q('#state');
 stp.style.background=busy?'#fef3c7':amber?'#fef3c7':term?(st==='done'?'#ecfdf5':'#fef2f2'):'#eef2ff';
 stp.style.color=busy?'#92400e':amber?'#92400e':term?(st==='done'?'#065f46':'#b91c1c'):'#3730a3';
 // fields are only editable while awaiting_approval / approved
 document.querySelectorAll('input[data-id]').forEach(i=>i.disabled=!editable);
 document.querySelectorAll('.mini').forEach(b=>b.disabled=!editable);
 q('#b_save').disabled=!editable;
 q('#b_approve').disabled=!editable||st==='approved';   // nothing to approve once approved
 q('#ex_live').disabled=st!=='approved';                 // LIVE ONLY after an explicit approval
 // Re-run is ONLY offered from the MOST RECENT successful run — never from a failed/unverified
 // attempt (that would carry a bad state forward) or a stale older success.
 const canRerun=!!d.run.is_latest_success;
 q('#latest').style.display=canRerun?'inline-block':'none';
 q('#b_new').style.display=canRerun?'inline-block':'none';
 const hint=q('#hint'); hint.innerHTML='';
 if(term&&!canRerun&&d.run.latest_success_id){
  hint.innerHTML=`↻ re-run from the <a class="link" href="/review/${d.run.latest_success_id}">latest successful run #${d.run.latest_success_id}</a>`;
 }
 if(busy){msg('⏳ executing on the network — wait for it to finish');startPoll();}
 else{stopPoll();
  if(st==='unverified')msg('⚠ NOT CONFIRMED on the network'+((d.run.unverified||[]).length?': '+(d.run.unverified).join(', '):'')+' — the account did not show the new value(s). Click “Edit & re-run”.');
  else if(term)msg('✔ verified & saved on the network — click “Edit & re-run” to change anything');
  else if(st==='awaiting_approval')msg('edit if needed → Approve → Execute LIVE');
  else if(st==='approved')msg('approved ✓ — ready to Execute LIVE (any edit needs re-approval)');
 }
}
let pollTimer=null;
function stopPoll(){if(pollTimer){clearInterval(pollTimer);pollTimer=null;}}
function renderFeed(d){
 const f=q('#feed'); if(!f) return;
 const acts=(d&&d.actions)||[];
 if(!acts.length){f.style.display='none';return;}
 f.style.display='block';
 f.innerHTML='<div class="feedhd">🔴 live · what the agent is doing on the network</div>'+
   acts.map(a=>`<div class="feedrow"><span class="fst ${a.status==='completed'?'ok':'mut'}">${a.status==='completed'?'✔':'…'}</span>${esc(a.reasoning||a.type||'')}</div>`).join('')+
   (d.recording
     ? `<div class="feedrow" style="margin-top:6px"><a class="link" href="${esc(d.recording)}" target="_blank">▶ open recording</a> <span style="color:#64748b">(partial while running · full after it finishes)</span></div>`
     : `<div class="feedrow" style="margin-top:6px;color:#64748b">▶ recording will appear shortly…</div>`);
 f.scrollTop=f.scrollHeight;
}
function startPoll(){
 if(pollTimer)return;
 const tick=async()=>{
  try{
   const [s,live]=await Promise.all([
     fetch('/api/workflows/'+RID+'/status').then(r=>r.json()),
     fetch('/api/workflows/'+RID+'/live').then(r=>r.json()).catch(()=>null)
   ]);
   renderFeed(live);
   if(['executing','running'].includes(s.state)){msg('⏳ executing on the network… ('+(s.skyvern||'running')+')');}
   else{stopPoll();msg('run '+s.state+(s.written_back?' · our records updated ✓':''));load();}
  }catch(e){}
 };
 tick();                       // fire immediately, don't wait 8s
 pollTimer=setInterval(tick,8000);
}
function ai(id){return ANS.find(a=>a.id===id)}
function upd(id){const i=q(`input[data-id="${id}"]`);const a=ai(id);a.value=i.value;q('#note-'+id).innerHTML=noteHtml(a)}
function setv(id,which){const i=q(`input[data-id="${id}"]`);i.value=(which==='default'?i.dataset.default:i.dataset.live)||'';upd(id)}
function edits(){const o={};document.querySelectorAll('input[data-id]').forEach(i=>{if(i.value!==i.dataset.orig)o[i.dataset.id]=i.value});return o}
async function save(){
 const u=edits(); if(!Object.keys(u).length){msg('nothing changed');return}
 const r=await fetch('/api/workflows/'+RID+'/answers',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({updates:u})});
 msg(r.ok?'saved ✓':'save failed'); load();
}
async function approve(){
 const r=await fetch('/api/workflows/'+RID+'/approve',{method:'POST'});
 const d=await r.json(); msg(r.ok?`approved ✓ (${d.state})`:'✗ '+(d.detail||'blocked')); load();
}
async function execLive(){
 if(Object.keys(edits()).length){msg('you have unsaved edits — Save first (that will require re-approval)');return}
 if(!confirm('Execute LIVE — this really submits to the network account. Continue?'))return;
 q('#ex_live').disabled=true; msg('submitting to the network…');
 const r=await fetch('/api/workflows/'+RID+'/execute?live=true',{method:'POST'});
 const d=await r.json();
 msg(r.ok?'submitted ✓ — executing on the network':'✗ '+(d.detail||'error'));
 load();
}
async function prepareNew(){
 msg('preparing a fresh sheet…');
 const r=await fetch('/api/workflows/apply',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({domain:RUN.site,network:RUN.network})});
 const d=await r.json();
 if(!r.ok){msg('✗ '+(d.detail||'error'));return}
 location.href='/review/'+d.workflow_id;
}
function msg(t){q('#msg').textContent=t}
load();
</script></body></html>""")


_REL_SIDE = _SIDE.replace('class="on" href="/review"', 'href="/review"') \
                 .replace('href="/reliability"', 'class="on" href="/reliability"')

_RELIABILITY = ("<!doctype html><html><head><meta charset='utf-8'><title>Reliability</title>"
    "<meta name='viewport' content='width=device-width, initial-scale=1'><style>" + _CSS +
    "table{width:100%;border-collapse:collapse;font-size:13.5px}"
    "th,td{text-align:left;padding:10px 12px;border-top:1px solid #f0f1f3}"
    "th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#6b7280;border-top:0}"
    "td.num{text-align:right;font-variant-numeric:tabular-nums}"
    ".eng{font-size:11px;padding:2px 8px;border-radius:999px;font-weight:600}"
    ".eng.script{background:#ecfdf5;color:#065f46}.eng.skyvern{background:#eff6ff;color:#1e40af}"
    ".kpi{display:flex;gap:14px;margin-bottom:18px;flex-wrap:wrap}"
    ".kpi .card2{flex-direction:column;align-items:flex-start;gap:2px;min-width:150px}"
    ".kpi b{font-size:24px;color:#111827}.kpi span{font-size:12px;color:#6b7280}"
    ".gd{color:#15803d;font-weight:600}.wn{color:#c2410c;font-weight:600}.rd{color:#b91c1c;font-weight:600}"
    "</style></head><body><div class='shell'>" + _REL_SIDE + """<div class="main">
 <div class="top"><h1>Reliability</h1><span class="pill">head / tail scorecard</span></div>
 <div id="kpi" class="kpi"></div>
 <div class="card"><table id="tbl"><thead><tr>
   <th>Network</th><th>Engine</th><th class='num'>Runs</th><th class='num'>Verified</th>
   <th class='num'>No-op</th><th class='num'>Unverified</th><th class='num'>Failed</th>
   <th class='num'>Success</th><th class='num'>Indep. verify</th><th class='num'>Avg time</th>
 </tr></thead><tbody id="body"></tbody></table></div>
 <div class="note mut" style="margin-top:14px">
  <b>Success</b> = verified + no-op (nothing to change). <b>Indep. verify</b> = we read the live
  account ourselves (deterministic) rather than trusting the agent's word — script engines are
  100% independent by construction. Skyvern rows fall back to the agent's read-back only when we
  have no script-reader for that network.
 </div>
</div></div>
<script>
const esc=s=>(s??'').toString().replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
const pc=p=>p>=90?'gd':p>=60?'wn':'rd';
fetch('/api/workflows/reliability').then(r=>r.json()).then(d=>{
 const t=d.totals||{};
 document.getElementById('kpi').innerHTML=
  `<div class='card2'><b>${t.runs||0}</b><span>live executions</span></div>`+
  `<div class='card2'><b class='${pc(t.success_pct||0)}'>${t.success_pct||0}%</b><span>overall success</span></div>`+
  `<div class='card2'><b>${t.networks||0}</b><span>networks</span></div>`;
 const rows=d.rows||[];
 const body=document.getElementById('body');
 if(!rows.length){body.innerHTML="<tr><td colspan='10' class='mut' style='padding:18px'>No live executions yet.</td></tr>";return;}
 body.innerHTML=rows.map(r=>`<tr>
   <td><a class='link' href='/review/${r.last_run}'>${esc(r.network)}</a></td>
   <td><span class='eng ${r.engine}'>${r.engine}</span></td>
   <td class='num'>${r.runs}</td>
   <td class='num'>${r.verified||''}</td><td class='num'>${r.noop||''}</td>
   <td class='num ${r.unverified?'wn':''}'>${r.unverified||''}</td>
   <td class='num ${r.failed?'rd':''}'>${r.failed||''}</td>
   <td class='num ${pc(r.success_pct)}'>${r.success_pct}%</td>
   <td class='num'>${r.independent_pct}%</td>
   <td class='num'>${r.avg_secs!=null?r.avg_secs+'s':'—'}</td></tr>`).join('');
});
</script></body></html>""")


@router.get("/reliability", response_class=HTMLResponse)
def reliability_page():
    return _RELIABILITY


@router.get("/review", response_class=HTMLResponse)
def review_index():
    return _INDEX


@router.get("/review/{run_id}", response_class=HTMLResponse)
def review_page(run_id: int):
    return _PAGE.replace("__RID__", str(run_id))
