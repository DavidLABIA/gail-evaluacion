"""Pipeline de evaluación masiva OUTBOUND para todas las llamadas reales GAIL.

Lee data/llamadas_gail.json (exportado por exportar_gail.py) y evalúa CADA llamada con
la suite completa:

  A. Heurísticas (rápidas, sin LLM): 7 reglas determinísticas de business.
  B. LLM-judges (7 reglas de negocio con rúbrica): sePresenta, mencionaProposito,
     pideConsentimiento, manejaNoInteres, ofreceAgendarCita, listadoMax3, tonoRespetuoso.
  C. LLM-judges GEval (opcional, --geval): cliente_no_interesado, agendamiento_cita.

Rendimiento y robustez:
  - Checkpoint por llamada (JSON incremental) → se puede interrumpir y reanudar.
  - Retry con backoff ante rate limit del proveedor del juez.
  - Heurísticas primero; LLM después (parámetro --sin-llm para correr solo heurísticas).
  - --limite N para pruebas rápidas.

Uso:
  export LULA_API_KEY=...   (solo si se exporta; acá no hace falta)
  .venv/bin/python gail_masivo/evaluar_masivo.py [--sin-llm] [--limite 20] [--juez ollama/qwen2.5:7b] [--geval] [--fuerza]
"""

import argparse
import json
import os
import re
import sys
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

AQUI = os.path.dirname(os.path.abspath(__file__))
FUENTE = os.path.join(AQUI, "data", "llamadas_gail.json")
EVAL_DIR = os.path.join(AQUI, "evaluacion")
RESULTADOS = os.path.join(EVAL_DIR, "resultados_masivos.json")

JUEZ_DEFECTO = "ollama/qwen2.5:7b"

# ─────────────────────────── A. HEURÍSTICAS ───────────────────────────

REGLA_HEURISTICA = {
    "se_presenta": lambda t: any(m in t for m in ["grupo proaco", "proaco", "soy de", "te llamo de", "le hablo de", "te hablo de"]),
    "menciona_proposito": lambda t: any(m in t for m in [
        "le llamo", "te llamo", "lo contacto", "te contacto", "comunicamos con usted",
        "su interés", "tu interés", "emprendimiento", "campaña", "consultó", "consulto",
        "unidad", "inversión", "inversion", "promoción", "beneficio", "escrúpulo"]),
    "pide_consentimiento": lambda t: any(m in t for m in [
        "¿le molesta", "le molesta", "¿puede hablar", "puede hablar", "¿es buen momento",
        "es buen momento", "tiene unos minutos", "¿tiene un momento", "tiene un momento",
        "¿puedo continuar", "puedo continuar", "lo puedo atender", "la puedo atender",
        "¿está disponible", "está disponible", "¿me escucha", "me permite"]),
    "maneja_no_interes": lambda t: True,  # se evalúa condicionalmente en evaluate_heuristica
    "ofrece_agendar_cita": lambda t: any(m in t for m in [
        "agendar", "agenda una", "una cita", "un turno", "reservar", "visita", "calendario",
        "caldotcom", "schedule", "turno con un asesor", "reunión", "reunion", "coordinamos",
        "coordinemos", "le paso con", "un asesor"]),
    "listado_max_3": lambda t: True,  # se evalúa condicionalmente
    "tono_respetuoso": lambda t: True,  # se evalúa condicionalmente (palabras prohibidas / mayúsculas)
}

PALABRAS_PROHIBIDAS = ["callate", "cállate", "estúpido", "estupido", "idiota", "hdp", "boludo", "tarado", "pelotudo"]
FRASES_NO_INTERES = ["no me interesa", "no estoy interesado", "no estoy interesada", "no quiero",
                     "no me llame", "no me moleste", "ya tengo", "no gracias"]
CIERRES_CORTES = ["gracias", "que tenga un buen día", "buen día", "hasta luego", "no lo molestamos",
                  "no le molesto", "lo dejo", "chau", "hasta pronto"]


