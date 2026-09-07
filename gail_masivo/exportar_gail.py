"""Exporta TODAS las llamadas outbound reales de TODAS las campañas GAIL desde el API de Lula.

API: https://api.lula.com  (auth por header X-API-Key)
Flujo:
  1. GET /v1/campaigns                       → lista todas las campañas del tenant.
  2. GET /v1/campaigns/{id}/touchpoints?includeTranscripts=true  → llama por llama (con transcript).
  3. Convierte los transcripts (role: user/assistant/tool_call) a turnos [CLIENTE]/[BOT]/[TOOL].
  4. Etiqueta el ORIGEN de cada llamada (simulacion / prueba / real) según el nombre de campaña.
  5. Guarda data/llamadas_gail.json — un array plano con metadata: campaign / contacto / outcome /
     duration / publishedAt / finishedAt / touchpointId / origen.

Manejo de rate limits:
  - El API puede bloquear con HTTP 401/429 tras ráfagas. Se aplica backoff exponencial
    (y congelamiento largo ante bloqueo persistente de 401) y se reanuda desde donde iba.
  - La lista de campañas ya exportadas se guarda en data/campañas_procesadas.json para no re-bajarlas.

Origen del dato (GPS-438):
  - En el tenant GAIL outbound actual TODAS las llamadas son simulación (generadas por IA).
    Por defecto cada campaña se etiqueta `simulacion` salvo que contenga "real"/"prod"
    en el nombre o se fuerce con --origen.
  - --origen "<campaign_id>=real|prueba|simulacion>" sobreescribe por campaña (camino a producción).
  - --origen-default cambia el valor por defecto para todo el tenant.

Apagar transcripciones (GPS-438):
  - Con --sin-transcriptos se exporta la metadata y el origen pero SIN guardar las transcripciones
    (menos PII al pasar a producción). El pipeline de evaluación sigue corriendo sobre el subset
    que ya fue exportado con transcript previo.

Uso:
  export LULA_API_KEY="api-..."
  .venv/bin/python gail_masivo/exportar_gail.py [--solo "nombre campaña"] [--fuerza] [--sin-transcriptos]
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

# ─── Origen del dato (GPS-438) ────────────────────────────────────────
# Para el tenant GAIL outbound, TODAS las llamadas son SIMULACIÓN (generadas
# por IA, no tráfico real de clientes) mientras no haya producción. El default
# es `simulacion`; cuando una campaña pase a producción real se marca con
# --origen "<campaign_id>=real".
ORIGEN_DEFAULT = "simulacion"

# Patrones que forzan un origen distinto al default (se evalúan en orden:
# especificidad decreciente). Un substring "real"/"prod" fuerza `real`.
PATRONES_REAL = ["real", "prod", "produccion", "producción"]


def clasificar_origen(campaign_name, campaign_id, overrides=None, default=None):
    """Devuelve el origen ('real'|'prueba'|'simulacion') de una campaña.

    Regla por nombre de campaña, sobreescribible por (campaign_id -> origen)
    vía --origen. El default es ORIGEN_DEFAULT (simulacion), salvo que el nombre
    indique claramente producción real.
    """
    if default is None:
        default = ORIGEN_DEFAULT
    if overrides and campaign_id in overrides:
        return overrides[campaign_id]
    n = str(campaign_name or "").lower()
    if any(p in n for p in PATRONES_REAL):
        return "real"
    if cid := str(campaign_id or "").lower():
        if cid in ("prod", "production", "produccion") or "real" in cid:
            return "real"
    return default


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
    parser.add_argument("--sin-transcriptos", action="store_true",
                        help="no guardar transcripciones (menos PII, para producción)")
    parser.add_argument("--origen", action="append", default=[],
                        help="sobreescribir origen: '<campaign_id>=<real|prueba|simulacion>'")
    parser.add_argument("--origen-default", default=ORIGEN_DEFAULT,
                        choices=["real", "prueba", "simulacion"],
                        help=f"origen por defecto cuando no hay override/patrón. Default: {ORIGEN_DEFAULT}")
    args = parser.parse_args()

    overrides = {}
    for ov in args.origen:
        if "=" in ov:
            cid, org = ov.split("=", 1)
            org = org.strip().lower()
            if org not in ("real", "prueba", "simulacion"):
                print(f"  ⚠ origen inválido '{org}' en --origen {ov}; se ignora", file=sys.stderr)
                continue
            overrides[cid.strip()] = org

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
        origen = clasificar_origen(nombre, cid, overrides, args.origen_default)
        print(f"· exportando {nombre!r} (id={cid}) · origen={origen}")
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
            if args.sin_transcriptos:
                turnos = []  # no guardar PII de transcripción
            else:
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
                "origen": origen,
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
    por_origen = {}
    for t in todas:
        camp = t["metadata"]["campaign"]
        totales[camp] = totales.get(camp, 0) + 1
        org = t["metadata"].get("origen", "real")
        por_origen.setdefault(org, 0)
        por_origen[org] += 1
    print(f"\nGuardadas {len(todas)} transcripciones en {SALIDA}")
    for camp, n in sorted(totales.items()):
        print(f"  - {camp}: {n} llamadas")
    con_turnos = sum(1 for t in todas if isinstance(t["transcripcion"], list) and t["transcripcion"])
    print(f"  ({con_turnos} con turnos [BOT]/[CLIENTE])")
    print(f"\nPor origen: " + " · ".join(f"{org}={n}" for org, n in sorted(por_origen.items())))
    if args.sin_transcriptos:
        print("  [--sin-transcriptos] No se guardaron transcripciones (solo metadata).")


if __name__ == "__main__":
    main()