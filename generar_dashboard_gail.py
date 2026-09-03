#!/usr/bin/env python3
"""Genera dashboard-evaluacion-gail.html — evaluación completa GAIL (45 llamadas reales).

Consolida heurísticas del pipeline + los 7 jueces, todo embebido (sin CDN, offline).
"""
import json, math
import html as H

EV = 'gail_masivo/evaluacion'

REG = ["se_presenta","menciona_proposito","pide_consentimiento","maneja_no_interes",
       "ofrece_agendar_cita","listado_max_3","tono_respetuoso"]
REG_ES = {
 'se_presenta':'Se presenta', 'menciona_proposito':'Menciona propósito',
 'pide_consentimiento':'Pide consentimiento','maneja_no_interes':'Maneja no-interés',
 'ofrece_agendar_cita':'Ofrece agendar cita','listado_max_3':'Listado máx 3',
 'tono_respetuoso':'Tono respetuoso'}

def carga(nombre):
    try:
        d = json.load(open(f"{EV}/{nombre}_resultados.json"))
        return d.get('llamadas', []) if isinstance(d, dict) else d
    except Exception:
        return []

def scores_de(ll, regla):
    s = ll.get('scores', {}).get(regla, {})
    return round(s.get('value', 0), 2) if isinstance(s, dict) else round(s if s is not None else 0, 2)

JUECES = ['deepeval','langsmith','opik','promptfoo','juez2_coder','juez3_cloud','gemini']
J_ETIQ = {
 'deepeval':'qwen7b · \nDeepEval','langsmith':'qwen7b · \nLangSmith','opik':'qwen7b · \nOpik',
 'promptfoo':'promptfoo','juez2_coder':'qwen-coder\njuez2','juez3_cloud':'gpt-oss\njuez3','gemini':'★Gemini\nref'}
J_VALIDOS = ['deepeval','langsmith','opik','juez2_coder','gemini']  # los confiables
J_COLOR = {'deepeval':'#3b82f6','langsmith':'#8b5cf6','opik':'#6366f1','juez2_coder':'#a855f7','gemini':'#22c55e'}

data = {j: carga(j) for j in JUECES}
idx = {j: {x['id']: x for x in data[j]} for j in JUECES}

# Heurísticas del pipeline
masivo = json.load(open(f"{EV}/resultados_masivos.json"))
HEUR = masivo['resumen']['heur']
LLM_PIPE = masivo['resumen']['llm']

# Fuente para metadata (campaign, outcome, duration)
FUENTE = json.load(open('gail_masivo/data/llamadas_gail.json'))
mids = {x['id']: x.get('metadata', {}) for x in FUENTE}

# Consolidar por llamada
llamadas = []
for cid, meta in mids.items():
    row = {'id': cid, 'campaign': meta.get('campaign','?'), 'outcome': meta.get('outcome',''),
           'contacto': meta.get('contacto',''), 'duration': meta.get('duration',0), 'scores': {}}
    for j in JUECES:
        e = idx[j].get(cid)
        if e:
            row['scores'][j] = {r: scores_de(e, r) for r in REG}
    llamadas.append(row)

def pearson(a, b):
    n=len(a); ma=sum(a)/n; mb=sum(b)/n
    num=sum((x-ma)*(y-mb) for x,y in zip(a,b))
    da=sum((x-ma)**2 for x in a); db=sum((y-mb)**2 for y in b)
    return round(num/math.sqrt(da*db),3) if da and db else 0

# Promedios por juez
prom = {}
for j in JUECES:
    vals = [row['scores'][j][r] for row in llamadas for r in REG if j in row['scores']]
    prom[j] = round(sum(vals)/len(vals),3) if vals else None

# Correlación matriz (con los que tienen datos de todas las llamadas)
corr = {}
validos_para_corr = [j for j in JUECES if prom[j] is not None]
for a in validos_para_corr:
    for b in validos_para_corr:
        va=[row['scores'][a][r] for row in llamadas if a in row['scores'] and b in row['scores'] for r in REG]
        vb=[row['scores'][b][r] for row in llamadas if a in row['scores'] and b in row['scores'] for r in REG]
        if va and vb:
            corr[(a,b)] = pearson(va,vb)