def a_texto(transcripcion):
    if isinstance(transcripcion, str):
        return transcripcion
    lineas = []
    for turno in transcripcion:
        speaker = str(turno.get("speaker", "")).upper()
        etiqueta = "BOT" if speaker in ("BOT", "AGENTE", "AGENT", "ASISTENTE") else "CLIENTE"
        lineas.append(f"[{etiqueta}] {turno.get('text', '')}")
    return "\n".join(lineas)


def evaluar_heuristicas(item):
    texto = a_texto(item.get("transcripcion", []))
    t = texto.lower()
    scores = {}
    for nombre, fn in REGLA_HEURISTICA.items():
        scores[nombre] = {"value": round(float(fn(t)), 2), "reason": ""}
    # maneja_no_interes: solo si hubo manifestación
    hay_no_interes = any(f in t for f in FRASES_NO_INTERES)
    if hay_no_interes:
        loop = t.count("no puedo transferir") + t.count("¿está seguro")
        cierre = any(c in t for c in CIERRES_CORTES)
        scores["maneja_no_interes"] = {
            "value": 1.0 if (cierre and loop == 0) else 0.0,
            "reason": "cierre cortés" if (cierre and loop == 0) else "insistió o no cerró cortés",
        }
    else:
        scores["maneja_no_interes"] = {"value": 1.0, "reason": "no hubo manifestación de no-interés"}
    # listado_max_3: contar propiedades listadas
    lista = re.findall(r"[\d]+[º°]?\s*(?:piso|depto|departamento|lote|unidad|torre|ambientes)", texto, re.I)
    hay_listado = "listado" in texto or "opciones" in texto or any(p in t for p in
                     ["departamento", "lote", "casa", "oficina", "local", "unidad"])
    if hay_listado:
        scores["listado_max_3"] = {"value": 1.0 if len(lista) <= 3 else 0.0, "reason": f"{len(lista)} ítems listados"}
    else:
        scores["listado_max_3"] = {"value": 1.0, "reason": "no hubo listado"}
    # tono_respetuoso
    if any(p in t for p in PALABRAS_PROHIBIDAS):
        scores["tono_respetuoso"] = {"value": 0.0, "reason": "palabra prohibida"}
    else:
        mayus = [p.strip(".,;:()¿?¡!\"'") for p in texto.split()
                 if len(p.strip(".,;:()¿?¡!\"'")) > 3 and p.strip(".,;:()¿?¡!\"'").isupper()
                 and "[" not in p and "]" not in p]
        scores["tono_respetuoso"] = {"value": 0.0 if len(mayus) > 3 else 1.0,
                                     "reason": f"mayúsculas: {mayus[:3]}" if len(mayus) > 3 else "tono respetuoso"}
    return scores, texto


# ─────────────────────── B. LLM-JUDGES (7 reglas) ───────────────────────

