# Modelo de Dominio Formal — SE-ITT
## Spec previa a implementación (Consigna 1: Spec Driven Development)

---

## 1. Vocabulario controlado (Enumeraciones de dominio)

Fuente única de verdad: `spec/contracts.py` (`seitt_core/domain.py` la reexporta, no la redefine — verificado por identidad de objeto en `validate_spec.py`, bloque [7]).

| Enum | Valores | Fuente normativa/documental |
|---|---|---|
| `SCOLabel` | `No Reactivo`, `Zona Gris`, `Reactivo` | README — Regla de Negocio Estricta #1 |
| `PhysicalIntegrity` | `Normal`, `Hemolizada`, `Lipemica` | PosterPaperSEITT §4.1 |
| `Marker` | `HIV`, `HBV`, `HCV`, `Sifilis`, `Chagas`, `HTLV_I_II`, `Brucelosis` | PIF — Knowledge Base + `knowledge_base.py` (R12, R14) |
| `UnitDisposition` | `Apta`, `Descarte`, `Cuarentena` | Eje 1 del veredicto bidimensional (INV-07) |
| `DonorDisposition` | `Habilitado`, `Diferido_Temporal`, `Diferido_Permanente` | Eje 2 del veredicto bidimensional (INV-07) |
| `AssayResult` | `Reactivo`, `No Reactivo`, `No Aplica`, `Pendiente` | README + consulta a bioquímica de referencia (INV-08) |
| `InputSource` | `analyzer_direct`, `medgemma_extraction` | Frontera no-wrapper (Consigna 5), ver §5 |

**Correcciones respecto de la versión previa de esta tabla** (todas verificadas contra el código real, no contra los papers):

- **`PhysicalIntegrity`**: se elimina `Hemolizada_Lipemica`. Hemólisis y lipemia son clínicamente equivalentes a efectos de R20 (ambas pertenecen a `INTERFERENCE_VALUES` y disparan el mismo corto-circuito por INV-02); un valor compuesto reintroduce el acoplamiento por *magic string* que §4bis hallazgo 4 documenta como corregido.
- **`Marker`**: son **7**, no 5. `HTLV_I_II` y `Brucelosis` existen en la KB desde el legado (R12, R14) pero no figuraban en el Poster ni en el TP2 (§4bis hallazgo 2).
- **`Verdict` no existe como enum único.** La tabla anterior lo describía con valores (`Diferimiento Temporal`, `Rechazo Tecnico`) que el código nunca implementó. El veredicto es **bidimensional**: `UnitDisposition` × `DonorDisposition`, ejes independientes (§4bis hallazgo 1, INV-07). Lo que el flujograma del TP2 llamaba "Rechazo Tecnico" es hoy `UnitDisposition.CUARENTENA` con donante sin resolver; "Diferimiento Temporal" es `DonorDisposition.DIFERIDO_TEMPORAL`, un valor del **otro** eje.
- **`AssayResult`** (antes `NATResult`): se agrega `Pendiente` (Fase 3, Paso 2) — ensayo solicitado con informe no llegado, ver INV-08 y R21 — y se renombra (Fase 3, Paso 2.5). El nombre viejo conflacionaba dos conceptos: `vdrl` y `clia` estaban tipados `NATResult` pese a que **VDRL es una prueba serológica no treponémica y CLIA un inmunoensayo treponémico — ninguno es un ensayo de ácidos nucleicos**. Es el vocabulario ÚNICO de resultado de cualquier ensayo; qué valores son legales para cada campo lo decide el invariante correspondiente (INV-08 para `nat`, INV-05 para `vdrl`/`clia`), no un tipo separado por ensayo.

Este vocabulario es **cerrado**: `sample_input.schema.json` usa `enum` estricto (no `string` libre), de modo que ninguna extracción de MedGemma pueda inyectar una etiqueta fuera de dominio (defensa de primera línea contra alucinación léxica del LLM). La igualdad de conjuntos entre cada enum Pydantic y su `enum` JSON Schema equivalente se verifica en `validate_spec.py`, bloque [6a] — no se confía en la sincronización manual.

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

`certeza_sco` se calcula para **las tres etiquetas** (no solo Zona Gris), aunque hoy solo `R2_alta_certeza`/`R2_baja_certeza`/`R2_critica` la consumen como condición. Se calcula, eso sí, **solo si hubo una lectura real**: sin `sco_inicial_valor` no hay certeza que derivar, y fuzzificar un centinela produciría un número sin referente clínico — ver **INV-16**.

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

