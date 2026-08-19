# Modelo de Dominio Formal — SE-ITT
## Spec previa a implementación (Consigna 1: Spec Driven Development)

---

## 1. Vocabulario controlado (Enumeraciones de dominio)

| Enum | Valores | Fuente normativa/documental |
|---|---|---|
| `SCOLabel` | `No Reactivo`, `Zona Gris`, `Reactivo` | README — Regla de Negocio Estricta #1 |
| `PhysicalIntegrity` | `Normal`, `Hemolizada`, `Lipemica`, `Hemolizada_Lipemica` | PosterPaperSEITT §4.1 |
| `Marker` | `HIV`, `HBV`, `HCV`, `Sifilis`, `Chagas` | PIF — Knowledge Base |
| `Verdict` | `Apta`, `Descarte`, `Cuarentena`, `Diferimiento Temporal`, `Rechazo Tecnico` | TP2 — flujograma |
| `NATResult` | `Reactivo`, `No Reactivo`, `No Aplica` | README |

Este vocabulario es **cerrado**: `sample_input.schema.json` usa `enum` estricto (no `string` libre), de modo que ninguna extracción de MedGemma pueda inyectar una etiqueta fuera de dominio (defensa de primera línea contra alucinación léxica del LLM).

---

## 2. Función de certeza difusa en Zona Gris