REGLAS_LLM_OUTBOUND = {
    "se_presenta": (
        "sePresenta: El bot se identifica como Grupo Proaco al inicio de la llamada. "
        "Puntuá 1.0 si dice 'Grupo Proaco' o 'Proaco' al principio. "
        "Puntuá 0.5 si se presenta genéricamente pero no dice la marca. "
        "Puntuá 0.0 si no se presenta."
    ),
    "menciona_proposito": (
        "mencionaProposito: El bot explica el motivo de la llamada (campaña, emprendimiento, interés previo). "
        "Puntuá 1.0 si dice por qué llama. "
        "Puntuá 0.5 si es ambiguo. "
        "Puntuá 0.0 si no explica el motivo."
    ),
    "pide_consentimiento": (
        "pideConsentimiento: El bot pregunta si puede continuar / es buen momento. "
        "Puntuá 1.0 si pregunta explícitamente. "
        "Puntuá 0.5 si lo implica. "
        "Puntuá 0.0 si no pregunta y continúa directo."
    ),
    "maneja_no_interes": (
        "manejaNoInteres: Ante 'no me interesa', el bot cierra cortésmente sin insistir. "
        "Puntuá 1.0 si cierra con gracia. "
        "Puntuá 0.5 si insiste una vez. "
        "Puntuá 0.0 si insiste más de una vez o no cierra."
    ),
    "ofrece_agendar_cita": (
        "ofreceAgendarCita: Si hay interés, el bot ofrece agendar cita/visita. "
        "Puntuá 1.0 si ofrece agendar o derivar a asesor. "
        "Puntuá 0.5 si menciona opciones pero no concreta. "
        "Puntuá 0.0 si no ofrece nada."
    ),
    "listado_max_3": (
        "listadoMax3: Si lista propiedades, de a máximo 3 y solo lo que pidió el lead. "
        "Puntuá 1.0 si lista 1-3 propiedades correctas. "
        "Puntuá 0.5 si lista más de 3 o incluye incorrectas. "
        "Puntuá 0.0 si lista muchas sin filtrar."
    ),
    "tono_respetuoso": (
        "tonoRespetuoso: El bot mantiene un tono respetuoso, sin insultos ni agresividad. "
        "Puntuá 1.0 si el tono es cortés durante toda la llamada. "
        "Puntuá 0.0 si hay insultos, gritos o agresividad."
    ),
}


def build_system_prompt():
    return (
        "Eres un evaluador estricto del voicebot de LAMADAS SALIENTES de Grupo Proaco "
        "(conversational AI. Un lead recibe una llamada del bot). "
        "Recibís un criterio individual y una transcripción en formato [BOT]/[CLIENTE]. "
        "Puntuás SOLO ese criterio con un score de 0 a 1 y una razón. "
        "Respondé EXACTAMENTE con JSON: {\"score\": 0.X, \"reason\": \"...\"}"
    )


def llamar_modelo(system_prompt, user_prompt, modelo, max_retries=6):
    """Llama al juez por HTTP directo. Soporta:
       - ollama/<modelo>      → http://localhost:11434/api/chat
       - <proveedor>/<modelo> → endpoint OpenAI-compatible vía env var de API key (OpenAI/Groq/Gemini).
    Sin litellm (su import cuelga por telemetría en redes bloqueadas).
    """
    tiempo_inicio = time.time()
    if modelo.startswith("ollama/"):
        modelo_name = modelo.split("/", 1)[1]
        url = "http://localhost:11434/api/chat"
        headers = {"Content-Type": "application/json"}
        clave = ""
        body = {
            "model": modelo_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 512},
        }
    else:
        proveedor, modelo_name = modelo.split("/", 1)
        env_var = {"openai": "OPENAI_API_KEY", "groq": "GROQ_API_KEY",
                   "gemini": "GEMINI_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
                   "together": "TOGETHER_API_KEY"}.get(proveedor)
        api_key = os.environ.get(env_var or "")
        if not api_key:
            raise SystemExit(f"Falta {env_var} para el proveedor '{proveedor}'")
        base = {"openai": "https://api.openai.com/v1", "groq": "https://api.groq.com/openai/v1",
                "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
                "deepseek": "https://api.deepseek.com/v1"}.get(proveedor)
        url = f"{base}/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        clave = api_key
        body = {
            "model": modelo_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 512,
        }
    import urllib.request
    import urllib.error
    import json as _json
    reintentos = max_retries
    for intento in range(reintentos):
        try:
            req = urllib.request.Request(
                url,
                data=_json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=90) as r:
                data = _json.load(r)
            if modelo.startswith("ollama/"):
                return data.get("message", {}).get("content")
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            print(f"    [error {e.code}] {e.reason}", file=sys.stderr)
            if intento < reintentos - 1:
                time.sleep(10 * (intento + 1))
        except Exception as e:
            print(f"    [error] {e}", file=sys.stderr)
            if intento < reintentos - 1:
                time.sleep(10 * (intento + 1))
    print(f"    [fail] {modelo} tras {int(time.time() - tiempo_inicio)}s", file=sys.stderr)
    return None


