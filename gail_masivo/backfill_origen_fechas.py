"""Backfill de origen + fechas en los resultados de evaluación sin re-evaluar.

Agrega a evaluacion/resultados_masivos.json:
  - metadata.origen    (simulacion/prueba/real) según la regla de exportar_gail
  - metadata.publishedAt / finishedAt  (ya presentes en data/llamadas_gail.json)

Reconcilia cada resultado con el metadata del fuente (data/llamadas_gail.json)
preservando los scores ya calculados, y regenera el resumen (incluye por_origen).

Uso:
  .venv/bin/python gail_masivo/backfill_origen_fechas.py
"""

import json
import os
import sys
from collections import defaultdict

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

from exportar_gail import clasificar_origen  # noqa: E402

FUENTE = os.path.join(AQUI, "data", "llamadas_gail.json")
RESULTADOS = os.path.join(AQUI, "evaluacion", "resultados_masivos.json")


def main():
    if not os.path.exists(FUENTE) or not os.path.exists(RESULTADOS):
        raise SystemExit("Faltan data/llamadas_gail.json o evaluacion/resultados_masivos.json")

    items = json.load(open(FUENTE, encoding="utf-8"))
    meta_por_id = {}
    for it in items:
        m = it.get("metadata", {})
        m2 = dict(m)
        if "origen" not in m2:
            m2["origen"] = clasificar_origen(m.get("campaign", ""), m.get("campaign_id", ""))
        meta_por_id[it["id"]] = m2

    raw = json.load(open(RESULTADOS, encoding="utf-8"))
    resultados = raw.get("resultados", raw) if isinstance(raw, dict) else raw

    cambiados = 0
    for r in resultados:
        mfuente = meta_por_id.get(r.get("id"))
        if not mfuente:
            continue
        if r.get("metadata") != mfuente:
            r["metadata"] = mfuente
            cambiados += 1

    print(f"Metadatas actualizados: {cambiados}")

    # Regenerar resumen (reusa la lógica de evaluar_masivo.resumir)
    from evaluar_masivo import resumir
    resumen = resumir(resultados)
    json.dump({"resultados": resultados, "resumen": resumen},
              open(RESULTADOS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"Guardado: {RESULTADOS}")
    print(f"Llamadas: {len(resultados)}")
    for org, d in sorted(resumen.get("por_origen", {}).items()):
        print(f"  {org}: {d['n']}")


if __name__ == "__main__":
    main()