# Por campaña (promedio del juez "deepeval" y gemini)
camps = {}
for row in llamadas:
    c = row['campaign']
    camps.setdefault(c, []).append(row)
campañas = sorted(camps.items())

# Utilidades para barras CSS
def barra(pct, color='#22c55e', label=None):
    w = max(2, round(pct*100,1))
    fill = f'<div class="barbg"><div class="bar" style="width:{w}%;background:{color}"></div></div>'
    return f'<div style="display:flex;align-items:center;gap:8px;flex:1"><div style="width:150px;text-align:right;color:#94a3b8;font-size:12px;padding-right:6px">{label or ""}</div>{fill}<span style="width:44px;font-weight:700;font-size:13px">{pct:.2f}</span></div>'

def dotbar(pct, color='#22c55e'):
    w=max(2,round(pct*100,1))
    return f'<div class="barbg" style="flex:1"><div class="bar" style="width:{w}%;background:{color}"></div></div><span style="width:44px;font-weight:700;font-size:12px">{pct:.2f}</span>'

# ============ Construir HTML ============
html=[]

html.append("""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GAIL · Evaluación Completa (45 llamadas · 7 jueces)</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}
.header{background:linear-gradient(135deg,#0a4a52,#0e7c86);padding:26px 32px;border-bottom:1px solid #22d3ee33}
.header h1{font-size:26px;font-weight:800;color:#fff}
.header p{color:#a7f3d0;margin-top:6px;font-size:14px;line-height:1.5}
.container{max-width:1500px;margin:0 auto;padding:24px}
.grid{display:grid;gap:20px;margin-bottom:24px}
.grid-2{grid-template-columns:repeat(2,1fr)}
.grid-3{grid-template-columns:repeat(3,1fr)}
.grid-4{grid-template-columns:repeat(4,1fr)}
.grid-5{grid-template-columns:repeat(5,1fr)}
.tab-container{display:flex;gap:4px;margin-bottom:20px;flex-wrap:wrap}
.tab{padding:9px 16px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:600;
     background:#1e293b;color:#94a3b8;border:none;transition:all .2s}
.tab.active{background:#22d3ee;color:#083344}
.tab:hover:not(.active){background:#334155;color:#e2e8f0}
.section{display:none}.section.active{display:block}
.card{background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155}
.card h3{font-size:13px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:12px}
.card h4{font-size:15px;color:#f8fafc;margin-bottom:8px}
.stat{font-size:34px;font-weight:800}
.stat.green{color:#22c55e}.stat.yellow{color:#eab308}.stat.red{color:#ef4444}.stat.purple{color:#a855f7}.stat.cyan{color:#22d3ee}
.badge{display:inline-block;padding:2px 9px;border-radius:9999px;font-size:11px;font-weight:700}
.badge-green{background:#166534;color:#bbf7d0}.badge-yellow{background:#854d0e;color:#fef08a}
.badge-red{background:#991b1b;color:#fecaca}.badge-cyan{background:#155e75;color:#a5f3fc}.badge-purple{background:#581c87;color:#e9d5ff}
.barbg{background:#334155;border-radius:4px;height:16px;overflow:hidden;min-width:40px}
.bar{height:100%;border-radius:4px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:9px 11px;text-align:left;border-bottom:1px solid #334155}
th{color:#94a3b8;font-weight:700;text-transform:uppercase;font-size:11px;letter-spacing:.5px;white-space:nowrap}
tr:hover td{background:#1e293b66}
.tblwrap{overflow-x:auto}
.metrica-row{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #1e293b}
.chip{display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700}
.chip-red{background:#991b1b33;color:#fca5a5}.chip-green{background:#16653433;color:#86efac}.chip-yellow{background:#854d0e33;color:#fde047}.chip-cyan{background:#155e75;color:#a5f3fc}
.note{background:#0a4a5222;border-left:3px solid #22d3ee;padding:12px 16px;border-radius:0 8px 8px 0;margin:14px 0;font-size:13px;color:#cbd5e1;line-height:1.6}
.kpi-sub{font-size:12px;color:#94a3b8;margin-top:2px}
select,input{background:#0f172a;border:1px solid #334155;color:#e2e8f0;padding:6px 10px;border-radius:6px;font-size:13px}
@media(max-width:900px){.grid-2,.grid-3,.grid-4,.grid-5{grid-template-columns:1fr}.container{padding:12px}.header{padding:18px}}
</style></head><body>
<div class="header">
<h1>📞 GAIL VoiceBot · Evaluación Completa de Calidad</h1>
<p>45 llamadas reales outbound · 15 campañas · 7 reglas de calidad · 7 jueces (heurísticas + 6 LLM) · Juez de referencia: <strong>Gemini (Google)</strong> · 630+ evaluaciones</p>
</div>
<div class="container">
""")

