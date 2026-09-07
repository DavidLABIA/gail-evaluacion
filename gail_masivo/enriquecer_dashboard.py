"""Enriquece el bloque DATOS incrustado en dashboard-evaluacion-gail.html
con `origen`, `publishedAt` y `finishedAt` desde evaluacion/resultados_masivos.json.

Cada registro del bloque DATOS se cruza por `id`. Los campos nuevos se agregan
siempre (sin romper el resto). Reemplaza el array `const DATOS = [...];`.

Uso:
  .venv/bin/python gail_masivo/enriquecer_dashboard.py
"""

import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RESULTADOS = os.path.join(AQUI, "evaluacion", "resultados_masivos.json")
DASHBOARD = os.path.join(os.path.dirname(AQUI), "dashboard-evaluacion-gail.html")


def main():
    if not os.path.exists(RESULTADOS) or not os.path.exists(DASHBOARD):
        raise SystemExit("Faltan resultados_masivos.json o dashboard-evaluacion-gail.html")

    data = json.load(open(RESULTADOS, encoding="utf-8"))
    resultados = data.get("resultados", data) if isinstance(data, dict) else data
    meta = {}
    for r in resultados:
        meta[r["id"]] = r.get("metadata", {})

    html = open(DASHBOARD, encoding="utf-8").read()

    m = re.search(r"const DATOS =\s*(\[.*?\])\s*;", html, re.DOTALL)
    if not m:
        raise SystemExit("No se encontró 'const DATOS = [...]' en el dashboard")

    datos = json.loads(m.group(1))
    modificados = 0
    for d in datos:
        md = meta.get(d.get("id"))
        if not md:
            continue
        for campo in ("origen", "publishedAt", "finishedAt"):
            val = md.get(campo)
            if val is None and campo == "origen":
                val = "simulacion"
            if val is not None:
                if d.get(campo) != val:
                    d[campo] = val
                    modificados += 1
    nuevo = "const DATOS =\n" + json.dumps(datos, ensure_ascii=False, separators=(",", ":")) + "\n;\n"
    html = html[: m.start()] + nuevo + html[m.end():]

    open(DASHBOARD, "w", encoding="utf-8").write(html)
    print(f"Campos actualizados en {modificados} registros")
    print(f"Dashboard actualizado: {DASHBOARD}")


if __name__ == "__main__":
    main()