**Conformidad de R4 con este invariante (corregida).** El antecedente de R4 era el desnudo `nat = Reactivo`, sin la conjunción `sco\_label = 	ext{No Reactivo}` que este invariante sí exige: la implementación era **más laxa que su propia especificación**. El efecto no era sobre el veredicto sino sobre `epidemiological_status` — R4 gana el arbitraje por prioridad a igual peso, así que etiquetaba `Periodo_Ventana` también los casos de serología reactiva (EV18), donde no hay ventana sino infección establecida. Se acotó el antecedente a lo que INV-04 ya decía. No es un cambio de criterio clínico: es cerrar la brecha entre la spec y la KB.

**Alcance operativo de la precondición de repetición en R13.** R13 (`Zona Gris ∧ NAT reactivo`) exige además `sco\_repeticion = 	ext{No Reactivo}`. La precondición es **operativa, no clínica**, y depende del circuito del banco: las muestras de NAT se derivan a un laboratorio externo y el informe llega al día siguiente, de modo que para cuando el resultado de NAT está disponible la repetición por duplicado ya se cursó. Un antecedente que no la exigiera describiría un flujo que en este banco no ocurre. **Confirmado por la bioquímica de referencia** — no es inferencia de quien escribe la KB. Bajo un modelo con NAT propio corriendo en paralelo a la serología, esta precondición no aplicaría y R13 volvería a su forma de dos condiciones; queda dicho acá para que un cambio de circuito no obligue a reconstruir el razonamiento desde cero.

Consecuencia registrada: una Zona Gris con NAT reactivo y **sin** repetición cursada ya no alcanza R13 y termina en veredicto pendiente por `R2_*` (se pide repetición o nueva muestra). No hay relajación de seguridad: pendiente no es `Apta` y la unidad no se libera. Lo que cambia no es el nivel de precaución, sino que se exige completar el paso del protocolo que el circuito real ya garantiza.

### INV-05 — Algoritmo de sífilis (no monotónico simple)
$$
vdrl\_reactive \land clia\_reactive \implies verdict = \text{Diferimiento Temporal}
$$
Nota de diseño: a diferencia de otros marcadores, sífilis **no** desemboca en `Descarte` directo sino en diferimiento del donante — distinción clínica que debe preservarse en la KB (no colapsar verdicts).

**Aplicabilidad de VDRL/CLIA (Fase 3, Paso 2.5).** Simétrica a INV-08, y por la misma razón:

$$
m \ne \text{Sifilis} \implies vdrl(m) = clia(m) = \text{No Aplica}
$$

$$
m = \text{Sifilis} \implies vdrl(m),\ clia(m) \in \{\text{Reactivo}, \text{No Reactivo}, \text{Pendiente}\}
$$

**Matriz completa VDRL×CLIA (Fase 3, corrección de veredicto).** Confirmada con el bioquímico de referencia: un reactivo en cualquiera de las dos técnicas, o discordancia entre ambas, es `Descarte`/`Diferido_Temporal` inmediato — no hay estado clínico de "solo esperar". De las 9 celdas, las 8 con al menos un resultado informado quedan resueltas por R8/R9/R10/R22 sin necesitar saber qué técnica se hizo primero: el veredicto depende únicamente del par de valores. La única celda sin resolver es `vdrl=Pendiente AND clia=Pendiente` (R23, bloqueo sin veredicto).

*Nota de fragilidad:* P/P es el único caso de Sífilis sin resultado informado en ninguna técnica; el bloqueo depende de que exista una regla intermedia que dispare para ese antecedente exacto — si se elimina, R1 vuelve a liberar la unidad sin lectura. R1 no distingue Sífilis de ningún otro marcador (su antecedente nunca miró `vdrl`/`clia`), así que la protección contra ese caso vive enteramente en R23, no en R1: es la misma clase de dependencia implícita ya documentada para R20/INV-16 (Hallazgos conocidos, CLAUDE.md), y merece la misma cautela ante refactors futuros del motor de reglas.