html.append("""
<div class="grid grid-2" style="margin-bottom:20px">
<div><div class="card" style="display:flex;gap:14px;align-items:center">
<div style="font-size:38px">🎧</div><div><h4>Llamadas reales</h4><div class="stat" style="font-size:28px;color:#f8fafc">45</div><div class="kpi-sub">15 campañas outbound · API Lula</div></div></div></div>
<div><div class="card" style="display:flex;gap:14px;align-items:center">
<div style="font-size:38px">🧪</div><div><h4>Reglas de calidad</h4><div class="stat" style="font-size:28px;color:#f8fafc">7 métricas</div><div class="kpi-sub">heurísticas determinísticas + rúbrica LLM</div></div></div></div>
<div><div class="card" style="display:flex;gap:14px;align-items:center">
<div style="font-size:38px">🔀</div><div><h4>Jueces LLM</h4><div class="stat" style="font-size:28px;color:#f8fafc">6</div><div class="kpi-sub">qwen7b · qwen-coder · gpt-oss · Gemini</div></div></div></div>
<div><div class="card" style="display:flex;gap:14px;align-items:center">
<div style="font-size:38px">⚖️</div><div><h4>Juez de referencia</h4><div class="stat" style="font-size:24px;color:#22c55e">Gemini</div><div class="kpi-sub">proveedor externo (Google)</div></div></div></div>
</div>

<div class="tab-container">
<button class="tab active" onclick="showTab('overview')">Overview</button>
<button class="tab" onclick="showTab('jueces')">Jueces</button>
<button class="tab" onclick="showTab('metricas')">Métricas</button>
<button class="tab" onclick="showTab('campanas')">Campañas</button>
<button class="tab" onclick="showTab('llamadas')">Llamadas</button>
<button class="tab" onclick="showTab('conclusiones')">Conclusiones</button>
</div>
""")

# ============ OVERVIEW ============
gqwen = prom['deepeval']; gcod = prom['juez2_coder']; ggem = prom['gemini']; gheur = 0.53
html.append(f"""
<!-- OVERVIEW -->
<div id="overview" class="section active">
<div class="grid grid-4" style="margin-bottom:20px">
<div class="card"><h3>Heurísticas</h3><div class="stat yellow">{gheur:.2f}</div><span class="badge badge-yellow">7 reglas · sin IA</span></div>
<div class="card"><h3>qwen2.5:7b</h3><div class="stat purple">{gqwen:.2f}</div><span class="badge badge-purple">DeepEval·LangSmith·Opik</span></div>
<div class="card"><h3>qwen2.5-coder</h3><div class="stat purple">{gcod:.2f}</div><span class="badge badge-purple">juez2</span></div>
<div class="card"><h3>★ Gemini (ref)</h3><div class="stat green">{ggem:.2f}</div><span class="badge badge-green">proveedor externo</span></div>
</div>

<div class="grid grid-2">
<div class="card"><h3>🎯 Score global por juez</h3>
""")
for j in ['deepeval','juez2_coder','gemini']:
    html.append(barra(prom[j], J_COLOR[j], J_ETIQ[j]))
html.append("""</div>
<div class="card"><h3>📊 Lectura rápida</h3>
<div class="metric">""")
# top problemas y fortalezas por consenso (gemini + qwen)
html.append("""
<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
<span class="chip chip-red">🔴 Débil crítico</span><span class="chip chip-yellow">🟡 Débil</span><span class="chip chip-green">🟢 Fortaleza</span>
</div>
""")
html.append("</div></div></div>")

