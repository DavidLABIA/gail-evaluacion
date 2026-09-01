"""Reintenta el export masivo GAIL hasta que el API de Lula deje de bloquear con 401.

Lógica:
  - Prueba GET /v1/campaigns cada N segundos.
  - Cuando el API responde 2xx o 4xx distinto de 401/429 → corre exportar_gail.py.
  - Log en reportes/export_log.txt. Ctrl+C para frenar.

Uso:
  export LULA_API_KEY="api-..."
  .venv/bin/python gail_masivo/reintentar_export.py [--cada 120] [--max-min 480]
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
API_BASE = "https://api.lula.com"
LOG = os.path.join(AQUI, "reportes", "export_log.txt")


def api_listo(api_key):
    req = urllib.request.Request(
        f"{API_BASE}/v1/campaigns",
        headers={"X-API-Key": api_key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return True, r.status
    except urllib.error.HTTPError as e:
        return False, e.code
    except Exception as e:
        return False, f"ERR {e}"


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    linea = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(linea)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(linea + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cada", type=int, default=120, help="segundos entre intentos")
    parser.add_argument("--max-min", type=int, default=1440, help="máx minutos a esperar")
    args = parser.parse_args()

    api_key = os.environ.get("LULA_API_KEY")
    if not api_key:
        raise SystemExit("Falta LULA_API_KEY")

    actual = os.path.dirname(os.path.abspath(__file__))
    exportador = os.path.join(actual, "exportar_gail.py")

    plazo = time.time() + args.max_min * 60
    intento = 0
    while time.time() < plazo:
        intento += 1
        ok, status = api_listo(api_key)
        if ok:
            log(f"API OK (HTTP {status}) en intento {intento} → corriendo exportar_gail.py")
            subprocess.run([sys.executable, exportador], check=False)
            log("export finalizado")
            return
        if status != 401:
            log(f"respuesta inesperada HTTP {status} en intento {intento} → corriendo export")
            subprocess.run([sys.executable, exportador], check=False)
            log("export finalizado")
            return
        log(f"HTTP 401 (bloqueo) intento {intento} → reintento en {args.cada}s")
        time.sleep(args.cada)
    log("tiempo de espera agotado")


if __name__ == "__main__":
    main()