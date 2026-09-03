# GAIL · Evaluación Masiva del VoiceBot (Outbound) con Llamadas Reales

Dashboard de evaluación automática de calidad de llamadas **outbound** del tenant **GAIL**,
construido sobre transcripciones reales descargadas de la **API de Lula**.

**Dashboard publicado:** https://david899b.github.io/gail-evaluacion/

---

## 📋 Resumen del análisis

| Métrica | Valor |
|---|---|
| Llamadas reales evaluadas | **45** |
| Campañas outbound | **15** |
| Reglas heurísticas (sin IA) | 7 |
| Reglas con juez LLM (rúbrica) | 7 |
| Modelo juez | qwen2.5:7b (local, Ollama) |
| Score heurístico global | **0.53** |
| Score LLM global | **0.47** |
| **Juez de referencia (Gemini)** | **0.52** |

### Fortalezas detectadas
- **Tono respetuoso** (heur 1.0 / LLM 0.86 / Gemini 1.0) y **manejo del no-interés** (heur 1.0 / LLM 0.79 / Gemini 0.96): el bot mantiene cortesía y cierra bien ante rechazos.
- `listado_max_3` alto en heurística (1.0) = no sobrecarga con listados.

### Debilidades detectadas
- **Pide consentimiento** (heur 0.11 / LLM 0.34 / **Gemini 0.02**): raramente pregunta si es buen momento antes de hablar del tema. ⚠️ Riesgo de incumplimiento normativo.
- **Menciona el propósito** (heur 0.27 / LLM 0.31 / **Gemini 0.20**): muchas llamadas no explican por qué llaman.
- **Ofrece agendar cita** (heur 0.07 / LLM 0.19 / **Gemini 0.09**): casi nunca deriva a cita/asesor en llamadas de interés.
- **Se presenta** (heur 0.29 vs LLM 0.62 / **Gemini 0.47**): la heurística es estricta; el LLM detecta presentación parcial.

---

## 🏗️ Pipeline

```
Lula API  →  exportar_gail.py  →  llamadas_gail.json  →  evaluar_masivo.py  →  resultados_masivos.json  →  generar_dashboard.py  →  index.html
```

| Paso | Script | Salida |
|---|---|---|
| Descargar campañas + transcripciones | `exportar_gail.py` | `data/llamadas_gail.json` |
| Evaluar (heurísticas + juez LLM) | `evaluar_masivo.py` | `evaluacion/resultados_masivos.json` |
| Generar dashboard | `generar_dashboard.py` | `index.html` |

### 1. Exportar datos desde Lula
```bash
export LULA_API_KEY="api-..."
.venv/bin/python gail_masivo/exportar_gail.py
```
Descarga todas las campañas y los touchpoints outbound con transcripción, con
paginación por cursor y reintentos con backoff ante rate-limit.

### 2. Evaluar las llamadas
```bash
.venv/bin/python gail_masivo/evaluar_masivo.py --juez ollama/qwen2.5:7b
```
Para cada llamada evalúa **7 heurísticas** (reglas determinísticas, sin IA) y
**7 reglas con juez LLM** (rúbrica de 5 anclas + chain-of-thought). Tiene
checkpoint/resume por llamada, así que puede interrumpirse y retomar.

> Opcional: agregar capa GEval con `--geval`.

### 3. Generar el dashboard
```bash
.venv/bin/python gail_masivo/generar_dashboard.py --salida index.html
```
Produce un HTML autocontenido (estilo Proaco: tabs, cards, charts, badges y
escala de colores verde/amarillo/rojo) con detalle por campaña y por llamada.

---

## 📊 Métricas evaluadas (outbound)

| Métrica | Descripción |
|---|---|
| `se_presenta` | Se identifica como la marca al inicio de la llamada |
| `menciona_proposito` | Explica por qué llama |
| `pide_consentimiento` | Pregunta si es buen momento / da permiso para continuar |
| `maneja_no_interes` | Ante "no me interesa" cierra cortés sin insistir |
| `ofrece_agendar_cita` | Ofrece cita/visita o derivar a asesor si hay interés |
| `listado_max_3` | Lista máximo 3 propiedades por mensaje |
| `tono_respetuoso` | Tono cortés durante toda la llamada |

### Escala de colores
- 🟢 `0.75–1.00` Cumple
- 🟡 `0.50–0.74` Parcial
- 🔴 `0.00–0.49` No cumple

---

## 🗂️ Estructura del repo

```
gail-evaluacion/
├── index.html                    # Dashboard principal (GitHub Pages)
├── dashboard-evaluacion-gail.html  # Dashboard de jueces (cross-tool)
├── gail_masivo/
│   ├── exportar_gail.py          # Export Lula API
│   ├── evaluar_masivo.py         # Evaluación (heur + LLM)
│   ├── generar_dashboard.py      # Generador del dashboard
│   ├── reintentar_export.py      # Reintento en background
│   ├── validar_consistencia.py   # Validación de consistencia del juez
│   ├── data/llamadas_gail.json   # Datos fuente (45 llamadas reales)
│   ├── evaluacion/
│   │   ├── resultados_masivos.json    # Heurísticas + LLM qwen7b
│   │   └── gemini_resultados.json     # Juez de referencia Gemini
│   ├── herramientas/
│   │   └── evaluar_gemini_urllib.py   # Evaluador Gemini (sin dependencias)
│   └── reportes/
├── shared/
│   └── juez_gail_http.py         # Juez LLM compartido (HTTP directo)
└── docs/                         # Documentación adicional
```

---

## 🔐 Seguridad
- La **API key de Lula** se pasa por variable de entorno (`LULA_API_KEY`), nunca hardcodeada.
- El repositorio contiene **datos reales de llamadas** (transcripciones). Se suben
  con fines de evaluación interna; avisar antes de hacer el repo público en caso
  de datos sensibles de clientes.

---

## 📅 Historial
- **2026-08-31**: Desbloqueo de la API (key nueva) → export de 45 llamadas reales → evaluación completa.
- **2026-09-01**: Dashboard estilo Proaco + despliegue a GitHub Pages.
- **2026-09-03**: Juez de referencia Gemini (gemini-flash-lite-latest, Google) → dashboard de jueces cross-tool con 6 jueces comparados.