html.append("""
<div class="grid grid-2" style="margin-top:0">
<div class="card"><h3>🧠 Consenso entre jueces (Gemini + qwen coinciden)</h3>
""")
# debilidades confirmadas por ambos
html.append("""
<div class="metric" style="margin-bottom:10px"><span class="chip chip-red">CRÍTICO</span> <strong style="color:#fca5a5">Pide consentimiento</strong> — el bot casi nunca pregunta si es buen momento. Riesgo normativo.
<div style="margin-top:6px">""")
html.append(dotbar(0.022,'#ef4444') + " Gemini")
html.append("</div><div style='color:#94a3b8;font-size:12px;margin-left:44px'>qwen7b=0.43 · coder=0.46</div></div>")
html.append("""
<div class="metric" style="margin-bottom:10px"><span class="chip chip-yellow">DÉBIL</span> <strong style="color:#fde047">Menciona propósito</strong> — no siempre explican por qué llaman.
<div style="margin-top:6px">""")
html.append(dotbar(0.20,'#eab308') + " Gemini")
html.append("</div><div style='color:#94a3b8;font-size:12px;margin-left:44px'>qwen7b=0.29 · coder=0.41</div></div>")
html.append("""
<div class="metric"><span class="chip chip-green">FORTALEZA</span> <strong style="color:#86efac">Tono respetuoso & manejo del no-interés</strong> — el bot cierra cortés ante rechazos.
</div></div>
<div class="card"><h3>🟥 Debilidades priorizadas</h3>""")
# priorizacion
prior = [('pide_consentimiento','0.02', 'gemini'), ('ofrece_agendar_cita','0.09','gemini'), ('menciona_proposito','0.20','gemini'), ('se_presenta','0.47','gemini')]
for nombre,prom_punt, j in [('Pide consentimiento','0.02','gemini'),('Ofrece agendar cita','0.09','gemini'),('Menciona propósito','0.20','gemini'),('Se presenta','0.47','gemini')]:
    html.append(f'<div style="display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid #1e293b"><span style="flex:1">{nombre}</span>{dotbar(float(prom_punt),"#ef4444")}</div>')
html.append("</div></div></div>")

# ============ JUECES ============
html.append("""
<!-- JUECES -->
<div id="jueces" class="section">
<div class="grid grid-5" style="margin-bottom:20px">""")
for j, e in [('deepeval','DeepEval'),('langsmith','LangSmith'),('opik','Opik'),('juez2_coder','juez2-coder'),('gemini','★ Gemini')]:
    color = J_COLOR[j]
    html.append(f'<div class="card"><h3>{e}</h3><div class="stat" style="color:{color}">{prom[j]:.3f}</div><span class="badge badge-cyan">{J_ETIQ[j].split("·")[0].strip()}</span></div>')
html.append("</div>")

# Correlación
html.append('<div class="card" style="margin-bottom:20px"><h3>📈 Correlación (Pearson) entre jueces</h3><div class="tblwrap"><table><thead><tr><th></th>')
orden = ['deepeval','langsmith','opik','juez2_coder','gemini']
for j in orden:
    html.append(f'<th>{J_ETIQ[j].replace("\\n"," ")}</th>')
html.append('</tr></thead><tbody>')
for a in orden:
    html.append(f'<tr><td style="font-weight:700;color:#e2e8f0">{J_ETIQ[a].replace("\\n"," ")}</td>')
    for b in orden:
        r = corr.get((a,b), 0)
        col = '#22c55e' if r>0.7 else ('#eab308' if r>0.4 else '#ef4444')
        html.append(f'<td style="color:{col};font-weight:700;text-align:center">{r:.2f}</td>')
    html.append('</tr>')
html.append('</tbody></table><p style="color:#94a3b8;font-size:12px;margin-top:8px">El trio DeepEval/LangSmith/Opik comparte el mismo modelo qwen7b (r=1.0). Gemini es el juez independiente que valida el consenso.</p></div>')

