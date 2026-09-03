"""Juez LLM confiable por HTTP directo para GAIL (sin litellm).

Reemplaza a litellm (su import cuelga por telemetría en redes bloqueadas).
Usa Ollama local vía /api/chat, con reintentos y parseo robusto de JSON.

Compartido por los evaluadores DeepEval / Opik / LangSmith de GAIL.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"

# Las 7 reglas outbound GAIL (mismas que el pipeline masivo)
REGLAS_OUTBOUND = {
    "se_presenta": (
        "El bot se identifica como la marca al inicio de la llamada. "
        "Puntuá 1.0 si dice la marca al principio. "
        "Puntuá 0.5 si se presenta genéricamente. "
        "Puntuá 0.0 si no se presenta."
    ),
    "menciona_proposito": (
        "El bot explica el motivo de la llamada (campaña, emprendimiento, interés previo). "
        "Puntuá 1.0 si dice por qué llama. "
        "Puntuá 0.5 si es ambiguo. "
        "Puntuá 0.0 si no explica el motivo."
    ),
    "pide_consentimiento": (
        "El bot pregunta si puede continuar / es buen momento. "
        "Puntuá 1.0 si pregunta explícitamente. "
        "Puntuá 0.5 si lo implicita. "
        "Puntuá 0.0 si no pregunta y continúa directo."
    ),
    "maneja_no_interes": (
        "Ante 'no me interesa', el bot cierra cortésmente sin insistir. "
        "Puntuá 1.0 si cierra con gracia. "
        "Puntuá 0.5 si insiste una vez. "
        "Puntuá 0.0 si insiste más de una vez."
    ),
    "ofrece_agendar_cita": (
        "Si hay interés, el bot ofrece agendar cita/visita o derivar a asesor. "
        "Puntuá 1.0 si ofrece agendar o derivar. "
        "Puntuá 0.5 si menciona opciones pero no concreta. "
        "Puntuá 0.0 si no ofrece nada."
    ),
    "listado_max_3": (
        "Si lista propiedades, de a máximo 3 y solo lo que pidió el lead. "
        "Puntuá 1.0 si lista 1-3 propiedades correctas. "
        "Puntuá 0.5 si lista más de 3 o incluye incorrectas. "
        "Puntuá 0.0 si lista muchas sin filtrar."
    ),
    "tono_respetuoso": (
        "El bot mantiene un tono respetuoso, sin insultos ni agresividad. "
        "Puntuá 1.0 si el tono es cortés durante toda la llamada. "
        "Puntuá 0.0 si hay insultos, gritos o agresividad."
    ),
}

MODELO_DEFAULT = "qwen2.5:7b"


def build_system_prompt():
    return (
        "Eres un evaluador estricto del voicebot de llamadas salientes de GAIL. "
        "Un lead recibe una llamada del bot (transcripción en formato [BOT]/[CLIENTE]). "
        "Recibís un criterio individual y debés puntuarlo con un score de 0 a 1 y una razón. "
        "Respondé EXACTAMENTE con JSON: {\"score\": 0.X, \"reason\": \"...\"}"
    )


def llamar_modelo(system_prompt, user_prompt, modelo=MODELO_DEFAULT, max_retries=6):
    """Llama al juez por HTTP directo a Ollama. Devuelve el texto crudo o None."""
    model_name = modelo.split("/", 1)[1] if "/" in modelo else modelo
    body = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 512},
    }
    for intento in range(max_retries):
        try:
            req = urllib.request.Request(
                OLLAMA_URL,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
            return data.get("message", {}).get("content")
        except urllib.error.HTTPError as e:
            print(f"    [error {e.code}] {e.reason}", file=sys.stderr)
        except Exception as e:
            print(f"    [error] {e}", file=sys.stderr)
        if intento < max_retries - 1:
            time.sleep(10 * (intento + 1))
    return None


def parse_score_json(texto):
    """Extrae {"score": float, "reason": str} de la respuesta del juez."""
    if not texto:
        return 0.0, "modelo no respondió"
    m = re.search(r'\{[^{}]*"score"[^{}]*\}', texto, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group())
            return float(d.get("score", 0)), str(d.get("reason", ""))
        except (json.JSONDecodeError, ValueError):
            pass
    scores = re.findall(r'"score"\s*:\s*([\d.]+)', texto)
    if scores:
        reasons = re.findall(r'"reason"\s*:\s*"([^"]*)"', texto)
        return float(scores[0]), reasons[0] if reasons else ""
    return 0.0, "no se pudo parsear"


def evaluar_item(texto, modelo=MODELO_DEFAULT, sin_llm=False):
    """Evalúa un texto de transcripción con las 7 reglas. Devuelve {regla: {value, reason}}."""
    system_prompt = build_system_prompt()
    scores = {}
    for metrica, criterio in REGLAS_OUTBOUND.items():
        if sin_llm:
            scores[metrica] = {"value": 0.0, "reason": "(sin LLM)"}
            continue
        user_prompt = (f"{criterio}\n\nTRANSCRIPCIÓN:\n{texto}")
        raw = llamar_modelo(system_prompt, user_prompt, modelo)
        score, reason = parse_score_json(raw)
        scores[metrica] = {"value": round(score, 2), "reason": reason}
    return scores


def a_texto(transcripcion):
    """Normaliza una transcripción (string, dict o lista de turnos) a texto [BOT]/[CLIENTE]."""
    if isinstance(transcripcion, str):
        return transcripcion
    if isinstance(transcripcion, dict):
        transcripcion = transcripcion.get("conversation") or transcripcion.get("transcripcion", [])
    lineas = []
    for turno in transcripcion:
        if not isinstance(turno, dict):
            continue
        speaker = str(turno.get("speaker") or turno.get("role") or "?").upper()
        etiqueta = "BOT" if speaker in ("BOT", "AGENTE", "AGENT", "ASISTENTE") else "CLIENTE"
        lineas.append(f"[{etiqueta}] {turno.get('text') or turno.get('content') or ''}")
    return "\n".join(lineas)


def cargar_resultados_masivos(ruta):
    """Carga el checkpoint del pipeline masivo (para poder comparar clientes/IDs)."""
    with open(ruta, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("resultados", data)
    return data


def promedio(diccionario):
    vals = [v["value"] for v in diccionario.values()]
    return round(sum(vals) / len(vals), 3) if vals else 0.0