**Corrección de diseño (ver §4bis, hallazgo #8):** la formalización original de esta sección asumía una función de pertenencia trapezoidal simétrica $\mu_{ZG}(x)$ con meseta central. La implementación real (`fuzzy_engine.fuzzificar_sco`) es una **rampa lineal monotónica**, no simétrica, que mide la proximidad al borde inferior de la Zona Gris:

$$
certeza(x) = \begin{cases}
\min\!\left(100,\ \dfrac{0.9-x}{0.9}\times 100\right) & x < 0.9 \quad \text{(No Reactivo)} \\[6pt]
\dfrac{1.1-x}{0.2}\times 100 & 0.9 \le x \le 1.1 \quad \text{(Zona Gris)} \\[6pt]
\min\!\left(100,\ \dfrac{x-1.1}{5.0}\times 100\right) & x > 1.1 \quad \text{(Reactivo)}
\end{cases}
$$

Dentro de Zona Gris, $certeza(0.9)=100\%$ (máxima confianza de estar cerca del límite "No Reactivo") y $certeza(1.1)=0\%$ (mínima confianza, el valor está pegado al límite "Reactivo"). Es una métrica de *proximidad direccional*, no de pertenencia difusa clásica — decisión de diseño del equipo, no un error, pero merece nombrarse con precisión: no es literalmente el trapecio $[a,b,c,d]$ que describen los papers académicos (Poster §3.2), es una simplificación lineal de un solo tramo. Se documenta así para que la memoria técnica no describa una fórmula que el código no implementa.

`certeza_sco` se calcula para **las tres etiquetas** (no solo Zona Gris), aunque hoy solo `R2_alta_certeza`/`R2_baja_certeza`/`R2_critica` la consumen como condición.

$$
sco\_label(x) = \begin{cases}
\text{No Reactivo} & x < 0.9 \\
\text{Zona Gris} & 0.9 \le x \le 1.1 \\
\text{Reactivo} & x > 1.1
\end{cases}
$$

Toda instancia de `MarkerResult` donde `sco_label` no coincida con esta función de `sco_value` es una **violación de invariante de dominio**, rechazada en la capa de tipado antes de llegar al Inference Engine.

---

## 3. Invariantes de dominio (formalizados)

### INV-01 — Monotonía de precaución en Zona Gris
$$
\forall\ m \in \text{marker\_results} : sco\_label_0(m) = \text{Zona Gris} \implies verdict(m) = \text{Descarte}
$$
independientemente de $sco\_label_1(m)$ (resultado del duplicado). El sistema **nunca** puede transicionar de sospecha a aptitud vía repetición desde Zona Gris. Regla de Oro (README).

### INV-02 — Precedencia del guard físico
$$
physical\_integrity \ne \text{Normal} \implies verdict = \text{Rechazo Tecnico}
$$
y esta regla debe evaluarse con `priority` estrictamente mayor que cualquier regla basada en S/CO (prioridad $\ge 90$). No es una regla más: es un *short-circuit* del árbitro lógico.

### INV-03 — Ambigüedad persistente en duplicados
Si tras la repetición el duplicado también cae en Zona Gris (o discorda con la lectura inicial), el descarte es preventivo y no admite una tercera repetición como mecanismo de resolución (evita bucles de re-testeo indefinido).

### INV-04 — Periodo de ventana NAT
$$
sco\_label = \text{No Reactivo} \land nat\_result = \text{Reactivo} \implies verdict = \text{Descarte}
$$
El NAT tiene precedencia sobre la serología convencional cuando discrepan, por mayor sensibilidad analítica en periodo de ventana.

### INV-05 — Algoritmo de sífilis (no monotónico simple)
$$
vdrl\_reactive \land clia\_reactive \implies verdict = \text{Diferimiento Temporal}
$$
Nota de diseño: a diferencia de otros marcadores, sífilis **no** desemboca en `Descarte` directo sino en diferimiento del donante — distinción clínica que debe preservarse en la KB (no colapsar verdicts).

### INV-06 — Riesgo epidemiológico declarado
$$
epidemiological\_risk\_flag \land (\forall m : sco\_label(m) = \text{No Reactivo}) \implies verdict = \text{Descarte}
$$
El riesgo declarado en anamnesis puede forzar descarte incluso con serología limpia (precaución sobre sensibilidad analítica).

---

## 4. Matriz de trazabilidad (Requerimiento → Regla → Invariante → Caso de prueba)

| Requerimiento clínico | Regla (`rule_id`) | Invariante | Caso de prueba (pendiente en Eval Harness) |
|---|---|---|---|
| Rechazo ante interferencia física | RN-01 | INV-02 | TC-HEMOLISIS-01 |
| Repetición ante Zona Gris inicial | RN-02 | INV-01 | TC-ZG-INICIAL-01 |
| Descarte post-duplicado sin importar resultado | RN-03 | INV-01, INV-03 | TC-ZG-DUPLICADO-{01,02} (ambos signos) |
| Descarte por ventana NAT | RN-04 | INV-04 | TC-NAT-VENTANA-01 |
| Diferimiento por algoritmo sífilis | RN-05 | INV-05 | TC-SIFILIS-ALGORITMO-01 |
| Descarte por riesgo epidemiológico | RN-06 | INV-06 | TC-RIESGO-EPI-01 |
| Aptitud por defecto | RN-07 | INV-01, INV-02, INV-06 | TC-APTA-BASELINE-01 |

> Esta matriz es el insumo directo del **Eval Harness** (frente siguiente): cada fila es, como mínimo, un caso de prueba obligatorio, con foco reforzado en los bordes exactos $S/CO \in \{0.9, 1.1\}$ de la Zona Gris.

---

## 4bis. Hallazgos de la formalización sobre el código legado

La confrontación de esta spec contra la implementación real (`knowledge_base.py`, `inference_engine.py`, `test_cases.py`) expuso divergencias entre lo documentado en los papers académicos (Poster/PIF/TP2) y el sistema efectivamente construido. Se listan porque son evidencia de valor de hacer Spec Driven Development sobre código ya escrito, no solo antes de escribirlo:

1. **Veredicto bidimensional no documentado en los papers.** El código distingue `unidad` (Apta/Descarte/Cuarentena) de `donante` (Habilitado/Diferido Temporal/Diferido Permanente). Los papers hablan de un "veredicto final" único. Se formaliza como dos ejes independientes (`UnitDisposition` × `DonorDisposition`).
2. **7 marcadores, no 5.** `HTLV I/II` y `Brucelosis` existen en `knowledge_base.py` (R12, R14) pero no se mencionan en el Poster ni el TP2.
3. **Arbitraje por peso, no por prioridad estricta.** `inference_engine.py` dispara *todas* las reglas que matchean (salvo R20) y resuelve por una jerarquía de pesos (§4ter), no por "la de mayor prioridad gana y corta". Se formaliza como **INV-07**.
4. **Acoplamiento implícito frágil en R20** (reclasificado — no es un bug activo). `fuzzy_engine.construir_hechos()` normaliza *explícitamente* `calidad_muestra` al string compuesto `"Hemolizada o Lipémica"` antes de que `knowledge_base.py` lo compare — hoy funciona, porque las dos puntas están sincronizadas a mano. El riesgo es de mantenibilidad: si se agrega un tercer valor de interferencia (ej. "Coagulada") hay que recordar tocar ambos archivos, y nada lo fuerza. Se reemplaza por un enum cerrado + operador `IN`, eliminando la necesidad de sincronizar dos módulos a mano.
5. **Duplicación de clave, no inconsistencia** (reclasificado). `fuzzy_engine.construir_hechos()` sí setea tanto `repeticion` como `sco_repeticion` con el mismo valor — R3 no está roto. El code smell es la redundancia (dos nombres para un mismo concepto, mantenidos sincronizados manualmente). Se unifica a `sco_repeticion` en la spec.
6. **`riesgo` como string, no booleano.** El código usa `"Sí"`/`"No"`; se migra a `bool` (tipado estricto, Consigna 2).
7. **NAT aplicable solo a HIV/HBV/HCV** (README, regla estricta #5) no estaba formalizado como invariante ejecutable — ahora es **INV-08**, verificado tanto en `MarkerResult` (contrato externo) como en `WorkingMemoryFacts` (contrato interno).
8. **Condiciones de R2_\* embebidas como `lambda` de Python en `knowledge_base.py`.** Rompe la promesa de "repositorio declarativo" que hacen los papers (§3.1): un `lambda` no es serializable, no es auditable por fuera de Python, y no puede versionarse como dato. El DSL de `rule.schema.json` ya lo resuelve con operadores `GTE`/`LT` explícitos sobre `certeza_sco` (ver R2_alta_certeza/baja/critica en `kb_rules.json`).
9. **`certeza_sco` no es exclusiva de Zona Gris** (corrección de alcance, ver §2). Se calcula para las tres etiquetas; el modelo anterior de esta spec la restringía incorrectamente.

## 4ter. INV-07 — Arbitraje por peso de decisión (formalización del motor real)

El Inference Engine no se detiene en la primera regla que matchea (salvo R20, único corto-circuito). Evalúa **todas** las reglas en orden de `priority` descendente, acumula las terminales que disparan, y se queda con la de mayor peso:

$$
w(\text{unidad}, \text{donante}) = \begin{cases}
4 & \text{unidad} = \text{Cuarentena} \\
3 & \text{unidad} = \text{Descarte} \land \text{donante} = \text{Diferido\_Permanente} \\
2 & \text{unidad} = \text{Descarte} \land \text{donante} = \text{Diferido\_Temporal} \\
1 & \text{unidad} = \text{Descarte} \land \text{donante} = \text{null} \\
0 & \text{unidad} = \text{Apta}
\end{cases}
$$

El veredicto final es $\arg\max_w$ entre las reglas terminales disparadas; en empate de peso, gana la de mayor `priority` (evaluada primero, no reemplazada por una posterior de igual peso — ver `_peso_decision` en `inference_engine.py`, comparación estrictamente `>`).

## 4quater. INV-15 — Forma dual del veredicto (terminal vs. pendiente)

Un `InferenceVerdict` tiene exactamente una de dos formas — nunca ambas, nunca ninguna:

(i) **Terminal** — `final_unit_disposition` presente, `pending_action` ausente. El ciclo de forward chaining alcanzó una regla terminal; el veredicto es candidato al arbitraje por peso de decisión (INV-07).

(ii) **Pendiente** — `final_unit_disposition` ausente, `pending_action` presente. El ciclo solo disparó reglas intermedias (`rule_type=intermediate`, ej. `R2_*`, `R8`) sin alcanzar ninguna terminal. Un veredicto pendiente **no participa** del arbitraje de INV-07: no es candidato, es una interrupción del ciclo que exige una acción clínica (repetición por duplicado, algoritmo confirmatorio) antes de poder emitir un veredicto terminal — confirmado contra `RuleEngine.evaluar()`: `decision_weight()` solo se invoca dentro de la rama `rule_type == "terminal"`.

$$
(final\_unit\_disposition \ne \bot) \;\oplus\; (pending\_action \ne \bot)
$$

Ambos presentes, o ambos ausentes, es una violación de invariante.

**Retrofit de código a spec:** esta es la forma que ya imponía `check_pending_action_consistency()` en `seitt_core/domain.py.InferenceVerdict` desde antes de esta spec — no es un invariante nuevo, es la formalización de un validador que el código real ya ejecutaba, ahora promovido junto con el resto del modelo a `spec/contracts.py` como fuente única (`seitt_core/domain.py` reexporta, no redefine).

---

## 5. Frontera de responsabilidad MedGemma ↔ Núcleo Simbólico

```
MedGemma (módulo neuronal)          Núcleo Simbólico (SE-ITT)
────────────────────────           ──────────────────────────
Reporte no estructurado    ──▶      valida contra
(texto libre, PDF, HL7)             sample_input.schema.json
        │                                    │
        ▼                                    ▼
  JSON candidato              rechaza si no valida
  (source=medgemma_extraction,      (DomainInvariantViolation /
   extraction_confidence)            SchemaValidationError)
```

MedGemma **no tiene** — por diseño de contrato, no por convención — ninguna vía de escritura hacia `Verdict`. Solo puede: (a) producir instancias de `SampleInputFacts`, y (b) consumir instancias de `InferenceVerdict` para redactar el reporte en lenguaje natural post-analítico. El schema es la frontera física de la arquitectura no-wrapper.