# Comparativa por métrica
html.append('<div class="card" style="margin-top:20px"><h3>⚖️ Comparativa por métrica (5 jueces válidos)</h3><div class="tblwrap"><table><thead><tr><th>Métrica</th>')
for j in ['deepeval','langsmith','opik','juez2_coder','gemini']:
    html.append(f'<th>{J_ETIQ[j].replace("\\n"," ")}</th>')
html.append('<th>Lectura</th></tr></thead><tbody>')
lectura = {
 'se_presenta':'Presentación parcial detectada por LLM',
 'menciona_proposito':'<span class="chip chip-yellow">DÉBIL</span> no explica el motivo',
 'pide_consentimiento':'<span class="chip chip-red">CRÍTICO</span> casi nunca pide permiso',
 'maneja_no_interes':'<span class="chip chip-green">FORTALEZA</span> cierre cortés',
 'ofrece_agendar_cita':'<span class="chip chip-yellow">DÉBIL</span> casi nunca ofrece cita',
 'listado_max_3':'<span class="chip chip-yellow">DISCREPANCIA</span> Gemini alto vs qwen bajo',
 'tono_respetuoso':'<span class="chip chip-green">FORTALEZA</span> tono cortés'}
for r in REG:
    html.append(f'<tr><td style="font-weight:700;color:#e2e8f0">{REG_ES[r]}</td>')
    for j in ['deepeval','langsmith','opik','juez2_coder','gemini']:
        v = prom[j]
        # promedio de esta metrica del juez
        vals=[row['scores'][j][r] for row in llamadas if j in row['scores']]
        mv = round(sum(vals)/len(vals),2) if vals else 0
        col = '#22c55e' if mv>=0.7 else ('#eab308' if mv>=0.35 else '#ef4444')
        html.append(f'<td style="color:{col};font-weight:700">{mv:.2f}</td>')
    html.append(f'<td style="color:#94a3b8;font-size:12px">{lectura[r]}</td></tr>')
html.append('</tbody></table></div></div></div>')

# ============ MÉTRICAS ============
html.append("""
<!-- METRICAS -->
<div id="metricas" class="section">
<div class="note">Los scores por métrica de cada juez comparados. Verde ≥0.7, amarillo 0.35-0.7, rojo &lt;0.35.</div>
""")
for r in REG:
    # promedio de cada juez en esta metrica
    filas=[]
    for j in J_VALIDOS:
        cols=[row['scores'][j][r] for row in llamadas if j in row['scores']]
        mv=round(sum(cols)/len(cols),2) if cols else 0
        filas.append((j,mv))
    html.append(f'<div class="card" style="margin-bottom:16px"><h3>{REG_ES[r]}</h3>')
    for j,mv in filas:
        col = '#22c55e' if mv>=0.7 else ('#eab308' if mv>=0.35 else '#ef4444')
        html.append(f'<div class="metrica-row"><span style="width:140px">{J_ETIQ[j].replace("\\n"," ")}</span>'+dotbar(mv,col)+'</div>')
    html.append('</div>')
html.append('</div>')

# ============ CAMPAÑAS ============
html.append("""
<!-- CAMPANAS -->
<div id="campanas" class="section">
<div class="note">Score promedio por campaña según el juez de referencia (Gemini) y qwen7b (DeepEval). Ordenado por score Gemini.</div>
""")
# promedio por campaña para gemini y deepeval
camp_rows=[]
for c, rows in campañas:
    if not rows: continue
    gvals=[row['scores']['gemini'].values() for row in rows if 'gemini' in row['scores'] and row['scores']['gemini']]
    flat=[v for g in gvals for v in g]
    gm = round(sum(flat)/len(flat),2) if flat else 0
    qvals=[row['scores']['deepeval'].values() for row in rows if 'deepeval' in row['scores'] and row['scores']['deepeval']]
    qflat=[v for g in qvals for v in g]
    qm = round(sum(qflat)/len(qflat),2) if qflat else 0
    n=len(rows)
    camp_rows.append((c,gm,qm,n))
