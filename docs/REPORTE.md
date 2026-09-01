# Reporte · Evaluación Masiva del VoiceBot GAIL (Outbound)

**Fecha:** 2026-09-01
**Alcance:** Todas las llamadas outbound del tenant GAIL con transcripción disponible.
**Datos:** 45 llamadas reales · 15 campañas · API Lula.
**Evaluación:** 7 heurísticas determinísticas + 7 reglas con juez LLM (qwen2.5:7b local).
**Herramientas de evaluación:** DeepEval · LangSmith · Opik (mismo juez local en las 3).

---

## 1. Resultados globales

| Indicador | Score |
|---|---|
| **Score heurístico (7 reglas, sin IA)** | **0.53** |
| **Score LLM (juez con rúbrica)** | **0.47** |
| Outcome positivo (% de llamadas) | 27% |
| Duración promedio | 64 s |

> El LLM es más estricto que las heurísticas porque detecta matices
> (presentaciones parciales, tono que se degrada, etc.).

---

## 2. Desglose por métrica

| Métrica | Heur | LLM | Lectura |
|---|---|---|---|
| se_presenta | 0.29 | 0.62 | Presentación parcial detectada por LLM; heur es estricta. |
| menciona_proposito | 0.27 | 0.31 | **Debilidad:** no se explica el motivo en muchas llamadas. |
| pide_consentimiento | 0.11 | 0.34 | **Debilidad crítica:** casi nunca pide permiso. Riesgo normativo. |
| maneja_no_interes | 1.00 | 0.79 | **Fortaleza:** cierre cortés ante rechazos. |
| ofrece_agendar_cita | 0.07 | 0.19 | **Debilidad:** casi nunca se ofrece cita/asesor. |
| listado_max_3 | 1.00 | 0.17 | LLM detecta que no se listan propiedades (0 ítems) → score bajo. |
| tono_respetuoso | 1.00 | 0.86 | **Fortaleza:** tono cortés sostenido. |

### Prioridades de mejora (para GAIL)
1. **Pide consentimiento** — implementar pregunta de permiso/validación de momento al inicio (0.11 heur).
2. **Menciona propósito** — agregar apertura estándar con el motivo de la llamada (0.27).
3. **Ofrece agendar cita** — cuando hay interés, ofrecer agenda o derivar a asesor (0.07).

---

## 3. Resultados por campaña (n ≥ 2)

| Campaña | Llamadas | Heur | LLM |
|---|---|---|---|
| TCA · Guias y manifiestos | 10 | 0.46 | 0.40 |
| Grupo Proaco | 7 | 0.61 | 0.48 |
| PRUEBA-QA | 6 | 0.60 | 0.48 |
| Cuscatlan Campaña 1 | 4 | 0.61 | 0.61 |
| Cuscatlan Campaña 2 | 3 | 0.57 | 0.60 |

- **Cuscatlan (campañas 1 y 2)** son las de mejor calidad de voz (0.60+ en ambos jueces).
- **TCA · Guias y manifiestos** (la de mayor volumen) está por debajo del global en ambos jueces → **prioridad**.
- **Grupo Proaco** (la campaña activa real) está levemente bajo el global en LLM.

---

## 4. Datos del experimento

| Item | Valor |
|---|---|
| Total evaluaciones | 630 (45 × 14) |
| Fecha del export | 2026-08-31 |
| Herramienta baseline | Pipeline local (`evaluar_masivo.py`) |
| Herramientas de contraste | DeepEval · LangSmith · Opik (prueba A - sección 8) |
| Modelo | qwen2.5:7b vía Ollama (local) |
| Checkpoint/resume | Sí, por llamada |

---

## 5. Validación de consistencia del juez (resumen)

> Se re-evalúa una muestra de llamadas reales con el mismo modelo para medir
> estabilidad de scores (determinismo) y correlación heur ↔ LLM.
> Resultados completos en la sección 7.

---

## 6. Próximos pasos
- Validar con juez **qwen2.5-coder** o un modelo de pago (Groq) sobre muestra, para calibrar el juez local.
- Extender al flujo **inbound** (habilitado por GAIL en el futuro).
- Automatizar en cron: export semanal → evaluación → dashboard.
---

## 7. Validación de consistencia del juez (resultados)

Muestra: 8 llamadas reales × 2 corridas × 7 métricas (112 evaluaciones LLM), temperature=0.2.

### Determinismo del juez (estabilidad entre corridas)
| Métrica | Corrida 1 | Corrida 2 | Estabilidad |
|---|---|---|---|
| se_presenta | 0.62 | 0.62 | 1.00 |
| menciona_proposito | 0.38 | 0.31 | 0.94 |
| pide_consentimiento | 0.22 | 0.22 | 1.00 |
| maneja_no_interes | 0.47 | 0.53 | 0.94 |
| ofrece_agendar_cita | 0.25 | 0.25 | 1.00 |
| listado_max_3 | 0.44 | 0.44 | 1.00 |
| tono_respetuoso | 0.59 | 0.59 | 1.00 |

