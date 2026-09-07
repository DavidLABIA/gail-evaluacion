"""Genera un dashboard HTML estilo Proaco (tabs, grid de stats, cards, charts)
con los resultados del análisis masivo GAIL.

Lee evaluacion/resultados_masivos.json, embebe los datos y produce un único HTML
listo para abrir en el navegador o subir a GitHub Pages.

Uso:
  .venv/bin/python gail_masivo/generar_dashboard.py [--salida gail_masivo/GAIL_DASHBOARD.html]
"""

import argparse
import json
import os
import html as html_mod
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
FUENTE = os.path.join(AQUI, "evaluacion", "resultados_masivos.json")

MÉTRICAS = [
    ("se_presenta", "👋", "#22c55e", "Se presenta como la marca"),
    ("menciona_proposito", "💬", "#eab308", "Explica el motivo de la llamada"),
    ("pide_consentimiento", "✋", "#ef4444", "Pide consentimiento para continuar"),
    ("maneja_no_interes", "🚫", "#eab308", "Maneja el 'no me interesa' cortésmente"),
    ("ofrece_agendar_cita", "📅", "#ef4444", "Ofrece agendar cita / derivar a asesor"),
    ("listado_max_3", "📋", "#eab308", "Lista máx. 3 propiedades a la vez"),
    ("tono_respetuoso", "😊", "#22c55e", "Tono respetuoso, sin agresividad"),
]

OUTCOMES_TOPE = ["answered", "talked", "interested", "appointment", "scheduled",
                 "quote", "sold", "contacted", "completed", "positive", "yes",
                 "success", "interesado", "visitado", "derivado", "asignado", "leads"]


def color_cls(v):
    if v >= 0.75:
        return "green"
    if v >= 0.50:
        return "yellow"
    return "red"


def color_hex(v):
    if v >= 0.75:
        return "#22c55e"
    if v >= 0.50:
        return "#eab308"
    return "#ef4444"


def badge(v, texto=None):
    texto = texto if texto is not None else f"{v*100:.0f}"
    return f'<span class="badge badge-{color_cls(v)}">{texto}</span>'


def score_bar(v, etiqueta=None):
    v = max(0.0, min(1.0, v))
    c = color_hex(v)
    extra = (f'<td style="text-align:right;padding-right:8px">{etiqueta}</td>' if etiqueta else "")
    return f"""
    <td style="padding:6px 4px;min-width:90px">
      <div style="display:flex;align-items:center;width:90px">
        <div style="flex:1;height:6px;background:#334155;border-radius:3px;overflow:hidden">
          <div style="width:{v*100:.0f}%;height:100%;background:{c};border-radius:3px"></div>
        </div>
      </div>
    </td>
    <td style="color:{c};font-weight:700;font-size:12px">{v*100:.0f}</td>"""


def tabla_metricas(tipo, data):
    rows = []
    for key, emoji, color, desc in MÉTRICAS:
        v = data.get(key, 0.0)
        rows.append(f"""
        <tr style="border-bottom:1px solid #334155">
          <td style="padding:8px 10px;width:34px"><span style="font-size:16px">{emoji}</span></td>
          <td style="padding:8px 10px;color:#e2e8f0;font-weight:600">{key}</td>
          <td style="padding:8px 10px;color:#94a3b8;font-size:12px">{desc}</td>
          {score_bar(v)}
        </tr>""")
    return "\n".join(rows)


def tabla_campanas(resumen):
    rows = []
    por = resumen["por_campana"]
    for camp in sorted(por.keys(), key=lambda c: -por[c]["n"]):
        d = por[camp]
        h = d.get("heur", {})
        l = d.get("llm", {})
        gh = sum(h.values()) / len(h) if h else 0
        gl = sum(l.values()) / len(l) if l else 0
        rows.append(f"""
        <tr style="border-bottom:1px solid #334155;cursor:pointer" onclick="filtrarCampana('{html_mod.escape(camp, quote=True)}')">
          <td style="padding:10px 12px;color:#f8fafc;font-weight:600">{html_mod.escape(camp)}</td>
          <td style="padding:10px 12px;text-align:center;color:#94a3b8">{d["n"]}</td>
          <td style="padding:10px 12px;text-align:center">{badge(gh)}</td>
          <td style="padding:10px 12px;text-align:center">{badge(gl)}</td>
          <td style="padding:10px 12px;text-align:center;color:#334155">▸</td>
        </tr>""")
    return "\n".join(rows)


