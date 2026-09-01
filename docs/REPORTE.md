# Reporte · Evaluación Masiva del VoiceBot GAIL (Outbound)

**Fecha:** 2026-09-01
**Alcance:** Todas las llamadas outbound del tenant GAIL con transcripción disponible.
**Datos:** 45 llamadas reales · 15 campañas · API Lula.
**Evaluación:** 7 heurísticas determinísticas + 7 reglas con juez LLM (qwen2.5:7b local).

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
| Herramienta | Pipeline local (`evaluar_masivo.py`) |
| Modelo | qwen2.5:7b vía Ollama (hidp local) |
| Checkpoint/resume | Sí, por llamada |

---

## 5. Validación de consistencia del juez (prueba adicional)

> Se re-evalúa una muestra de llamadas reales con el mismo modelo para medir
> estabilidad de scores (determinismo) y correlación heur ↔ LLM.

**Resultado:** (completar tras la corrida de `validar_consistencia.py`)

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