Antes de este paso `vdrl`/`clia` eran `AssayResult | None`, y ese `None` significaba **dos cosas a la vez**: *"este marcador no tiene ese ensayo"* y *"el ensayo corresponde pero no se informó todavía"* — exactamente la conflación que el Paso 2 corrigió para `nat`. Ahora se derivan del marcador igual que `nat`: `No Aplica` fuera de Sífilis, `Pendiente` en Sífilis sin informe. Como efecto colateral se corrigió un **descarte silencioso**: `construir_hechos()` hacía `AssayResult(vdrl) if (marker == SIFILIS and vdrl is not None) else None`, de modo que un `vdrl` provisto para un marcador no-Sífilis desaparecía sin error; hoy se rechaza con `DomainInvariantViolation`.

### INV-06 — Riesgo epidemiológico declarado
$$
epidemiological\_risk\_flag \land (\forall m : sco\_label(m) = \text{No Reactivo}) \implies verdict = \text{Descarte}
$$
El riesgo declarado en anamnesis puede forzar descarte incluso con serología limpia (precaución sobre sensibilidad analítica).

### INV-08 — Aplicabilidad del ensayo NAT (bidireccional)

El ensayo NAT es clínicamente aplicable **solo** a HIV, HBV y HCV (README — Regla de Negocio Estricta #5). El invariante tiene dos direcciones, ambas obligatorias:

$$
m \notin \{\text{HIV}, \text{HBV}, \text{HCV}\} \implies nat(m) = \text{No Aplica}
$$

$$
m \in \{\text{HIV}, \text{HBV}, \text{HCV}\} \implies nat(m) \in \{\text{Reactivo}, \text{No Reactivo}, \text{Pendiente}\}
$$

Para un marcador no-NAT, tanto `Reactivo`/`No Reactivo` como `Pendiente` son violaciones: el ensayo no corresponde, y el único valor honesto es `No Aplica`. Para un marcador NAT-aplicable, `No Aplica` es **igual de inválido** que un resultado inventado: el ensayo sí corresponde, y su estado debe ser uno de los tres reales.

**Segunda dirección — endurecimiento (Fase 3, Paso 2).** La formulación original solo verificaba la primera dirección. `Pendiente` (valor nuevo de `AssayResult`, entonces todavía llamado `NATResult`) es lo que hace necesaria y verificable a la segunda: sin él, un marcador NAT-aplicable cuyo informe todavía no llegó no tenía ninguna representación honesta — `No Reactivo` afirma un resultado que nadie leyó, y `No Aplica` contradice la primera dirección. El defecto concreto que esto corrige: `fuzzy_engine.construir_hechos()` tenía `No Aplica` como default silencioso, lo que volvía indistinguible *"el ensayo no corresponde"* de *"el ensayo corresponde pero no fue informado"* — y permitía liberar una unidad (R1 → Apta) sin que nadie hubiera leído el NAT. Consulta a la bioquímica de referencia: con NAT no informado la unidad **no se libera**; el flujo real espera el informe (ver R21).

Verificado en ambas direcciones y en las dos capas: `MarkerResult` (contrato externo) y `WorkingMemoryFacts` (contrato interno), más los `allOf` condicionales equivalentes en `sample_input.schema.json` y `working_memory_facts.schema.json`.

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
10. **Ningún marcador no-NAT podía alcanzar `Apta`** (defecto latente, detectado en Fase 3 Paso 2). R1 es la única regla que produce `Apta` y su antecedente exigía `nat = No Reactivo`. Como Chagas, Sífilis, HTLV I/II y Brucelosis tienen `nat = No Aplica` por INV-08, R1 no podía disparar jamás para ellos: un Chagas no reactivo sin riesgo no disparaba **ninguna** regla y el ciclo terminaba con `triggered_rules` vacío, que `InferenceVerdict` rechaza (`ValidationError`). Ningún caso del Eval Harness lo cubría — todos los casos no-NAT del dataset esperaban `Descarte` o veredicto pendiente. Se corrige con pertenencia positiva `IN ["No Reactivo", "No Aplica"]`, que además excluye explícitamente `Pendiente`. Ese antecedente demasiado estricto era, sin embargo, *load-bearing por accidente*: ver la cláusula de acción pendiente en §4ter.

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

**Cláusula de acción pendiente (Fase 3, Paso 2).** Una regla intermedia disparada invalida un candidato terminal `Apta`, y solo `Apta`:

$$
\exists\,r \in \text{fired} : rule\_type(r) = \text{intermediate} \;\land\; \arg\max_w = \text{Apta} \implies \text{veredicto pendiente (INV-15, forma ii)}
$$

Un pendiente impide la **liberación**, nunca el **descarte**: un hallazgo serológico positivo no necesita que se completen los pasos pendientes para justificar el descarte, de modo que un candidato `Descarte`/`Cuarentena` no se toca. Con una acción pendiente sin completar (repetición por duplicado, CLIA confirmatorio, informe NAT), liberar la unidad equivaldría a afirmar un resultado que nadie leyó.

Antes de esta cláusula la propiedad se sostenía **por coincidencia, no por diseño**: `R2_*` no colisionaba con R1 porque exigen `sco` mutuamente excluyente (`Zona Gris` vs `No Reactivo`), y `R8` quedaba excluido únicamente porque R1 exigía `nat = No Reactivo` y Sífilis tiene `nat = No Aplica`. Al cerrar el antecedente de R1 con `IN ["No Reactivo", "No Aplica"]` — necesario para que Chagas, HTLV I/II, Sífilis y Brucelosis puedan alcanzar `Apta`, ver §4bis hallazgo 10 — esa protección accidental desapareció y un caso de VDRL reactivo con CLIA pendiente pasaba a liberarse como `Apta`. La cláusula lo convierte en una propiedad del árbitro, válida también para toda regla intermedia que se agregue en el futuro sin tener que recordar sincronizar el antecedente de R1.

## 4quater. INV-15 — Forma dual del veredicto (terminal vs. pendiente)

Un `InferenceVerdict` tiene exactamente una de dos formas — nunca ambas, nunca ninguna:

(i) **Terminal** — `final_unit_disposition` presente, `pending_action` ausente. El ciclo de forward chaining alcanzó una regla terminal; el veredicto es candidato al arbitraje por peso de decisión (INV-07).

(ii) **Pendiente** — `final_unit_disposition` ausente, `pending_action` presente. El ciclo solo disparó reglas intermedias (`rule_type=intermediate`, ej. `R2_*`, `R8`) sin alcanzar ninguna terminal. Un veredicto pendiente **no participa** del arbitraje de INV-07: no es candidato, es una interrupción del ciclo que exige una acción clínica (repetición por duplicado, algoritmo confirmatorio) antes de poder emitir un veredicto terminal — confirmado contra `RuleEngine.evaluar()`: `decision_weight()` solo se invoca dentro de la rama `rule_type == "terminal"`.

$$
(final\_unit\_disposition \ne \bot) \;\oplus\; (pending\_action \ne \bot)
$$

Ambos presentes, o ambos ausentes, es una violación de invariante.

**Retrofit de código a spec:** esta es la forma que ya imponía `check_pending_action_consistency()` en `seitt_core/domain.py.InferenceVerdict` desde antes de esta spec — no es un invariante nuevo, es la formalización de un validador que el código real ya ejecutaba, ahora promovido junto con el resto del modelo a `spec/contracts.py` como fuente única (`seitt_core/domain.py` reexporta, no redefine).

### INV-16 — Ausencia de certeza sin lectura

**Enunciado.** `certeza_sco` (y su proyección externa `certainty_index`) está definida **si y solo si** existe un `sco_inicial_valor` real medido:

$$
sco\_inicial\_valor = ot \implies certeza\_sco = ot
$$

Toda etiqueta `sco` derivada de un centinela sintético — interferencia física (INV-02) o marcador cuya inferencia no depende de S/CO (INV-05) — se acompaña de `certeza_sco = None`, nunca de un grado de pertenencia calculado sobre el centinela.

**Fundamento.** Fuzzificar un centinela produce un número con forma de dato clínico y sin referente. El rechazo técnico por hemólisis llegaba con `certainty_index = 1.0` — la certeza más alta que el sistema puede emitir — en el único camino donde nadie leyó un S/CO. Un valor así no es un dato pobre: es un dato **inventado**, y en un CDSS se lee como confianza máxima justo donde no hubo medición.

**Enforcement.** `construir_hechos()` deja `certeza_sco = None` cuando `sco_inicial_valor is None`, y `expert_system.evaluar_caso()` no sintetiza valor ante interferencia (pasa `None`, no `0.0`). El contrato ya lo admite: `InferenceVerdict.certainty_index` es `float | None`, y `verdict.schema.json` no lo incluye entre los `required`. El Eval Harness lo verifica sobre los casos de `interferencia_fisica`.

**Nota de alcance.** El invariante gobierna la CERTEZA, no la etiqueta. La etiqueta `sco` sigue siendo el centinela `No Reactivo` en ambos caminos, y eso es un defecto **abierto y distinto**: es lo que permite que R1 dispare sobre datos de Sífilis y aporte al log una línea que afirma "tamizaje negativo completo / unidad apta" en casos de Descarte. Se registra la conexión acá para que no se lea INV-16 como si hubiera cerrado el problema del centinela completo: cerró la mitad numérica.

### INV-17 — Precondición de la repetición por duplicado (RN-02)

**Enunciado.** La repetición por duplicado **solo se ordena** cuando la lectura inicial cayó en Zona Gris. Ningún otro resultado inicial la motiva:

$$
sco\_repeticion \neq \bot \implies sco\_inicial = \text{Zona Gris}
$$

**Fundamento.** Confirmado por el bioquímico de referencia (regla de negocio RN-02). Una lectura inicial No Reactiva no deja nada que dirimir, y una Reactiva ya cerró el tamizaje por su propio criterio: en ninguno de los dos casos el protocolo cursa un duplicado. El duplicado existe exclusivamente para resolver la indeterminación analítica de la Zona Gris — es el mecanismo que INV-01 (monotonía de precaución) e INV-03 (ambigüedad persistente) presuponen, y hasta acá vivía como supuesto tácito de ambos.

**Estado de enforcement: DECLARADO, NO EJECUTADO.** Ninguna capa rechaza hoy un `sco_repeticion_valor` con `sco_inicial` fuera de Zona Gris: `construir_hechos()` lo fuzzifica sin mirar la etiqueta inicial, y `WorkingMemoryFacts` no lo valida. El invariante se formaliza acá **antes** de tener validador, en el orden que fija la Consigna 1 (spec primero), y su enforcement queda como frente propio — no se cuela como anexo de la sesión de arbitraje.

**Consecuencia para el arbitraje de `epidemiological_status`.** RN-02 gobierna la **operatoria**, no la **representabilidad**. Varios pares de reglas terminales que empatan en peso de decisión son clínicamente inalcanzables bajo RN-02 pero siguen siendo entradas construibles mientras no haya validador:

| Par | Antecedente conjunto | Alcanzable bajo RN-02 |
|---|---|---|
| R4 vs R19 | `sco = No Reactivo` + `sco_repeticion = Reactivo` | No |
| marcador (R5, R7, R11, R12, R15, R16, R17) vs R19 | `sco = Reactivo` + `sco_repeticion = Reactivo` | No |
| R6 vs R18 | `sco = No Reactivo` + `sco_repeticion = Zona Gris` | No |
| R14 vs R18 | `sco = Reactivo` (Brucelosis) + `sco_repeticion = Zona Gris` | No |

Que un par sea inalcanzable **no lo exime** de tener resolución declarada: mientras la entrada sea construible, el motor puede llegar a arbitrarlo, y un `epidemiological_status` resuelto por orden de `priority` accidental es exactamente lo que el mecanismo de precedencia explícita (§INV-18) viene a impedir. La tabla de precedencia los cubre de forma defensiva, y la fila «Alcanzable» queda registrada acá para que, el día que INV-17 tenga validador, se sepa cuáles entradas pasan a ser código muerto verificable en vez de conjetura.

### INV-18 — Precedencia explícita de `epidemiological_status`

**Enunciado.** Cuando dos reglas terminales empatan en peso de decisión (INV-07) y declaran `epidemiological_status` distinto, el valor publicado se determina por una **resolución declarada para ese par**, nunca por el orden de `priority`.

**El problema que cierra.** `priority` cumplía dos roles a la vez: ordenaba la **evaluación** de las reglas y, como efecto lateral de que el arbitraje conserva al primer candidato de peso máximo, desempataba **qué `epidemiological_status` se publica**. El segundo rol nunca se especificó regla por regla — era una consecuencia del orden. Eso importa más que un detalle de presentación porque `epidemiological_status` es parte de `verdict.schema.json`, el único artefacto que el módulo neuronal puede consumir en fase post-analítica: un contrato neuro-simbólico no puede apoyarse en un campo cuyo valor depende de un orden que nadie declaró.

**Mecanismo.** Tabla declarativa por par de `rule_id` en `spec/rules/epi_precedence.json` (espejada en `seitt_core/rules/`, misma disciplina que `kb_rules.json`), validada contra `spec/schemas/epi_precedence.schema.json` en cada `RuleEngine.load()`. Cuatro resoluciones:

| `resolution` | Semántica | Origen típico |
|---|---|---|
| `winner` | Gana el `epidemiological_status` de la regla nombrada, sin importar peso ni prioridad. | Excepción clínica acotada (B1: R4 sobre R19). |
| `concat` | El veredicto publica la unión ordenada de ambos estados, separados por `" + "`. Los `null` se omiten. | «Ambos en la misma línea» (B2-B8). |
| `indistinct` | Se decidió que la elección no tiene consecuencia clínica; se conserva el incumbente. | Par sin caso real (C1, C2). |
| `pending_clinical_review` | El conflicto está **identificado y abierto**, a la espera de criterio clínico. Runtime idéntico a `indistinct`. | Familia A (sífilis). |

**Separación de responsabilidades.** El mecanismo gobierna **solo** `epidemiological_status`. `unit_disposition` y `donor_disposition` siguen saliendo del `best_candidate` del arbitraje por peso, intactos, de modo que ninguna edición de la tabla puede alterar una decisión clínica. Fijado como test (`test_la_precedencia_no_toca_la_disposicion`).

**Por qué por par y no un entero por regla.** Un orden total no puede expresar (i) una excepción acotada —R4 debe ganarle a R19 *sin* pasar a ganarle a ninguna otra regla—, (ii) la concatenación, ni (iii) —lo decisivo— la diferencia entre «se decidió que da igual» y «nadie lo decidió». Sin (iii) el chequeo de completitud no puede existir: una omisión sería indistinguible de una decisión.

**Completitud (enforcement).** Un par sin entrada **no levanta excepción en tiempo de inferencia**: se conserva el incumbente y el par se reporta en `InferenceResult.epi_undeclared_pairs`. Tumbar un veredicto de disposición correcta por una deuda de especificación le negaría al bioquímico un resultado válido. La detección va a CI, por dos vías complementarias:

1. **Estática** — enumeración exhaustiva del espacio de `WorkingMemoryFacts` discreto: todo par co-satisfacible que empata en peso con estados distintos debe tener entrada. Es el contrato de entrada real de `RuleEngine.evaluar()`, así que un par que Pydantic admite puede efectivamente llegar al arbitraje.
2. **Dinámica** — el Eval Harness falla si algún caso del golden produce `epi_undeclared_pairs` no vacío.

**Medición al cierre de esta sesión:** 24 pares co-satisfacibles con empate y estado distinto (de 44 que da el conteo estático ingenuo; 20 son antecedentes incompatibles). 10 resueltos —B1 por `winner`, B2-B8 por `concat`, C1/C2 por `indistinct`—, 14 en `pending_clinical_review`.

**Dos pares que el relevamiento previo no tenía.** La enumeración exhaustiva encontró `(R3, R6)` y `(R3, R14)`, ausentes de las tres familias del dossier. Ambos dependen de que `sco` y `sco_inicial` puedan diferir: `construir_hechos()` los deriva siempre de la misma fuzzificación, pero `WorkingMemoryFacts` no los acopla, así que el estado es construible entrando directo por `RuleEngine.evaluar()`. Se registra como deuda propia (ver CLAUDE.md): el contrato de memoria de trabajo admite un estado que el motor difuso no puede producir, y hasta acá nadie lo había mirado.

---

# Invariantes de la frontera neuro-simbólica (INV-09 … INV-14)

> Bloque a integrar en `spec/domain_model.md`. Verificar que los IDs estén
> libres antes de insertar: al cierre del Paso 2.5 estaban ocupados INV-01…08
> e INV-15 (forma dual del veredicto), más los `INV-STRUCT-*`. Al cierre de la
> sesión de contenido del núcleo simbólico se suma **INV-16** (ausencia de
> certeza sin lectura, §INV-16 arriba), que es de dominio y no de frontera.
> Si alguno de INV-09…14 ya está tomado, correrlos y avisar.
>
> INV-10 y INV-14 pertenecen a la mitad post-analítica del contrato
> (narrativa). Se incluyen aquí **solo para reservar el ID y fijar el
> enunciado**; su enforcement se implementa en la segunda tanda.

---

## INV-09 — Aislamiento de la confianza neuronal

**Enunciado.** La confianza de extracción emitida por el módulo neuronal
(`ExtractedField.confidence`, y su agregado `SampleInputFacts.extraction_confidence`)
es metadato de auditoría. **No puede ser antecedente de ninguna regla, ni
combinarse aritméticamente con `certeza_sco` o con ningún grado de pertenencia
difuso.**

**Fundamento.** Son magnitudes de dominios distintos: `confidence` mide fidelidad
de transcripción de un documento; `certeza_sco` mide pertenencia a una banda
analítica. Sumarlas, promediarlas o umbralizarlas conjuntamente produciría un
número sin referente clínico, y convertiría de hecho al LLM en participante de
la inferencia.

**Enforcement.** Cerrar `fact_path` en `rule.schema.json` a un enum sobre los
campos de `WorkingMemoryFacts`:

```json
"fact_path": {
  "type": "string",
  "enum": ["calidad_muestra", "marcador", "sco", "sco_inicial",
           "sco_repeticion", "certeza_sco", "nat", "riesgo", "vdrl", "clia"]
}
```

Con el enum cerrado, una regla que lea confianza del modelo **no valida contra
el DSL** y `RuleEngine.load()` la rechaza al arranque. Deja de ser una promesa
para volverse algo sintácticamente inexpresable — mismo movimiento que la
corrección del magic string de R20 (§4bis.4).

**Verificación.** `validate_spec.py`: una regla sintética con
`fact_path: "extraction_confidence"` debe ser rechazada por `rule.schema.json`.

---

## INV-10 — Estabilidad de la observación frente a perturbación de extracción

**Enunciado.** Sea $\Lambda:\mathbb{R}^+ \to \{\mathrm{NR}, \mathrm{ZG}, \mathrm{R}\}$
la función de etiquetado del Fuzzy Engine y $\Pi(x)$ el conjunto de perturbaciones
plausibles de OCR/NLP sobre el valor $x$. Una observación numérica es **inestable**
si

$$\exists\, x' \in \Pi(x) \;:\; \Lambda(x') \neq \Lambda(x)$$