def _fecha(m):
    for k in ("publishedAt", "finishedAt"):
        t = str(m.get(k) or "")
        if t:
            import re as _re
            mt = _re.match(r"^(\d{4}-\d{2}-\d{2})", t)
            return mt.group(1) if mt else t[:10]
    return ""


def _badge_origen(org):
    org = org or "simulacion"
    cls = {"real": "badge-green", "prueba": "badge-yellow"}.get(org, "badge-purple")
    return f'<span class="badge {cls}" style="text-transform:lowercase">{org}</span>'


def tabla_llamadas(resultados):
    rows = []
    for r in resultados:
        m = r["metadata"]
        camp = html_mod.escape(str(m.get("campaign", "?")), quote=True)
        contacto = html_mod.escape(str(m.get("contacto", "")) or r["id"])
        out = html_mod.escape(str(m.get("outcome", "")))
        dur = int(m.get("duration") or 0)
        org = html_mod.escape(str(m.get("origen", "simulacion")), quote=True)
        fecha = _fecha(m)
        h = r["scores"]["heur"]
        l = r["scores"]["llm"]
        gh = sum(x["value"] for x in h.values()) / len(h)
        gl = sum(x["value"] for x in l.values()) / len(l)
        pos = any(t in str(m.get("outcome", "")).lower() for t in OUTCOMES_TOPE)
        rows.append(f"""
        <tr style="border-bottom:1px solid #334155" data-camp="{camp}" data-org="{org}" data-fecha="{fecha}">
          <td style="padding:8px 12px;color:#f8fafc">{contacto}</td>
          <td style="padding:8px 12px;color:#94a3b8">{html_mod.escape(str(m.get("campaign","")))}</td>
          <td style="padding:8px 12px">{_badge_origen(org)}</td>
          <td style="padding:8px 12px;color:#94a3b8;font-size:12px">{fecha or "—"}</td>
          <td style="padding:8px 12px;color:#94a3b8;font-size:12px">{out}</td>
          <td style="padding:8px 12px;color:#94a3b8;font-size:12px">{dur}s</td>
          <td style="padding:8px 12px;text-align:center;font-size:13px">{"✅" if pos else "—"}</td>
          <td style="padding:8px 12px;color:#e2e8f0">{gh*100:.0f}</td>
          <td style="padding:8px 12px;color:#e2e8f0">{gl*100:.0f}</td>
        </tr>""")
    return "\n".join(rows)


def porcentaje_outcomes(resultados):
    if not resultados:
        return 0
    pos = sum(1 for r in resultados
              if any(t in str(r["metadata"].get("outcome", "")).lower() for t in OUTCOMES_TOPE))
    return round(pos * 100 / len(resultados))


def duracion_prom(resultados):
    durs = [int(r["metadata"].get("duration") or 0) for r in resultados
            if r["metadata"].get("duration")]
    return round(sum(durs) / len(durs)) if durs else 0