camp_rows.sort(key=lambda x:x[1])
html.append('<div class="tblwrap"><table><thead><tr><th>Campaña</th><th>Llamadas</th><th>★ Gemini</th><th>qwen7b</th></tr></thead><tbody>')
for c,gm,qm,n in camp_rows:
    barcol = lambda v,col: f'<div class="barbg" style="width:70px"><div class="bar" style="width:{max(2,round(v*100))}%;background:{col}"></div></div>{v:.2f}'
    colg='#22c55e' if gm>=0.7 else ('#eab308' if gm>=0.35 else '#ef4444')
    colq='#22c55e' if qm>=0.7 else ('#eab308' if qm>=0.35 else '#ef4444')
    html.append(f'<tr><td style="font-weight:600">{H.escape(c)}</td><td>{n}</td>'
                f'<td style="color:#94a3b8;font-size:12px">{n} call</td>'
                f'<td>'+barcol(gm,colg)+f'</td><td>'+barcol(qm,colq)+f'</td></tr>')
html.append('</tbody></table></div></div>')

# ============ LLAMADAS ============
html.append("""
<!-- LLAMADAS -->
<div id="llamadas" class="section">
<div class="grid grid-3" style="margin-bottom:16px">
<div><label>Juez: </label><select id="bus-juez"></select></div>
<div><label>Campaña: </label><select id="bus-camp"><option value="">Todas</option></select></div>
<div><label>Outcome: </label><select id="bus-out"><option value="">Todos</option></select></div>
</div>
<div class="tblwrap"><table><thead><tr><th>Contacto</th><th>Campaña</th><th>Outcome</th><th>Dur</th><th>Score</th><th>Detalle</th></tr></thead><tbody id="tabla-llamadas"></tbody></table></div>
<script>
""")
# Inyectar datos de llamadas como JS
html.append("const DATOS = ")
html.append(json.dumps([{ 'id':r['id'],'campaign':r['campaign'],'outcome':r['outcome'],'contacto':r['contacto'],
   'duration':r['duration'],'scores':{j:{k:r['scores'][j][k] for k in REG} for j in J_VALIDOS if j in r['scores']}}
   for r in llamadas], ensure_ascii=False))
html.append(""";
const REG_ARR = """ + json.dumps(REG) + """;
const REG_ES1 = """ + json.dumps(REG_ES) + """;
const JUEZ_NOMBRE = {"deepeval":"qwen7b (DeepEval)","langsmith":"qwen7b (LangSmith)","opik":"qwen7b (Opik)","juez2_coder":"qwen-coder","gemini":"★ Gemini"};

// llenar selects
const selJuez=document.getElementById('bus-juez');
Object.keys(JUEZ_NOMBRE).forEach(j=>{const o=document.createElement('option');o.value=j;o.textContent=JUEZ_NOMBRE[j];selJuez.appendChild(o)});
selJuez.value='gemini';
const campSet=new Set(DATOS.map(d=>d.campaign));
const selCamp=document.getElementById('bus-camp');
campSet.forEach(c=>{const o=document.createElement('option');o.value=c;o.textContent=c;selCamp.appendChild(o)});
const outSet=new Set(DATOS.map(d=>d.outcome));
const selOut=document.getElementById('bus-out');
outSet.forEach(o=>{const oo=document.createElement('option');oo.value=o;oo.textContent=o;selOut.appendChild(oo)});

function scoreProm(scores){
  if(!scores) return 0;
  const v=Object.values(scores);
  return v.length? v.reduce((a,b)=>a+b,0)/v.length : 0;
}
function renderTabla(){
  const juez=selJuez.value, camp=selCamp.value, out=selOut.value;
  const rows=DATOS.filter(d=>(!camp||d.campaign===camp)&&(!out||d.outcome===out))
    .map(d=>{const s=d.scores[juez];return{...d,score:scoreProm(s),s:s}})
    .sort((a,b)=>a.score-b.score);
  const tb=document.getElementById('tabla-llamadas');
  tb.innerHTML=rows.map(d=>{
    const sc=d.score, scCol=sc>=0.7?'#22c55e':(sc>=0.35?'#eab308':'#ef4444');
    const det=REG_ARR.map(r=>`<span title="${REG_ES1[r]}: ${d.s&&d.s[r]!==undefined?d.s[r].toFixed(2):'-'}">${d.s&&d.s[r]!==undefined?d.s[r].toFixed(1):'-'}</span>`).join(' ');
    return `<tr><td>${d.contacto||'-'}</td><td>${(d.campaign||'').length>28?(d.campaign.slice(0,27)+'…'):d.campaign}</td><td>${d.outcome||'-'}</td><td>${d.duration||0}s</td><td style="font-weight:700;color:${scCol}">${sc.toFixed(2)}</td><td style="font-size:11px;color:#94a3b8;max-width:260px">${det}</td></tr>`;
  }).join('');
}
[selJuez,selCamp,selOut].forEach(s=>s.addEventListener('change',renderTabla));
renderTabla();
</script>
</div>
""")

