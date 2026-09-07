"""Genera una versión anonimizada de evaluacion/resultados_masivos.json.

Reemplaza contacto por "Contacto 001/002/...", phone por "XXXX-XXXX",
contactId y externalId por hashes truncados. Conserva: campaign, outcome,
duration, scores, origen, fechas, touchpointId (son hashes internos).

Salida: evaluacion/resultados_anon.json (mismo esquema, datos anonimizados).

Uso:
  .venv/bin/python gail_masivo/anonimizar_datos.py
"""

import json
import os
import re

AQUI = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(AQUI, "evaluacion", "resultados_masivos.json")
DST = os.path.join(AQUI, "evaluacion", "resultados_anon.json")
MAP_FILE = os.path.join(AQUI, "evaluacion", "contacto_anon_map.json")


def load_map():
    if os.path.exists(MAP_FILE):
        return json.load(open(MAP_FILE, encoding="utf-8"))
    return {}


def save_map(m):
    json.dump(m, open(MAP_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def anon_contacto(nombre, cmap):
    nombre = str(nombre or "sin-nombre").strip()
    if not nombre or nombre == "sin-nombre":
        return "Contacto ---"
    if nombre in cmap:
        return cmap[nombre]
    idx = len(cmap) + 1
    anon = f"Contacto {idx:03d}"
    cmap[nombre] = anon
    return anon


def anon_phone(phone):
    if not phone:
        return ""
    s = str(phone)
    digits = re.sub(r'\D', '', s)
    if len(digits) >= 7:
        return f"XXXX-{digits[-4:]}"
    return "XXXX"


def anon_id(ident):
    if not ident:
        return ""
    return str(ident)[:8]


def main():
    if not os.path.exists(SRC):
        raise SystemExit(f"No existe {SRC}")

    data = json.load(open(SRC, encoding="utf-8"))
    resultados = data.get("resultados", data) if isinstance(data, dict) else data
    resumen = data.get("resumen", {}) if isinstance(data, dict) else {}

    cmap = load_map()
    antes = len(cmap)

    for r in resultados:
        m = r.get("metadata", {})
        if "contacto" in m:
            m["contacto"] = anon_contacto(m["contacto"], cmap)
        if "phone" in m:
            m["phone"] = anon_phone(m["phone"])
        if "contactId" in m:
            m["contactId"] = anon_id(m["contactId"])
        if "externalId" in m:
            m["externalId"] = anon_id(m["externalId"])

    save_map(cmap)
    nuevos = len(cmap) - antes

    salida = {"resultados": resultados, "resumen": resumen}
    json.dump(salida, open(DST, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Anonimizados: {len(resultados)} registros · {nuevos} contactos nuevos → {DST}")


if __name__ == "__main__":
    main()