def build(global_heur, global_llm, resumen, resultados, generado):
    por = resumen["por_campana"]
    n = resumen["n_llamadas"]
    campañas = len(por)
    pct_pos = porcentaje_outcomes(resultados)
    dur = duracion_prom(resultados)
    total_eval = n * 7 * 2  # 7 reglas heur + 7 reglas llm

    por_origen = resumen.get("por_origen", {})
    badges_origen = " ".join(
        f'<span class="badge {"badge-green" if o=="real" else "badge-yellow" if o=="prueba" else "badge-purple"}" style="text-transform:lowercase">{o}: {d["n"]}</span>'
        for o, d in sorted(por_origen.items())
    )

    # datasets para chart.js
    heur_keys = [k for k, _, _, _ in MÉTRICAS]
    heur_vals = [round(resumen["heur"].get(k, 0), 3) for k in heur_keys]
    llm_vals = [round(resumen["llm"].get(k, 0), 3) for k in heur_keys]

    camp_names = sorted(por.keys(), key=lambda c: -por[c]["n"])
    camp_heur = [round(sum(por[c]["heur"].values()) / 7, 3) for c in camp_names]
    camp_llm = [round(sum(por[c]["llm"].values()) / 7, 3) for c in camp_names]

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GAIL VoiceBot · Evaluación Masiva con Llamadas Reales</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}}
.header{{background:linear-gradient(135deg,#1e293b,#334155);padding:24px 32px;border-bottom:1px solid #475569}}
.header h1{{font-size:24px;font-weight:700;color:#f8fafc}}
.header p{{color:#94a3b8;margin-top:4px;font-size:14px}}
.container{{max-width:1400px;margin:0 auto;padding:24px}}
.grid{{display:grid;gap:20px;margin-bottom:24px}}
.grid-3{{grid-template-columns:repeat(3,1fr)}}
.grid-2{{grid-template-columns:repeat(2,1fr)}}
.grid-4{{grid-template-columns:repeat(4,1fr)}}
.card{{background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155}}
.card h3{{font-size:14px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:12px}}
.card h4{{font-size:15px;color:#f8fafc;margin-bottom:8px}}
.stat{{font-size:32px;font-weight:700}}
.stat.green{{color:#22c55e}}.stat.yellow{{color:#eab308}}.stat.red{{color:#ef4444}}
.stat.blue{{color:#3b82f6}}.stat.purple{{color:#a855f7}}
.badge{{display:inline-block;padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600}}
.badge-green{{background:#166534;color:#bbf7d0}}.badge-yellow{{background:#854d0e;color:#fef08a}}
.badge-red{{background:#991b1b;color:#fecaca}}.badge-blue{{background:#1e40af;color:#bfdbfe}}
.badge-purple{{background:#581c87;color:#e9d5ff}}
.chart-card{{background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155}}
.chart-card h3{{font-size:16px;color:#f8fafc;margin-bottom:16px}}
table{{width:100%;border-collapse:collapse}}
th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid #334155;font-size:13px}}
th{{color:#94a3b8;font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.5px}}
td{{color:#e2e8f0}}
.tab-container{{display:flex;gap:4px;margin-bottom:20px;flex-wrap:wrap}}
.tab{{padding:8px 16px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:500;
     background:#334155;color:#94a3b8;border:none;transition:all .2s}}
.tab.active{{background:#a855f7;color:#fff}}
.tab:hover:not(.active){{background:#475569;color:#e2e8f0}}
.section{{display:none}}.section.active{{display:block}}
.tool-badge{{display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600}}
.tool-badge.opik{{background:#3b82f620;color:#3b82f6}}
.tool-badge.deepeval{{background:#22c55e20;color:#22c55e}}
.tool-badge.langsmith{{background:#a855f720;color:#a855f7}}
.legend-item{{display:flex;align-items:flex-start;gap:12px;padding:10px 0;border-bottom:1px solid #334155}}
.legend-item:last-child{{border-bottom:none}}
.legend-icon{{width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0}}
.legend-text h4{{font-size:14px;color:#f8fafc;margin-bottom:2px}}
.legend-text p{{font-size:12px;color:#94a3b8;line-height:1.4}}
.step{{display:flex;gap:16px;padding:16px 0;border-bottom:1px solid #334155}}
.step:last-child{{border-bottom:none}}
.step-num{{width:36px;height:36px;border-radius:50%;background:#a855f7;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;flex-shrink:0}}
.step-text h4{{font-size:14px;color:#f8fafc;margin-bottom:4px}}
.step-text p{{font-size:13px;color:#94a3b8;line-height:1.5}}
@media(max-width:768px){{.grid-4,.grid-3,.grid-2{{grid-template-columns:1fr}}.container{{padding:12px}}.header{{padding:16px}}}}
</style>
</head>
<body>
<div class="header">
<h1>📞 GAIL VoiceBot · Evaluación Masiva con Llamadas Reales</h1>
<p>{n} llamadas · {campañas} campañas outbound · 7 reglas heurísticas + 7 con juez LLM · qwen2.5:7b local · Generado {generado}</p>
<p style="margin-top:6px">{badges_origen}</p>
</div>

<div class="container">
<div class="tab-container">
<button class="tab active" onclick="showTab('overview')">Overview</button>
<button class="tab" onclick="showTab('metrics')">Métricas</button>
<button class="tab" onclick="showTab('campanas')">Campañas</button>
<button class="tab" onclick="showTab('calls')">Llamadas</button>
<button class="tab" onclick="showTab('pruebas')">Pruebas</button>
</div>

<!-- ═══════════ OVERVIEW ═══════════ -->
<div id="overview" class="section active">
<div class="grid grid-4" style="margin-bottom:20px">
<div class="card"><h3>Score Heurísticas</h3><div class="stat {color_cls(global_heur)}">{global_heur*100:.0f}</div><span class="badge badge-{color_cls(global_heur)}">7 reglas · sin IA</span></div>
<div class="card"><h3>Score LLM (Juez IA)</h3><div class="stat {color_cls(global_llm)}">{global_llm*100:.0f}</div><span class="badge badge-{color_cls(global_llm)}">7 reglas · qwen2.5:7b</span></div>
<div class="card"><h3>Outcome Positivo</h3><div class="stat green">{pct_pos}%</div><span class="badge badge-blue">answered / interesado…</span></div>
<div class="card"><h3>Duración Promedio</h3><div class="stat" style="color:#f8fafc">{dur}s</div><span class="badge badge-purple">por llamada</span></div>
</div>

<div class="grid grid-2">
<div class="chart-card"><h3>Score Heurístico por Métrica</h3><canvas id="chartHeur"></canvas></div>
<div class="chart-card"><h3>Score LLM por Métrica</h3><canvas id="chartLLM"></canvas></div>
</div>

<div class="grid grid-2" style="margin-top:20px">
<div class="chart-card"><h3>Heurísticas vs LLM por Métrica</h3><canvas id="chartCompare"></canvas></div>
<div class="chart-card"><h3>Score por Campaña</h3><canvas id="chartCamp"></canvas></div>
</div>
</div>

<!-- ═══════════ MÉTRICAS ═══════════ -->
<div id="metrics" class="section">
<div class="grid grid-2">
<div class="card">
<h3>⚙️ Heurísticas · promedio global ({global_heur*100:.0f})</h3>
<table><tbody>{tabla_metricas('heur', resumen["heur"])}</tbody></table>
</div>
<div class="card">
<h3>🤖 Reglas con juez LLM · promedio global ({global_llm*100:.0f})</h3>
<table><tbody>{tabla_metricas('llm', resumen["llm"])}</tbody></table>
</div>
</div>
<div class="card" style="margin-top:20px">
<h3>📊 Escala de Colores</h3>
<div style="display:flex;gap:16px;margin-top:8px;flex-wrap:wrap">
<div style="display:flex;align-items:center;gap:6px"><div style="width:16px;height:16px;border-radius:4px;background:#22c55e"></div><span style="font-size:13px">🟢 0.75 - 1.00: Cumple</span></div>
<div style="display:flex;align-items:center;gap:6px"><div style="width:16px;height:16px;border-radius:4px;background:#eab308"></div><span style="font-size:13px">🟡 0.50 - 0.74: Parcial</span></div>
<div style="display:flex;align-items:center;gap:6px"><div style="width:16px;height:16px;border-radius:4px;background:#ef4444"></div><span style="font-size:13px">🔴 0.00 - 0.49: No cumple</span></div>
</div>
</div>
</div>

<!-- ═══════════ CAMPAÑAS ═══════════ -->
<div id="campanas" class="section">
<div class="card">
<h3>📋 Resultados por Campaña</h3>
<table>
<thead><tr><th>Campaña</th><th style="text-align:center">Llamadas</th><th style="text-align:center">Heur</th><th style="text-align:center">LLM</th><th></th></tr></thead>
<tbody>{tabla_campanas(resumen)}</tbody>
</table>
<p style="color:#94a3b8;font-size:12px;margin-top:12px">Hacé clic en una campaña para filtrar el detalle por llamada.</p>
</div>
</div>

<!-- ═══════════ LLAMADAS ═══════════ -->
<div id="calls" class="section">
<div class="grid grid-3" style="margin-bottom:16px">
<div><label style="display:block;font-size:12px;color:#94a3b8;margin-bottom:4px">Origen: </label><select id="filtro-org" onchange="aplicarFiltros()"><option value="">Todos</option><option value="real">real</option><option value="prueba">prueba</option><option value="simulacion">simulacion</option></select></div>
<div><label style="display:block;font-size:12px;color:#94a3b8;margin-bottom:4px">Desde: </label><input type="date" id="filtro-fecha-ds" onchange="aplicarFiltros()"></div>
<div><label style="display:block;font-size:12px;color:#94a3b8;margin-bottom:4px">Hasta: </label><input type="date" id="filtro-fecha-hs" onchange="aplicarFiltros()"></div>
</div>
<div style="font-size:12px;color:#94a3b8;margin-bottom:8px">Mostrando <b id="filtro-cnt"></b> llamadas.</div>
<div class="card">
<h3>📞 Detalle por Llamada ({n})</h3>
<table>
<thead><tr><th>Contacto</th><th>Campaña</th><th>Origen</th><th>Fecha</th><th>Outcome</th><th>Duración</th><th>Positivo</th><th>Heur</th><th>LLM</th></tr></thead>
<tbody>{tabla_llamadas(resultados)}</tbody>
</table>
</div>
</div>

<!-- ═══════════ PRUEBAS ═══════════ -->
<div id="pruebas" class="section">
<div class="card" style="margin-bottom:20px">
<h3>🧪 Pruebas Realizadas</h3>
<table>
<thead><tr><th>#</th><th>Prueba</th><th>Herramienta</th><th>Modelo</th><th>Llamadas</th><th>Métricas</th><th>Resultado</th></tr></thead>
<tbody>
<tr><td>1</td><td>QA ficción (validación)</td><td><span class="tool-badge deepeval">Local</span></td><td>qwen2.5:7b</td><td>6</td><td>7</td><td><span class="badge badge-yellow">GLOBAL 0.469</span></td></tr>
<tr><td>2</td><td>Llamadas reales GAIL</td><td><span class="tool-badge deepeval">Local</span></td><td>qwen2.5:7b</td><td>{n}</td><td>7 heur + 7 llm</td><td>{badge(global_heur)} heur · {badge(global_llm)} llm</td></tr>
</tbody>
</table>
</div>

<div class="grid grid-3">
<div class="card">
<h3>✅ Pruebas de Conexión</h3>
<table>
<tr><td style="border:none">Lula API</td><td style="border:none;text-align:right"><span class="badge badge-green">OK</span></td></tr>
<tr><td style="border:none">Ollama qwen2.5:7b</td><td style="border:none;text-align:right"><span class="badge badge-green">OK</span></td></tr>
<tr><td style="border:none">Export transcripciones</td><td style="border:none;text-align:right"><span class="badge badge-green">45</span></td></tr>
</table>
</div>
<div class="card">
<h3>📊 Datos del Experimento</h3>
<table>
<tr><td style="border:none">Fecha</td><td style="border:none;text-align:right"><strong>2026-08-31</strong></td></tr>
<tr><td style="border:none">Llamadas reales</td><td style="border:none;text-align:right"><strong>{n}</strong></td></tr>
<tr><td style="border:none">Campañas</td><td style="border:none;text-align:right"><strong>{campañas}</strong></td></tr>
<tr><td style="border:none">Total evaluaciones</td><td style="border:none;text-align:right"><strong>{total_eval}</strong></td></tr>
</table>
</div>
<div class="card">
<h3>🏗️ Flujo del Sistema</h3>
<div class="step"><div class="step-num">1</div><div class="step-text"><h4>Export Lula API</h4><p>Se bajan todas las campañas y transcripciones outbound de GAIL via API key.</p></div></div>
<div class="step"><div class="step-num">2</div><div class="step-text"><h4>Evaluación</h4><p>7 heurísticas determinísticas + 7 reglas con juez LLM local (qwen2.5:7b), con rúbrica y CoT.</p></div></div>
<div class="step"><div class="step-num">3</div><div class="step-text"><h4>Dashboard</h4><p>Agregación por llamada y campaña con score global.</p></div></div>
</div>
</div>
</div>
</div>

<script>
function showTab(id){{document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.getElementById(id).classList.add('active');event.target.classList.add('active')}}

function aplicarFiltros(){{
  const org=document.getElementById('filtro-org').value;
  const ds=document.getElementById('filtro-fecha-ds').value;
  const hs=document.getElementById('filtro-fecha-hs').value;
  let vis=0;
  document.querySelectorAll('#calls tbody tr').forEach(tr=>{{
    const torg=tr.dataset.org||'simulacion', tf=tr.dataset.fecha||'';
    let ok = (!org||torg===org);
    if(ok&&ds&&(!tf||tf<ds)) ok=false;
    if(ok&&hs&&(!tf||tf>hs)) ok=false;
    tr.style.display = ok?'':'none';
    if(ok) vis++;
  }});
  document.getElementById('filtro-cnt').textContent = vis;
}}

function filtrarCampana(camp){{
  document.querySelectorAll('#calls tbody tr').forEach(tr=>{{
    tr.style.display = tr.dataset.camp === camp ? '' : 'none';
  }});
  document.getElementById('calls').classList.add('active');
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab')[3].classList.add('active');
}}

Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = '#334155';
const metricas = {json.dumps(heur_keys, ensure_ascii=False)};
const heur = {json.dumps(heur_vals)};
const llm = {json.dumps(llm_vals)};
const campNames = {json.dumps(camp_names, ensure_ascii=False)};
const campHeur = {json.dumps(camp_heur)};
const campLLM = {json.dumps(camp_llm)};

new Chart(document.getElementById('chartHeur'),{{type:'bar',data:{{labels:metricas,datasets:[{{label:'Heur',data:heur,backgroundColor:'#3b82f6'}}]}},options:{{scales:{{y:{{min:0,max:1}}}}}}}});
new Chart(document.getElementById('chartLLM'),{{type:'bar',data:{{labels:metricas,datasets:[{{label:'LLM',data:llm,backgroundColor:'#a855f7'}}]}},options:{{scales:{{y:{{min:0,max:1}}}}}}}});
new Chart(document.getElementById('chartCompare'),{{type:'bar',data:{{labels:metricas,datasets:[{{label:'Heur',data:heur,backgroundColor:'#3b82f6'}},{{label:'LLM',data:llm,backgroundColor:'#a855f7'}}]}},options:{{scales:{{y:{{min:0,max:1}}}}}}}});
new Chart(document.getElementById('chartCamp'),{{type:'bar',data:{{labels:campNames,datasets:[{{label:'Heur',data:campHeur,backgroundColor:'#3b82f6'}},{{label:'LLM',data:campLLM,backgroundColor:'#a855f7'}}]}},options:{{indexAxis:'y',scales:{{x:{{min:0,max:1}}}}}}}});
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--salida", default=os.path.join(AQUI, "GAIL_DASHBOARD.html"))
    parser.add_argument("--fuente", default=FUENTE, help="archivo JSON de entrada (default: resultados_masivos.json)")
    args = parser.parse_args()

    if not os.path.exists(args.fuente):
        raise SystemExit(f"No existe {args.fuente}. Corré primero evaluar_masivo.py")

    data = json.load(open(args.fuente, encoding="utf-8"))
    if isinstance(data, list):
        resumen = {"n_llamadas": len(data), "por_campana": {}, "heur": {}, "llm": {},
                   "global_heur": 0, "global_llm": 0}
        resultados = data
    else:
        resumen = data["resumen"]
        resultados = data["resultados"]

    generado = datetime.now().strftime("%Y-%m-%d %H:%M")
    html_texto = build(resumen["global_heur"], resumen["global_llm"], resumen, resultados, generado)
    with open(args.salida, "w", encoding="utf-8") as f:
        f.write(html_texto)
    print(f"Dashboard generado: {args.salida}")


if __name__ == "__main__":
    main()