# ============ CONCLUSIONES ============
html.append("""
<!-- CONCLUSIONES -->
<div id="conclusiones" class="section">
<div class="grid grid-2">
<div class="card"><h3 class="""+"'"+"""h3">✅ Consenso robusto (Gemini + qwen)</h3>
<div class="metric spoiler"><h4>Resultado global</h4><p>Los jueces convergen: score global <strong>0.47–0.52</strong>. Gemini (referencia externa) da <strong>0.524</strong>, validando los ~0.47 de qwen7b.</p></div>
<div class="metric"><h4>Fortalezas confirmadas</h4><p>✅ <strong style="color:#86efac">Tono respetuoso</strong> (qwen .95 / Gemini 1.0)<br>✅ <strong style="color:#86efac">Manejo no-interés</strong> (qwen .63 / Gemini .96)</p></div>
<div class="metric"><h4>Debilidades confirmadas</h4><p>🔴 <strong style="color:#fca5a5">Pide consentimiento</strong> (qwen .43 / Gemini .02) → riesgo normativo<br>🟡 <strong style="color:#fde047">Menciona propósito</strong> (qwen .29 / Gemini .20)<br>🟡 <strong style="color:#fde047">Ofrece agendar cita</strong> (qwen .31 / Gemini .09)</p></div>
</div>
<div class="card"><h3>⚠️ Discrepancia a resolver</h3>
<div class="metric"><h4>listado_max_3</h4>
<p>Gemini mide <strong style="color:#22c55e">0.93</strong> (alto) mientras qwen mide <strong style="color:#ef4444">0.06–0.18</strong> (bajo). Interpretación opuesta del criterio "si no lista propiedades". <strong>Requerido:</strong> revisar la rúbrica y definir qué cuenta como listado.</p></div>
</div>
<div class="card"><h3>📌 Prioridades de mejora para el bot (acción)</h3>
<ol style="margin-left:22px;line-height:1.9">
<li><strong>Implementar petición de consentimiento</strong> al inicio (pregunta de buen momento) — déficit crítico y normativo.</li>
<li><strong>Agregar apertura estándar</strong> con el propósito de la llamada.</li>
<li><strong>Ofrecer agendar cita / derivar a asesor</strong> cuando hay interés.</li>
</ol>
</div>
<div class="card" style="grid-column:1/-1"><h3>🎯 Conclusión metodológica</h3>
<p>Usar un <strong>juez de referencia de proveedor externo</strong> (Gemini) que corre con la misma rúbrica y el mismo dataset aumenta la fidelidad: confirma que los hallazgos no son un artefacto del modelo local. Correlación qwen↔gemini de <strong>r≈0.48</strong> es positiva pero moderada, coherente con modelos distintos — la coincidencia en <em>cuáles</em> métricas son débiles/fuertes es lo que da confianza. La discrepancia en <code>listado_max_3</code> es el caso a auditar manualmente.</p>
</div>
</div>
</div>

<script>
function showTab(id){document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.getElementById(id).classList.add('active');event.target.classList.add('active')}
</script>
</div></body></html>
""")

out_html = "\n".join(html)
with open('dashboard-evaluacion-gail.html','w',encoding='utf-8') as f:
    f.write(out_html)
print('OK dashboard-evaluacion-gail.html generado:', round(len(out_html)/1024,1),'KB')