def parse_score_json(texto):
    if not texto:
        return 0.0, "modelo no respondió"
    m = re.search(r'\{[^{}]*"score"[^{}]*\}', texto, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group())
            return float(d.get("score", 0)), d.get("reason", "")
        except (json.JSONDecodeError, ValueError):
            pass
    scores = re.findall(r'"score"\s*:\s*([\d.]+)', texto)
    if scores:
        reasons = re.findall(r'"reason"\s*:\s*"([^"]*)"', texto)
        return float(scores[0]), reasons[0] if reasons else ""
    return 0.0, "no se pudo parsear"


def evaluar_llm(item, texto, juez):
    system_prompt = build_system_prompt()
    scores = {}
    for metrica, criterio in REGLAS_LLM_OUTBOUND.items():
        user_prompt = criterio + "\n\nTRANSCRIPCIÓN:\n" + texto
        raw = llamar_modelo(system_prompt, user_prompt, juez)
        score, reason = parse_score_json(raw)
        scores[metrica] = {"value": round(score, 2), "reason": reason}
    return scores


def evaluar_geval(item, texto, juez):
    system_prompt = build_system_prompt()
    reglas = {
        "cliente_no_interesado": (
            "Si el lead dice que no le interesa, el bot debe cerrar la llamada cortésmente, "
            "sin insistir ni repetir la oferta. Puntuá 0-1."
        ),
        "agendamiento_cita": (
            "Si el lead muestra interés, el bot debe ofrecer agendar una cita o derivarlo a un asesor. "
            "Puntuá 0-1."
        ),
    }
    scores = {}
    for metrica, criterio in reglas.items():
        user_prompt = criterio + "\n\nTRANSCRIPCIÓN:\n" + texto
        raw = llamar_modelo(system_prompt, user_prompt, juez)
        score, reason = parse_score_json(raw)
        scores[metrica] = {"value": round(score, 2), "reason": reason}
    return scores


