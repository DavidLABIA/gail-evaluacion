"""Validación de consistencia del pipeline GAIL.

Re-evalúa una muestra de llamadas reales con el juez LLM (k corridas) y mide:
  1. Determinismo del juez (estabilidad de scores LLM entre corridas).
  2. Correlación Heur ↔ LLM por métrica.

Uso:
  .venv/bin/python gail_masivo/validar_consistencia.py --muestra 10 --k 2 [--juez ollama/qwen2.5:7b]
"""

import argparse
import json
import os
import random
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(AQUI, "data", "llamadas_gail.json")
RESULTADOS = os.path.join(AQUI, "evaluacion", "resultados_masivos.json")

MÉTRICAS = ["se_presenta", "menciona_proposito", "pide_consentimiento",
            "maneja_no_interes", "ofrece_agendar_cita", "listado_max_3", "tono_respetuoso"]

URL = "http://localhost:11434/api/generate"

PROMPT = """Sos un evaluador estricto de llamadas de un voicebot inmobiliario outbound (GAIL).
Evaluá la métrica '{metrica}' sobre esta transcripción.

RÚBRICA:
  1.0 = cumple claramente · 0.5 = parcial · 0.0 = no cumple
Ante casos ambiguos usá 0.25/0.75.

TRANSCRIPCIÓN:
{transcript}

Devolvé SOLO JSON: {{"score": 0.0-1.0, "reason": "breve"}}"""


def cargar_datos():
    llamadas = json.load(open(DATOS, encoding="utf-8"))
    if isinstance(llamadas, dict):
        llamadas = llamadas.get("llamadas", llamadas.get("resultados", []))
    return llamadas


def transcript_to_text(t):
    if isinstance(t, str):
        return t
    if isinstance(t, list):
        out = []
        for turno in t:
            if isinstance(turno, dict):
                role = turno.get("role", turno.get("speaker", "?"))
                content = (turno.get("content") or turno.get("text")
                           or turno.get("transcript") or "")
                out.append(f"[{role.upper()}] {content}")
        return "\n".join(out)
    return str(t)


def llamada_a_meta(llamada):
    m = llamada.get("metadata", llamada)
    if "campaign" in m:
        return m
    return {"campaign": m.get("campaignName", m.get("name", "?")),
            "contacto": m.get("contactFirstName", "?"),
            "outcome": m.get("outcome", "")}


def extraer_json(texto):
    m = re.search(r"\{[^{}]+\}", texto, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    try:
        return json.loads(texto)
    except Exception:
        return None


def llamar_ollama(prompt):
    import urllib.request
    body = json.dumps({"model": "qwen2.5:7b", "prompt": prompt,
                       "stream": False, "options": {"temperature": 0.2}}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read()).get("response", "")
    except Exception as e:
        print(f"  [error Ollama] {e}")
        return ""


def evaluar_llm(llamada, metrica):
    transcript = transcript_to_text(llamada.get("transcripcion") or llamada.get("transcript", ""))
    if not transcript:
        return None
    prompt = PROMPT.format(metrica=metrica, transcript=transcript[:4000])
    resp = llamar_ollama(prompt)
    data = extraer_json(resp)
    if not data:
        return None
    return float(data.get("score", data.get("value", 0)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--muestra", type=int, default=10)
    parser.add_argument("--k", type=int, default=2, help="número de corridas por llamada/métrica")
    args = parser.parse_args()

    random.seed(2026)
    llamadas = cargar_datos()
    muestras = random.sample(llamadas, min(args.muestra, len(llamadas)))
    print(f"Validando consistencia sobre {len(muestras)} llamadas × {args.k} corridas")

    # heur scores ya calculados (del checkpoint)
    heur_por_id = {}
    if os.path.exists(RESULTADOS):
        res = json.load(open(RESULTADOS, encoding="utf-8"))
        res = res["resultados"] if isinstance(res, dict) else res
        for r in res:
            heur_por_id[r["id"]] = r["scores"]["heur"]

    llm_por_metrica = {m: [] for m in MÉTRICAS}
    heur_por_metrica = {m: [] for m in MÉTRICAS}
    llamada_llm_por_id = {}

    for i, ll in enumerate(muestras, 1):
        mid = ll.get("id", f"s{i}")
        print(f"[{i}/{len(muestras)}] {mid}...")
        meta = llamada_a_meta(ll)
        heur = heur_por_id.get(mid, {})
        for m in MÉTRICAS:
            scores = [evaluar_llm(ll, m) for _ in range(args.k)]
            scores = [s for s in scores if s is not None]
            if not scores:
                continue
            llamada_llm_por_id.setdefault(mid, {})[m] = scores
            llm_por_metrica[m].append(sum(scores) / len(scores))
            if m in heur and "value" in heur[m]:
                heur_por_metrica[m].append(heur[m]["value"])

    # reporte
    print("\n=== DETERMINISMO (score promedio por corrida) ===")
    print(f"{'métrica':<24}{'scores':<40}{'rango'}")
    deter = {m: 1.0 for m in MÉTRICAS}
    for m in MÉTRICAS:
        por_corrida = {c: [] for c in range(args.k)}
        for mid, met in llamada_llm_por_id.items():
            if m in met and len(met[m]) == args.k:
                for c, s in enumerate(met[m]):
                    por_corrida[c].append(s)
        if por_corrida[0] and por_corrida[args.k - 1]:
            a = sum(por_corrida[0]) / len(por_corrida[0])
            b = sum(por_corrida[args.k - 1]) / len(por_corrida[args.k - 1])
            deter[m] = 1 - abs(a - b)
            print(f"{m:<24}corr1={a:.2f} corr{args.k}={b:.2f}  estabilidad={deter[m]:.2f}")

    print("\n=== CORRELACIÓN HEUR ↔ LLM (por métrica) ===")
    from math import sqrt
    for m in MÉTRICAS:
        h = heur_por_metrica.get(m, [])
        l = llm_por_metrica.get(m, [])
        if len(h) >= 3 and len(h) == len(l):
            mh, ml = sum(h) / len(h), sum(l) / len(l)
            num = sum((a - mh) * (b - ml) for a, b in zip(h, l))
            den = sqrt(sum((a - mh) ** 2 for a in h) * sum((b - ml) ** 2 for b in l)) or 1
            r = num / den
            print(f"{m:<24} heur={mh:.2f} llm={ml:.2f}  r={r:.2f}")

    print("\n✅ Validación completada.")


if __name__ == "__main__":
    main()