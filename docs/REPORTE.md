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