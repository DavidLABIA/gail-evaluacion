"""Exporta TODAS las llamadas outbound reales de TODAS las campañas GAIL desde el API de Lula.

API: https://api.lula.com  (auth por header X-API-Key)
Flujo:
  1. GET /v1/campaigns                       → lista todas las campañas del tenant.
  2. GET /v1/campaigns/{id}/touchpoints?includeTranscripts=true  → llama por llama (con transcript).
  3. Convierte los transcripts (role: user/assistant/tool_call) a turnos [CLIENTE]/[BOT]/[TOOL].
  4. Guarda data/llamadas_gail.json — un array plano con metadata: campaign / contacto / outcome /
     duration / publishedAt / finishedAt / touchpointId.

Manejo de rate limits:
  - El API puede bloquear con HTTP 401/429 tras ráfagas. Se aplica backoff exponencial
    (y congelamiento largo ante bloqueo persistente de 401) y se reanuda desde donde iba.
  - La lista de campañas ya exportadas se guarda en data/campañas_procesadas.json para no re-bajarlas.

Uso:
  export LULA_API_KEY="api-..."
  .venv/bin/python gail_masivo/exportar_gail.py [--solo "nombre campaña"] [--fuerza]
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_BASE = "https://api.lula.com"
AQUI = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(AQUI, "data")
SALIDA = os.path.join(DATA_DIR, "llamadas_gail.json")
CAMPAÑAS_JSON = os.path.join(DATA_DIR, "campañas_procesadas.json")
LOCK_JSON = os.path.join(DATA_DIR, "export_lock.json")

BACKOFF_401 = 300       # segundos a esperar cuando el API devuelve 401 (bloqueo de rate limit)
BACKOFF_429 = 60        # segundos a esperar cuando devuelve 429
SLEEP_ENTRE_CAMPANAS = 2  # segundos entre campañas para no disparar el rate limit
SLEEP_ENTRE_PAGINAS = 1  # segundos entre páginas de touchpoints


def requester(url, api_key, reintentos=8):
    """GET con retry: 429→backoff 60s, 401 persistente→backoff 5min (hasta N intentos)."""
    req = urllib.request.Request(url, headers={"X-API-Key": api_key, "Accept": "application/json"})
    for intento in range(reintentos):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                espera = BACKOFF_429 if e.code == 429 else 5
                print(f"  HTTP {e.code} en {url} → reintento {intento + 1}/{reintentos} en {espera}s", file=sys.stderr)
                time.sleep(espera)
                continue
            if e.code == 401:
                espera = BACKOFF_401
                print(f"  HTTP 401 (bloqueo) en {url} → reintento {intento + 1}/{reintentos} en {espera}s", file=sys.stderr)
                time.sleep(espera)
                continue
            raise (SystemExit(f"Error HTTP {e.code} en {url}: {e.reason}"))
        except Exception as e:
            print(f"  Error transitorio: {e} → reintento {intento + 1}/{reintentos} en 10s", file=sys.stderr)
            time.sleep(10)
    raise SystemExit(f"No se pudo consultar (persistente): {url}")


def paginar_touchpoints(campaign_id, api_key, limit=100):
    """Recorre la paginación cursor (after) del endpoint de touchpoints con transcripts."""
    items = []
    after = None
    while True:
        url = f"{API_BASE}/v1/campaigns/{campaign_id}/touchpoints?includeTranscripts=true&limit={limit}"
        if after:
            url += f"&after={after}"
        body = requester(url, api_key)
        data = body.get("data", [])
        items.extend(data)
        total = body.get("total")
        if not data:
            break
        last = data[-1].get("touchpointId") or data[-1].get("id")
        if total is not None and len(items) >= total:
            break
        if not last or last == after:
            break
        after = last
        time.sleep(SLEEP_ENTRE_PAGINAS)
    return items


def a_turnos(transcript):
    """Normaliza un transcript (role: user/assistant/tool_call) a turnos [CLIENTE]/[BOT]/[TOOL]."""
    if not transcript:
        return []
    if isinstance(transcript, str):
        return transcript
    lineas = []
    for t in transcript:
        if not isinstance(t, dict):
            continue
        role = str(t.get("role", "")).lower()
        etiqueta = {"user": "CLIENTE", "assistant": "BOT", "tool_call": "TOOL",
                    "tool_call_result": "TOOL", "system": "SISTEMA",
                    "function": "TOOL", "function_call": "TOOL"}.get(role, role.upper())
        texto = t.get("content", "") or t.get("text", "")
        if isinstance(texto, list):
            texto = " ".join(str(part.get("text", "")) for part in texto if isinstance(part, dict))
        texto = str(texto).strip()
        if not texto:
            continue
        lineas.append({"speaker": etiqueta, "text": texto})
    return lineas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--solo", default=None, help="nombre (substring) de campaña a exportar")
    parser.add_argument("--fuerza", action="store_true", help="re-exportar campañas ya procesadas")
    args = parser.parse_args()

    api_key = os.environ.get("LULA_API_KEY")
    if not api_key:
        raise SystemExit("Falta LULA_API_KEY (export LULA_API_KEY=\"api-...\")")

    os.makedirs(DATA_DIR, exist_ok=True)
    todas = json.load(open(SALIDA, encoding="utf-8")) if os.path.exists(SALIDA) else []
    ids_vistos = {t["metadata"]["touchpointId"] for t in todas if "touchpointId" in t["metadata"]}
    procesadas = set(json.load(open(CAMPAÑAS_JSON, encoding="utf-8"))) if os.path.exists(CAMPAÑAS_JSON) else set()

    print("Listando campañas del tenant GAIL...")
    resp = requester(f"{API_BASE}/v1/campaigns", api_key)
    campañas = resp if isinstance(resp, list) else resp.get("data", resp.get("campaigns", []))
    print(f"Total campañas en el API: {len(campañas)}")

    for c in campañas:
        nombre = c.get("name", "sin-nombre")
        cid = c.get("id")
        if args.solo and args.solo.lower() not in str(nombre).lower():
            continue
        if not args.fuerza and cid in procesadas:
            print(f"· ya procesada: {nombre}")
            continue
        print(f"· exportando: {nombre!r} (id={cid})")
        touchpoints = paginar_touchpoints(cid, api_key)
        con_transcript = 0
        for t in touchpoints:
            transcript = t.get("transcript")
            nombre_contacto = " ".join(filter(None, [t.get("contactFirstName"), t.get("contactLastName")])) or "sin-nombre"
            duration = t.get("duration") or 0
            outcome = t.get("outcome") or t.get("status") or "unknown"
            tipo = t.get("type") or t.get("message") or "unknown"
            tid = t.get("touchpointId") or t.get("id")
            if t.get("errorMessage"):
                continue
            if not transcript and not t.get("conversationId"):
                continue
            turnos = a_turnos(transcript)
            if not turnos:
                continue
            acc = t.get("additionalData") or {}
            metadata = {
                "proyecto": "gail",
                "flow": "outbound",
                "campaign_id": cid,
                "campaign": nombre,
                "contacto": nombre_contacto,
                "phone": t.get("phoneNumber"),
                "outcome": outcome,
                "duration": duration,
                "type": tipo,
                "touchpointId": tid,
                "contactId": t.get("contactId"),
                "externalId": t.get("externalId"),
                "publishedAt": t.get("publishedAt"),
                "finishedAt": t.get("finishedAt"),
                "conversationId": t.get("conversationId"),
                "customFields": acc.get("customFields"),
            }
            if tid in ids_vistos:
                continue
            ids_vistos.add(tid)
            todas.append({"id": f"{cid}-{tid}" if tid else f"{cid}-{len(todas)}",
                          "transcripcion": turnos, "metadata": metadata})
            con_transcript += 1
        print(f"   → {len(touchpoints)} touchpoints, {con_transcript} con transcript")
        procesadas.add(cid)
        json.dump(sorted(procesadas), open(CAMPAÑAS_JSON, "w", encoding="utf-8"), indent=2)
        time.sleep(SLEEP_ENTRE_CAMPANAS)

    json.dump(todas, open(SALIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    totales = {}
    for t in todas:
        camp = t["metadata"]["campaign"]
        totales[camp] = totales.get(camp, 0) + 1
    print(f"\nGuardadas {len(todas)} transcripciones en {SALIDA}")
    for camp, n in sorted(totales.items()):
        print(f"  - {camp}: {n} llamadas")
    con_turnos = sum(1 for t in todas if isinstance(t["transcripcion"], list) and t["transcripcion"])
    print(f"  ({con_turnos} con turnos [BOT]/[CLIENTE])")


if __name__ == "__main__":
    main()