Toda observación inestable **exige confirmación humana explícita del campo**,
con independencia de la `confidence` reportada por el modelo.

**Conjunto de perturbaciones $\Pi(x)$.** Cerrado y declarativo:

| Clase | Descripción | Ejemplo |
|---|---|---|
| `decimal_shift` | coma decimal desplazada un lugar en cualquier sentido | `0.95` → `9.5` |
| `last_digit_delta` | último dígito significativo $\pm 1$ | `1.09` → `1.10` |
| `digit_confusion` | confusiones frecuentes de OCR: $0\!\leftrightarrow\!8$, $1\!\leftrightarrow\!7$, $5\!\leftrightarrow\!6$, $3\!\leftrightarrow\!9$ | `0.85` → `0.95` |
| `digit_transposition` | intercambio de dos dígitos adyacentes | `1.05` → `1.50` |

**Fundamento.** El riesgo dominante de la extracción automática en este dominio
no es la alucinación semántica sino el **error de un dígito**. Un `9.5` leído
como `0.95` convierte un Reactivo en Zona Gris; un `1.05` leído como `0.05`
convierte una unidad a descartar en una unidad Apta. Ninguna autoevaluación del
modelo protege contra esto: un OCR puede estar muy seguro de un carácter mal
leído. La defensa es simbólica — se verifica la **estabilidad de la decisión**,
no la confianza de quien la informó.