# ─────────────────────────── MAIN ───────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sin-llm", action="store_true", help="solo heurísticas (sin LLM-judges)")
    parser.add_argument("--geval", action="store_true", help="sumar los GEval (cliente_no_interesado, agendamiento_cita)")
    parser.add_argument("--juez", default=JUEZ_DEFECTO, help=f"modelo juez. Default: {JUEZ_DEFECTO}")
    parser.add_argument("--limite", type=int, default=None, help="evaluar solo las primeras N llamadas")
    parser.add_argument("--fuerza", action="store_true", help="re-evaluar las ya evaluadas")
    parser.add_argument("--campaña", default=None, help="evaluar solo una campaña (substring)")
    args = parser.parse_args()

    if not os.path.exists(FUENTE):
        raise SystemExit(f"No existe {FUENTE}. Corré primero gail_masivo/exportar_gail.py")

    items = json.load(open(FUENTE, encoding="utf-8"))
    if args.campaña:
        items = [i for i in items if args.campaña.lower() in str(i["metadata"].get("campaign", "")).lower()]
    if args.limite:
        items = items[: args.limite]
    print(f"Llamadas a evaluar: {len(items)}")

    os.makedirs(EVAL_DIR, exist_ok=True)
    resultados = []
    if os.path.exists(RESULTADOS):
        raw = json.load(open(RESULTADOS, encoding="utf-8"))
        resultados = raw.get("resultados", raw) if isinstance(raw, dict) else raw

    hechas = {r["id"] for r in resultados} if not args.fuerza else set()
    pendientes = [i for i in items if i["id"] not in hechas]
    print(f"Ya evaluadas: {len(items) - len(pendientes)} · pendientes: {len(pendientes)}")

    for idx, item in enumerate(pendientes, 1):
        lid = item["id"]
        camp = item["metadata"].get("campaign", "?")
        flecha = "·"
        try:
            heur, texto = evaluar_heuristicas(item)
            entradas = {"heur": heur}
            if not args.sin_llm:
                entradas["llm"] = evaluar_llm(item, texto, args.juez)
                if args.geval:
                    entradas["geval"] = evaluar_geval(item, texto, args.juez)
            resultado = {"id": lid, "metadata": item["metadata"], "scores": entradas}
            resultados.append(resultado)
            json.dump(resultados, open(RESULTADOS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

            avg_h = sum(v["value"] for v in heur.values()) / len(heur)
            if "llm" in entradas:
                avg_l = sum(v["value"] for v in entradas["llm"].values()) / len(entradas["llm"])
                flecha = f"heur={avg_h:.2f} llm={avg_l:.2f}"
            else:
                flecha = f"heur={avg_h:.2f}"
            print(f"[{idx}/{len(pendientes)}] {camp[:28]:<28} {lid[-12:]:<14} {flecha}")
        except Exception as e:
            print(f"  ERROR en {lid}: {e}", file=sys.stderr)
            traceback.print_exc()

    # ── Resumen agregado ──
    resumen = resumir(resultados)
    json.dump({"resultados": resultados, "resumen": resumen},
              open(RESULTADOS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    imprimir_resumen(resumen)


def resumir(resultados):
    def _prom(quién):
        acc = {}
        n = 0
        for r in resultados:
            for cat, metrics in r["scores"].items():
                if quién and cat != quién:
                    continue
                for k, v in metrics.items():
                    acc.setdefault(k, []).append(v["value"])
                    n += 1
        return {k: round(sum(v) / len(v), 3) for k, v in acc.items()} if acc else {}

    por_campana = {}
    for r in resultados:
        camp = r["metadata"].get("campaign", "?")
        por_campana.setdefault(camp, []).append(r)

    res = {
        "n_llamadas": len(resultados),
        "heur": _prom("heur"),
        "llm": _prom("llm"),
        "geval": _prom("geval"),
        "global_heur": round(sum(_prom("heur").values()) / max(1, len(_prom("heur"))), 3),
        "global_llm": round(sum(_prom("llm").values()) / max(1, len(_prom("llm"))), 3),
        "por_campana": {},
    }
    for camp, rrs in por_campana.items():
        h = {}
        for r in rrs:
            for k, v in r["scores"].get("heur", {}).items():
                h.setdefault(k, []).append(v["value"])
        l = {}
        for r in rrs:
            for k, v in r["scores"].get("llm", {}).items():
                l.setdefault(k, []).append(v["value"])
        res["por_campana"][camp] = {
            "n": len(rrs),
            "heur": {k: round(sum(v) / len(v), 3) for k, v in h.items()},
            "llm": {k: round(sum(v) / len(v), 3) for k, v in l.items()},
        }
    return res


def imprimir_resumen(res):
    print("\n" + "=" * 70)
    print(f"RESUMEN MASIVO GAIL OUTBOUND · {res['n_llamadas']} llamadas")
    print("=" * 70)
    for label, key in [("Heurísticas", "heur"), ("LLM-judges 7 reglas", "llm"), ("GEval", "geval")]:
        data = res.get(key)
        if data:
            print(f"\n{label}:")
            for k, v in sorted(data.items()):
                print(f"  {k:28s} avg={v:.3f}")
    if res["por_campana"]:
        print("\nPor campaña:")
        for camp, d in sorted(res["por_campana"].items(), key=lambda x: -x[1]["n"]):
            h = d["heur"]
            gh = round(sum(h.values()) / max(1, len(h)), 3) if h else 0
            extra = ""
            if d["llm"]:
                gl = round(sum(d["llm"].values()) / max(1, len(d["llm"])), 3)
                extra = f" · llm={gl:.3f}"
            print(f"  {camp[:40]:<40} n={d['n']:>4}  heur={gh:.3f}{extra}")
    print("\nGuardado en:", RESULTADOS)


if __name__ == "__main__":
    main()