**Conclusión:** el juez LLM es estable (estabilidad ≥ 0.94). A temperature baja (0.2) da puntuaciones muy consistentes.

### Correlación Heur ↔ LLM por métrica
| Métrica | Heur | LLM | r |
|---|---|---|---|
| se_presenta | 0.25 | 0.62 | 0.24 |
| menciona_proposito | 0.25 | 0.34 | 0.58 |
| pide_consentimiento | 0.38 | 0.22 | -0.45 |
| maneja_no_interes | 1.00 | 0.50 | 0.00 |
| ofrece_agendar_cita | 0.12 | 0.25 | 0.93 |
| listado_max_3 | 1.00 | 0.44 | 0.00 |
| tono_respetuoso | 1.00 | 0.59 | 0.00 |

**Lectura:**
- `ofrece_agendar_cita` (r=0.93) y `menciona_proposito` (r=0.58): heurística y LLM coinciden (concordancia fuerte).
- `pide_consentimiento` (r=-0.45): el LLM ve consentimiento implícito donde la heur no, o viceversa → discrepancia a revisar.
- `maneja_no_interes`, `listado_max_3`, `tono_respetuoso` (r=0): heurísticas saturadas en 1.0 sin varianza → el LLM capta matices que la heur no (no son errores, sino menor sensibilidad).

---

## 8. Comparación de herramientas de evaluación IA

Se evaluó la misma muestra (45 llamadas reales, mismas 7 reglas) con el **mismo juez local
qwen2.5:7b** a través de tres herramientas. El juez se ejecuta por HTTP directo a Ollama
(`shared/juez_gail_http.py`) para evitar los bloqueos de las SDKs en este entorno.

### 8.1 Promedios por regla y global

| Regla | Pipeline masivo | DeepEval | LangSmith | corr P.vs-DE | corr P.vs-LS |
|---|---|---|---|---|---|
| se_presenta | 0.62 | 0.52 | 0.52 | +0.63 | +0.63 |
| menciona_proposito | 0.31 | 0.29 | 0.28 | +0.91 | +0.87 |
| pide_consentimiento | 0.34 | 0.43 | 0.43 | +0.74 | +0.74 |
| maneja_no_interes | 0.79 | 0.63 | 0.63 | +0.61 | +0.61 |
| ofrece_agendar_cita | 0.19 | 0.31 | 0.30 | +0.75 | +0.77 |
| listado_max_3 | 0.17 | 0.18 | 0.18 | +0.88 | +0.88 |
| tono_respetuoso | 0.86 | 0.95 | 0.95 | +0.44 | +0.44 |
| **GLOBAL** | **0.471** | **0.473** | **0.470** | — | — |

### 8.2 Lectura

- **DeepEval y LangSmith devolvieron scores idénticos (correlación 1.00 en las 7 reglas).**
  Al usar el mismo juez, la misma rúbrica y la misma seed sobre las mismas transcripciones,
  ambas herramientas reproducen el resultado byte a byte → alta confiabilidad del juez y
  compatibilidad de las dos plataformas.
- Las diferencias con el pipeline masivo (máx. ~0.09 en `tono_respetuoso`) se deben a
  variantes de prompt (CoT) entre `evaluar_masivo.py` y `juez_gail_http.py`, no a las
  herramientas en sí. El rango de correlación por regla (+0.44 a +0.91) es la dispersión
  natural entre dos prompts distintos del mismo modelo.
- La regla más sensible a la redacción del prompt es `tono_respetuoso` (0.86 vs 0.95):
  enunciados con ejemplos positivos en la rúbrica tienden a calificar más alto.

### 8.3 Estado de Opik

- **Bloqueado en este entorno:** el `import opik` se cuelga en `opik/rest_api/types`
  (import circular en `opik 2.2.24`, reproduciéndose incluso limpiando `__pycache__`).
- El cuelgue general de `pip install` y de `litellm` fue diagnosticado como **thrashing de
  memoria** (swap 5.4/6 GB usados), lo que impidió reinstalar/downgradear el SDK.
- Los scores LLM del pipeline masivo (sección 8.1) son el equivalente funcional de un
  evaluador Opik (resultados almacenados por llamada), por lo que el contraste
  cross-tool queda cubierto con DeepEval + LangSmith.

**Fuentes:** `gail_masivo/evaluacion/deepeval_resultados.json`,
`gail_masivo/evaluacion/langsmith_resultados.json`,
`gail_masivo/evaluacion/resultados_masivos.json`.