**Enforcement.** `guardrails/extraction_gate.py`, materializado en
`BoundaryAnalysis` de `extraction_gate_report.schema.json`. Costo computacional
despreciable: $|\Pi(x)|$ es del orden de la decena y $\Lambda$ es una comparación
de umbrales.

---

## INV-11 — Precondición de validación humana y admisibilidad de lote

**Enunciado.** Ninguna instancia de `SampleInputFacts` con
`source = medgemma_extraction` alcanza el Inference Engine sin una
`ValidationAttestation` que la referencie. La atestación puede ser individual o
por lote; el lote es admisible únicamente cuando, para toda muestra $s$ del
conjunto $S$:

$$
\mathrm{lote\_admisible}(S) \iff \bigwedge_{s \in S} \Big[
\underbrace{\textstyle\bigwedge_{a \in A_s} \rho(a) = \mathrm{NoReactivo}}_{\text{sin hallazgo por ninguna vía}}
\;\wedge\;
\underbrace{\nexists\, a \in A_s : \rho(a) = \mathrm{Pendiente}}_{\text{sin ensayo en curso}}
$$
$$
\wedge\; \mathrm{integridad}(s) = \mathrm{Normal}
\;\wedge\; \neg\,\mathrm{riesgo}(s)
\;\wedge\; \mathrm{unresolved}(s) = \emptyset
\;\wedge\; \neg\,\mathrm{inestable}(s) \Big]
$$

