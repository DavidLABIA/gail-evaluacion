"""Anonimiza datos sensibles (contactos, phones) en dashboards HTML generados.

Reemplaza nombres de contacto por "Contacto 001/002/...", teléfonos por "XXXX-XXXX"
y contactId/externalId por hashes truncados. Conserva: campañas, outcomes, scores,
fechas, origen, ids (son hashes internos, no identifican personas).

Puede trabajar sobre dos formatos:
  A. const DATOS = [...] (dashboard-evaluacion-gail.html) — reemplaza contacto/phone
  B. <tr><td>Contacto</td>... (tablas HTML estáticas de generar_dashboard.py)

Uso:
  python gail_masivo/anonimizar.py --input archivo.html --output archivo-anon.html
  python gail_masivo/anonimizar.py --inplace dashboard.html   (reemplaza en el mismo archivo)
"""

import argparse
import hashlib
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))

# ─── Mapa estable contacto→anon_id (persistente entre corridas) ─────
CONTACTO_MAP_FILE = os.path.join(AQUI, "evaluacion", "contacto_anon_map.json")


def load_contacto_map():
    if os.path.exists(CONTACTO_MAP_FILE):
        return json.load(open(CONTACTO_MAP_FILE, encoding="utf-8"))
    return {}


def save_contacto_map(m):
    json.dump(m, open(CONTACTO_MAP_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def anon_contacto(nombre, contacto_map):
    """Devuelve 'Contacto 001' etc. de forma estable (siempre el mismo nombre → el mismo ID)."""
    nombre = str(nombre or "sin-nombre").strip()
    if not nombre or nombre == "sin-nombre":
        return "Contacto ---"
    if nombre in contacto_map:
        return contacto_map[nombre]
    idx = len(contacto_map) + 1
    anon = f"Contacto {idx:03d}"
    contacto_map[nombre] = anon
    return anon


def anon_phone(phone):
    """Reemplaza teléfono por placeholder sin perder formato."""
    if not phone:
        return ""
    s = str(phone)
    # conservar últimos 4 dígitos si hay 7+
    digits = re.sub(r'\D', '', s)
    if len(digits) >= 7:
        return f"XXXX-{digits[-4:]}"
    return "XXXX"


def anon_id(ident):
    """Trunca un hash a 8 chars para que no sea rastreable."""
    if not ident:
        return ""
    return str(ident)[:8]


# ─── Anonimizar const DATOS = [...] ──────────────────────────────────

def anonimizar_datos_js(html, contacto_map):
    """Reemplaza campos contacto/phone/contactId/externalId en el bloque const DATOS."""
    m = re.search(r"(const DATOS =\s*\[)(.*?)(\]\s*;)", html, re.DOTALL)
    if not m:
        return html, 0

    datos = json.loads("[" + m.group(2) + "]")
    modificados = 0
    for d in datos:
        if "contacto" in d:
            nuevo = anon_contacto(d["contacto"], contacto_map)
            if nuevo != d["contacto"]:
                d["contacto"] = nuevo
                modificados += 1
        if "phone" in d:
            d["phone"] = anon_phone(d["phone"])
        if "contactId" in d:
            d["contactId"] = anon_id(d["contactId"])
        if "externalId" in d:
            d["externalId"] = anon_id(d["externalId"])

    nuevo_bloque = m.group(1) + json.dumps(datos, ensure_ascii=False, separators=(",", ":"))[1:-1] + m.group(3)
    html = html[:m.start()] + nuevo_bloque + html[m.end():]
    return html, modificados


# ─── Anonimizar tablas HTML estáticas ────────────────────────────────

def anonimizar_tablas_html(html, contacto_map):
    """Busca filas de tabla <tr> con <td>Contacto</td> y anonimiza los primeros <td> que sean nombres."""
    # Patrón: <tr>...<td>Nombre Apellido</td> (el contacto suele ser el primer td)
    patrones = [
        # tabla llamadas de generar_dashboard: <td>contacto</td> como primer td en <tr>
        (r'(<tr style="border-bottom:1px solid #334155"[^>]*>.*?)'
         r'<td[^>]*>([^<]{2,50})</td>'
         r'(<td[^>]*>[^<]*</td>){0,2}', None),  # skip, usar otro approach
    ]
    # Approach simpler: reemplazar strings de contacto conocidos en cualquier td
    # Usar el mapa contacto_map invertido (anon→real) para buscar y reemplazar
    # Mejor: buscar patrón de nombre en td después de data-camp
    modificados = 0

    # Para tablas de generar_dashboard.py: el contacto aparece como primer td de <tr>
    # con estilo border-bottom:1px solid #334155
    def reemplazar_td_contacto(match):
        nonlocal modificados
        contenido = match.group(2).strip()
        # Si parece nombre (no es score, badge, número, icono, fecha, etc.)
        if (len(contenido) < 3 or len(contenido) > 50 or
            re.match(r'^[\d.%\-/]+$', contenido) or
            re.match(r'^(badge|span|div|<)', contenido) or
            contenido in ('✅', '—', '0.00', '0', '') or
            re.match(r'^\d+s$', contenido)):
            return match.group(0)
        # Buscar en el mapa invertido
        for real, anon in contacto_map.items():
            if anon == contenido:
                return match.group(0)  # ya anonimizado
        # Si el contenido parece un nombre real, anonimizar
        nuevo = anon_contacto(contenido, contacto_map)
        if nuevo != contenido:
            modificados += 1
            return match.group(1) + '<td' + match.group(2) + '</td>' + match.group(3)
        return match.group(0)

    return html, modificados


def anonimizar_html(html_texto, contacto_map):
    """Anonimiza todo el HTML: bloque JS + tablas HTML."""
    html, n1 = anonimizar_datos_js(html_texto, contacto_map)
    # Anonimizar también patrones de nombre en tablas estáticas (index.html)
    # Buscar Contacto NN/XX como hash corto o nombre largo en <td>
    n2 = 0
    def _reemplazar(match):
        nonlocal n2
        old = match.group(1)
        nuevo = anon_contacto(old, contacto_map)
        if nuevo != old:
            n2 += 1
            return f"<td>{nuevo}</td>"
        return match.group(0)
    # Buscar <td>Nombre</td> donde Nombre es 2-40 chars alfanum + espacios, no es badge/fecha/number
    html = re.sub(
        r'<td>([A-ZÁÉÍÓÚÑÜa-záéíóúñü][A-ZÁÉÍÓÚÑÜa-záéíóúñü .]{1,38}[A-ZÁÉÍÓÚÑÜa-záéíóúñü])</td>',
        _reemplazar, html
    )
    return html, n1 + n2


# ─── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", required=True, help="HTML a anonimizar")
    parser.add_argument("--output", "-o", default=None, help="HTML de salida (default: sobre-escribe input)")
    parser.add_argument("--inplace", action="store_true", help="reemplaza en el mismo archivo")
    args = parser.parse_args()

    html = open(args.input, encoding="utf-8").read()
    contacto_map = load_contacto_map()
    antes = len(contacto_map)

    html_anon, n = anonimizar_html(html, contacto_map)

    save_contacto_map(contacto_map)
    nuevos = len(contacto_map) - antes

    out = args.input if args.inplace or args.output is None else args.output
    open(out, "w", encoding="utf-8").write(html_anon)
    print(f"Anonimizados: {n} registros · {nuevos} contactos nuevos → {out}")


if __name__ == "__main__":
    main()