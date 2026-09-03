#!/usr/bin/env python3
"""Evaluador Gemini (Google) para GAIL outbound usando SOLO urllib (stdlib).

No depende de `requests`. Usa la misma rúbrica de 7 reglas y las 45 llamadas
reales para servir de juez de referencia (ground truth) contrastable contra
Ollama/DeepEval/LangSmith/Opik/Promptfoo.

Checkpoint por regla para reanudar ante rate limits. Corre en background.

Uso:
  GEMINI_API_KEY=... python3 gail_masivo/herramientas/evaluar_gemini_urllib.py
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, '..', '..', 'shared'))
sys.path.insert(0, os.path.join(AQUI, '..'))
from juez_gail_http import REGLAS_OUTBOUND, a_texto, promedio  # noqa: E402

FUENTE = os.path.join(AQUI, '..', 'data', 'llamadas_gail.json')
SALIDA = os.path.join(AQUI, '..', 'evaluacion', 'gemini_resultados.json')
CHECKPOINT = os.path.join(AQUI, '..', 'evaluacion', 'gemini_checkpoint.json')

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/"
GEMINI_MODEL = "gemini-flash-lite-latest"

SISTEMA = (
    "Eres un evaluador estricto del voicebot de llamadas salientes de GAIL. "
    "Un lead recibe una llamada del bot (transcripcion en formato [BOT]/[CLIENTE]). "
    "Recibis un criterio individual y debes puntuarlo con un score de 0 a 1 y una razon. "
    'Respondé EXACTAMENTE con JSON: {"score": 0.X, "reason": "..."}. '
    "No agregues texto fuera del JSON."
)


def llamar_gemini(api_key, criterio, transcripcion, max_intentos=6):
    url = f"{GEMINI_URL}{GEMINI_MODEL}:generateContent?key={api_key}"
    body = {
        "system_instruction": {"parts": [{"text": SISTEMA}]},
        "contents": [{
            "parts": [{"text": f"{criterio}\n\nTRANSCRIPCION:\n{transcripcion}\n\n"
                                'Respondé JSON'}]
        }],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 512},
    }
    for intento in range(max_intentos):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.load(r)
            candidates = data.get("candidates", [])
            if not candidates:
                reason = data.get("promptFeedback", {}).get("blockReason", "sin candidato")
                raise ValueError(f"Sin candidato: {reason}")
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts)
        except urllib.error.HTTPError as e:
            resp = e.read().decode("utf-8", "ignore")
            code_msg = resp[:200]
            if e.code == 429:
                espera = 15 * (intento + 1)
                print(f"    [429] esperando {espera}s (intento {intento+1}/{max_intentos}) | {code_msg}", file=sys.stderr, flush=True)
                time.sleep(espera)
            elif e.code == 503:
                espera = 12 * (intento + 1)
                print(f"    [503] esperando {espera}s (intento {intento+1}/{max_intentos})", file=sys.stderr, flush=True)
                time.sleep(espera)
            elif e.code in (400, 403, 404):
                print(f"    [fatal {e.code}] {code_msg}", file=sys.stderr, flush=True)
                if intento >= 1:
                    return None
                time.sleep(5)
            else:
                print(f"    [HTTP {e.code}] {code_msg}", file=sys.stderr, flush=True)
                time.sleep(10 * (intento + 1))
        except Exception as e:
            print(f"    [error] {e}", file=sys.stderr, flush=True)
            time.sleep(10 * (intento + 1))
    return None


def parse_output(raw, regla):
    if isinstance(raw, str) and raw.strip():
        s = raw.strip()
        if s.startswith("```"):
            s = s.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            d = json.loads(s)
            if isinstance(d, dict) and "score" in d:
                return {"value": float(d["score"]), "reason": str(d.get("reason", ""))}
        except Exception:
            pass
    return {"value": 0.0, "reason": f"output no parseable ({regla}): {str(raw)[:120]}"}


def cargar_checkpoint():
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT, encoding="utf-8") as f:
            return json.load(f)
    return {}


def guardar_checkpoint(data):
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", help="ID de una llamada a evaluar")
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Falta GEMINI_API_KEY en el entorno")

    with open(FUENTE, encoding="utf-8") as f:
        llamadas = json.load(f)
    if isinstance(llamadas, dict):
        llamadas = llamadas.get("llamadas", llamadas.get("resultados", []))

    items = []
    for it in llamadas:
        texto = a_texto(it.get("transcripcion", []))
        if texto:
            items.append({"id": it.get("id"), "transcripcion": texto})
    if args.solo:
        items = [i for i in items if args.solo in i["id"]]

    total_llamadas = len(items)
    total_reglas = len(REGLAS_OUTBOUND)
    print(f"Juez Gemini/{GEMINI_MODEL} | {total_llamadas} llamadas x {total_reglas} reglas={total_llamadas*total_reglas} evals", flush=True)

    checkpoint = cargar_checkpoint()

    def stats():
        hechas = sum(len(s) for s in checkpoint.values())
        return hechas, total_llamadas * total_reglas

    for idx, it in enumerate(items, 1):
        cid = it["id"]
        if cid not in checkpoint:
            checkpoint[cid] = {}
        for regla, criterio in REGLAS_OUTBOUND.items():
            if regla in checkpoint[cid]:
                continue
            done, total = stats()
            print(f"[llamada {idx}/{total_llamadas}] {cid[:20]}... | regla {regla} | {done}/{total} evals", flush=True)
            raw = llamar_gemini(api_key, criterio, it["transcripcion"])
            checkpoint[cid][regla] = parse_output(raw, regla)
            guardar_checkpoint(checkpoint)

    # Resumen
    resultados = []
    for it in items:
        scores = checkpoint.get(it["id"], {})
        if scores:
            resultados.append({"id": it["id"], "avg": promedio(scores), "scores": scores})

    if not resultados:
        print("Sin resultados.")
        return

    promedios = {k: round(sum(r["scores"].get(k, {"value": 0})["value"] for r in resultados) / len(resultados), 3)
                 for k in REGLAS_OUTBOUND}
    global_avg = round(sum(promedios.values()) / len(promedios), 3)

    summary = {
        "herramienta": "Juez-Gemini", "modelo": GEMINI_MODEL, "tipo": "outbound",
        "n_llamadas": len(resultados), "promedios": promedios,
        "global_avg": global_avg, "llamadas": resultados,
    }
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*56}\nRESUMEN Gemini ({GEMINI_MODEL}) OUTBOUND GAIL")
    for k, v in promedios.items():
        print(f"  {k}: {v}")
    print(f"  GLOBAL: {global_avg}", flush=True)


if __name__ == "__main__":
    main()