donde $A_s$ es el conjunto de ensayos de la muestra (S/CO de cada marcador, NAT,
VDRL, CLIA) y $\rho$ su resultado en el vocabulario unificado `AssayResult`.

**Fundamento.** Criterio fijado por la bioquímica de referencia: se admite
aprobación por lote cuando los resultados son no reactivos. Formalmente, el lote
coincide con el conjunto de unidades cuyo veredicto sería **Apta por R1**;
cualquier desvío —Zona Gris, reactividad, ensayo pendiente, hemólisis o lipemia,
riesgo declarado en anamnesis, campo no resuelto— sale a revisión individual.

La cláusula $\neg\,\mathrm{inestable}(s)$ (INV-10) es constitutiva, no accesoria:
sin ella, un falso No Reactivo por error de un dígito entraría al lote y se
aprobaría en bloque sin que nadie mire ese campo, convirtiendo la aprobación por
lote en una ruta de bypass silencioso de R1.

Nótese que la primera conjunción es hoy una comprobación **uniforme** sobre los
tres campos de ensayo, y no tres casos especiales, gracias a la unificación de
vocabulario en `AssayResult` (Paso 2.5).

**Enforcement.** `adapters/extraction_adapter.py` rechaza con
`UnattestedExtractionError`. La elegibilidad se computa en
`guardrails/extraction_gate.py` y se persiste en `batch_predicate`.

---

## INV-12 — Prohibición de default clínico por omisión

**Enunciado.** Ningún campo clínicamente significativo puede adquirir valor por
omisión, ni en el adaptador de extracción, ni en el Fuzzy Engine, ni en los
contratos. Un campo ausente o no resuelto produce un **error explícito**
(`IncompleteExtractionError` / `DomainInvariantViolation`), nunca un valor
asumido.

**Fundamento.** Un default silencioso desactiva reglas sin dejar rastro. Si
`physical_integrity` ausente se asumiera `Normal`, R20 —único corto-circuito del
motor— no dispararía jamás sobre extracciones incompletas. El caso ya se
verificó empíricamente en el Paso 2: el default de `nat` a `"No Aplica"` habría
liberado unidades con NAT no informado, contra el flujo real del laboratorio.

**Corolario de representación.** La política "ausencia sí, `null` no" (§1.5) es
condición necesaria pero no suficiente: el código debe distinguir ambos casos
con `"campo" not in data`, nunca con `data.get("campo") is None`, que los
colapsa. Verificado como defecto real en el Paso 2.5.

**Enforcement.** `unresolved_fields` es `required` en el envelope aunque esté
vacío; `missing_required_fields` no vacío aborta la ingesta.

---

## INV-13 — Independencia de disponibilidad respecto del módulo neuronal

**Enunciado.** La capacidad del sistema de emitir un veredicto clínico es
**independiente** de la disponibilidad, latencia o corrección de MedGemma. Toda
funcionalidad del módulo neuronal es una mejora opcional sobre un camino
simbólico que ya es completo y correcto.

**Fundamento.** Es la lectura arquitectónica de la Consigna 5. Si el veredicto
dependiera de que el LLM responda, el sistema sería un wrapper con pasos extra,
sin importar cuán acotado esté el rol del modelo.

**Enforcement.** Inversión de dependencias: `seitt_core/ports/` define
`ExtractionPort` y `NarrationPort` como `typing.Protocol`; los adaptadores viven
en el borde. `seitt_core/` **no importa nada de MedGemma en ninguna dirección**.

**Verificación.** Test de arquitectura ejecutable: análisis AST de los imports de
`seitt_core/` que falla el build ante cualquier acoplamiento al módulo neuronal.
Es evidencia empírica de no-wrapper, no una afirmación del capítulo de diseño.

---

## INV-14 — Confinamiento del dato nominal *(reservado — post-analítico)*

**Enunciado.** `approver_id` y `approver_credential` no pueden cruzar hacia el
módulo neuronal en ninguna dirección, ni como entrada de extracción ni como
contexto de narrativa. Ningún identificador de donante acompaña a un `sample_id`
fuera del núcleo simbólico.

**Fundamento.** La atestación introduce el primer y único dato nominal de persona
real del sistema; el donante permanece anonimizado por diseño. El schema de
`narrative_request` ya es una proyección mínima con `additionalProperties: false`,
de modo que la garantía es estructural — pero conviene enunciarla, porque es
exactamente el tipo de campo que alguien agrega «para personalizar el reporte».
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
