# SE-ITT — Sistema Experto Híbrido basado en Lógica Difusa para ITT en Bancos de Sangre

## Qué es esto

PFG (Proyecto Final de Grado) de Ingeniería en Sistemas de la Información (UCP).
Sistema experto que evalúa la aptitud de unidades de sangre donadas según
resultados de tamizaje serológico (Infecciones Transmisibles por Transfusión),
usando lógica difusa para clasificar valores S/CO y un motor de reglas
declarativo para el veredicto clínico. Marco normativo: Ley 22.990 y
Res. 1507/2015 (Argentina). El sistema es un CDSS (Clinical Decision Support
System): apoya, no reemplaza, al bioquímico responsable.

Roadmap a mediano plazo: integrar MedGemma (4B) como capa de extracción
pre-analítica NLP (parsing de reportes no estructurados → JSON), sin que el
LLM participe jamás de la inferencia clínica (arquitectura no-wrapper).

## Las 5 consignas de cátedra (innegociables en cualquier diseño o código)

1. **Spec Driven Development**: specs formales (JSON Schema / DSL) preceden
   a la implementación. Requerimientos y casos de prueba antes que código.
2. **No Vibe Coding**: tipado estático, invariantes de dominio ejecutables,
   manejo explícito de excepciones, cobertura de tests.
3. **Eval Harness**: evaluación automatizada — Tasa de Acierto, tiempo
   promedio de inferencia, concordancia (Cohen's Kappa) vs. criterio
   clínico experto, con foco reforzado en Zona Gris (0.9–1.1 S/CO).
4. **IDE fijo / entorno controlado**: Docker Compose, reproducibilidad de
   builds, linter y formateador **cerrados**. Imagen multi-stage con base
   pineada por digest, `constraints.txt`, perfiles `app`/`ci`, y `ruff`
   (check + format) como gate ejecutable en la etapa `test`. **Falta solo
   el type checker** (`mypy`) — ver frente 3 más abajo.
5. **No-Wrapper LLM**: MedGemma nunca decide el veredicto. Solo extrae
   (pre-analítico) y traduce el log explicativo a lenguaje natural
   (post-analítico). La frontera está forzada por schema, no por convención.

## Estructura del repo

```
legacy/       Código original (main.py con tkinter+ttk estándar,
              expert_system.py, knowledge_base.py con reglas embebidas
              en lambdas, etc.)
              Se preserva como referencia histórica — no se modifica
              ningún comportamiento clínico, regla de negocio, ni valor
              de umbral. Única excepción: los imports internos se
              actualizaron a rutas absolutas (`from legacy.xxx import ...`)
              como parte del `git mv` a este directorio, ya que ahora es
              un paquete y los imports relativos del root ya no resuelven.
  test_cases_manual/       6 casos de prueba manuales armados durante el
                            TP2 grupal, anteriores al Eval Harness formal.
                            Ya no se ejecutan por ningún script — fueron
                            superados por seitt_core/eval/eval_dataset.json
                            (28 casos, con criterio experto formalizado y
                            foco en Zona Gris). Se conservan solo como
                            referencia histórica de qué escenarios se
                            probaban antes de la Consigna 3.

spec/         Fase 0: especificación formal.
  domain_model.md          Invariantes (INV-01..08), fórmulas, hallazgos
  contracts.py             Modelos Pydantic v2 (enums, validadores)
  validate_spec.py         Arnés que valida schemas + KB + casos límite
  schemas/*.schema.json    8 JSON Schemas (Draft 2020-12)
  rules/kb_rules.json      KB declarativa: 25 entradas (R1..R23, con R2
                            desdoblada en 3 variantes de certeza)

seitt_core/   Fase 1: refactor del motor, DSL-driven (reemplaza a legacy/).
  domain.py, fuzzy_engine.py, rule_engine.py, explicador.py,
  expert_system.py
  rules/kb_rules.json       (copia sincronizada de spec/rules/)
  tests/                    tests pytest de regresión + fuzzy engine
  eval/                     Fase 2: Eval Harness
    eval_dataset.json       39 casos con criterio experto (ground truth),
                            incluido el contenido esperado de la traza
                            (expected.explanation_citations) y el
                            epidemiological_status esperado
    eval_harness.py         Corre el dataset, mide métricas
    eval_report.json        Último reporte generado

app/          Fase 3: interfaz de usuario nueva, arquitectura web.
  api/                      Backend FastAPI. Adaptador HTTP sobre
                            expert_system.evaluar_caso() — no reexporta
                            el dominio directo: tiene sus propios modelos
                            de request/response (app/api/schemas.py).
  web/                      Frontend estático (HTML/CSS/JS plano, sin
                            paso de build), servido por FastAPI.

tests/        Tests de nivel repo (no de un módulo): arquitectura
              (INV-13, por AST), API HTTP y empaquetado del artefacto
              distribuible.

docs/         Papers académicos ya existentes (Poster, PIF, TP2) — leer
              con cautela, tienen discrepancias documentadas vs. el código
              real (ver domain_model.md §4bis).

Dockerfile          Imagen multi-stage: builder / runtime / test.
docker-compose.yml  Perfiles `app` (demo), `ci` (validación), `dev`.
constraints.txt     Versiones exactas de TODO el árbol, transitivas
                    incluidas. Se regenera desde la imagen, no del host.
.dockerignore       Deja fuera legacy/, .venv/, .git/, artefactos.
.gitattributes      LF forzado (Windows + core.autocrlf=true).
```

## Origen y propiedad del repositorio

Este repositorio es una **migración con historial completo** desde el
repositorio original del TP2 grupal (`felix-toledo/sistema-experto-infecciones`),
donde el proyecto arrancó como trabajo en equipo. A partir de la migración,
el desarrollo continúa en solitario como parte del PFG, bajo
`santiago-borda/sistema-experto-pfg`. El historial de commits previo a la
migración se preservó intencionalmente (no se hizo squash) para dejar
trazabilidad clara de qué es aporte grupal (TP2) y qué es continuación
individual (PFG) — relevante para cualquier pregunta de autoría en la
defensa.

## Flujo de git (acordado, no lo cambies sin avisar)

- Trabajar en la rama **`refactor/spec-driven-v2`**, nunca directo en `main`.
- Si la rama no existe todavía en el repo local, crearla desde `main` antes
  de tocar cualquier archivo: `git checkout -b refactor/spec-driven-v2`.
- Si `legacy/` todavía no existe: mover ahí los archivos originales con
  `git mv` (preserva historial) — `main.py`, `expert_system.py`,
  `knowledge_base.py`, `inference_engine.py`, `fuzzy_engine.py`,
  `explicador.py`, `test_cases.py` — antes de agregar `spec/` y `seitt_core/`.
- **No mergear `refactor/spec-driven-v2` a `main` todavía.** Quedan dos
  condiciones pendientes antes del merge: (1) Dockerización cerrada,
  (2) contrato MedGemma↔Motor Difuso definido. Recién ahí, un commit
  final que documente la transición completa.
- Commits chicos y descriptivos por frente de trabajo (ej. "feat(spec):
  agrega working_memory_facts.schema.json", no un commit gigante con todo
  junto) — ayuda a que el `git log` sea legible como narrativa de
  ingeniería para la memoria técnica del PFG.

## Estado actual (verificar corriendo esto al empezar cualquier sesión)

```bash
ruff format --check . && ruff check .     # esperado: sin diferencias, "All checks passed!"
python spec/validate_spec.py              # esperado: 89/89 OK
python -m pytest                          # esperado: 99 passed
python seitt_core/eval/eval_harness.py    # esperado: 39/39, kappa 1.0, traza 39/39, 25/25 reglas
```

`ruff format --check` **verifica, no reescribe**. Para aplicar el formato:
`ruff format .` y `ruff check --fix .`. Config en `pyproject.toml`
(`[tool.ruff]`): `legacy/` está excluido y no se toca; `E501` está
deliberadamente fuera del ruleset — ver la nota en el propio archivo.

**En Windows**: `validate_spec.py` y el Eval Harness imprimen símbolos de
estado no-ASCII. Si la consola abre en cp1252 (habitual bajo un shell no
interactivo), el arnés muere con `UnicodeEncodeError` antes de reportar
nada — no es un fallo de validación. Anteponer `PYTHONIOENCODING=utf-8`.

Nótese que `pytest` corre **sin argumentos**: `tests/` (arquitectura, API,
empaquetado) y `seitt_core/tests/` (regresión, fuzzy) se recogen juntos.
Acotarlo a `seitt_core/tests/` deja fuera la mitad de la red de seguridad.

Lo mismo dentro del contenedor, que además valida la wheel real:

```bash
docker compose --profile ci up --build --exit-code-from ci   # exit 0 en verde
docker compose --profile app up --build                      # demo en :8000
SEITT_PORT=8001 docker compose --profile app up --build      # si 8000 está ocupado
```

Si alguno falla, es la primera prioridad a resolver antes de tocar cualquier
otra cosa — son la red de seguridad contra regresiones.

## Decisiones de arquitectura que hay que respetar

- **Veredicto bidimensional**: `unit_disposition` (Apta/Descarte/Cuarentena)
  × `donor_disposition` (Habilitado/Diferido_Temporal/Diferido_Permanente)
  son ejes independientes. No colapsar en un enum único.
- **Arbitraje por peso (INV-07)**: el motor dispara TODAS las reglas que
  matchean (no first-match), y resuelve por jerarquía de peso de decisión
  (Cuarentena=4 > Descarte+Permanente=3 > Descarte+Temporal=2 > Descarte=1
  > Apta=0). R20 (integridad física) es el único corto-circuito real.
- **KB declarativa externa**: las reglas viven en `kb_rules.json`, nunca
  embebidas como lambdas en Python (eso era el defecto principal del
  legado). `RuleEngine.load()` re-valida contra `rule.schema.json` en cada
  arranque — no confiar en que el archivo siga siendo válido sin chequeo.
- **Zona Gris (INV-01, "Regla de Oro")**: monotonía de precaución estricta.
  Un valor inicial en Zona Gris (0.9 ≤ S/CO ≤ 1.1) SIEMPRE termina en
  Descarte de la unidad, sin importar el resultado de la repetición.
- **Certeza difusa**: es una rampa lineal (NO trapecio simétrico) — 100%
  en el borde 0.9, 0% en el borde 1.1. Se compara a precisión completa,
  el redondeo a 2 decimales es solo para presentación (bug real
  encontrado y corregido por el Eval Harness — ver domain_model.md §2).
- **NAT solo aplica a HIV/HBV/HCV** (INV-08). 7 marcadores en total:
  HIV, HBV, HCV, Sifilis, Chagas, HTLV_I_II, Brucelosis.

## Convenciones de código

- Python tipado estáticamente (type hints en toda función pública).
- Pydantic v2 para cualquier estructura de datos que cruce un límite de
  módulo (nunca dicts sueltos entre capas).
- Excepciones explícitas: heredar de `SEITTDomainError` (en `domain.py`),
  nunca `except Exception` genérico ni fallos silenciosos.
- Toda regla nueva de negocio va primero a `kb_rules.json` +
  `domain_model.md` (spec), después al código — nunca al revés.

## Hallazgos conocidos (deuda técnica registrada, no olvidada)

Defectos reales detectados y **deliberadamente no corregidos todavía**,
con el motivo del diferimiento. Se listan acá para que no se pierdan
entre sesiones ni se redescubran desde cero.

- ~~**`certainty_index = 1.0` en rechazo técnico (R20).**~~ **SALDADA.**
  `expert_system` sintetizaba un S/CO centinela (`0.0`) ante interferencia
  física, y `fuzzificar_sco(0.0)` devuelve 100% de certeza: el rechazo
  técnico llegaba con la certeza **más alta** del sistema, en el único
  camino donde nadie leyó un S/CO. Se corrige pasando `None` en vez de
  `0.0`, y se formaliza como **INV-16** (ausencia de certeza sin lectura)
  en `domain_model.md`. El contrato ya lo admitía (`certainty_index` era
  `float | None` y no figura en los `required` de `verdict.schema.json`),
  así que no hubo ningún invariante que reescribir — verificado con un
  barrido, no por lectura.
  La contención del borde dejó de ser contención: `certeza_es_significativa`
  se derivaba de la disposición (`!= Cuarentena`), un proxy que tapaba el
  número inventado sin conocer el hecho; ahora deriva de que
  `certainty_index` exista. El linter confirmó que el acoplamiento se fue
  (`UnitDisposition` quedó sin uso en `app/api/main.py`).
  *Ojo con el alcance:* INV-16 gobierna la **certeza**, no la **etiqueta**.
  El centinela de `sco` sigue vivo y es la causa del hallazgo de Sífilis de
  más abajo. Se cerró la mitad numérica del problema del centinela.

- ~~**El Eval Harness no cubre la traza explicativa.**~~ **SALDADA.**
  El arnés ahora verifica el contenido de `explanation_log` en los 33
  casos: `expected.explanation_citations` declara, por línea, qué campo
  cita la regla y con qué valor renderizado, y `verificar_traza()` lo
  compara. La línea esperada se **re-renderiza desde la plantilla vigente
  de la KB** con los valores golden, así que reescribir la redacción de
  una regla no rompe los 34 casos, pero citar otro campo sí. Control
  negativo en `seitt_core/tests/test_eval_harness.py`: con el bug
  histórico de R20 reintroducido, el arnés baja a 31/33 y sale con
  código 1.

- ~~**[PRIORIDAD ALTA] El veredicto de Sífilis podía liberar un reactivo
  sin confirmar.**~~ **SALDADA la mitad de disposición — primera corrección
  de esta cadena de sesiones con impacto real en `unit_disposition`/
  `donor_disposition`, no solo en trazabilidad o texto de reporte.**
  Confirmado con el bioquímico de referencia: un reactivo en cualquiera de
  las dos técnicas (VDRL o CLIA), o discordancia entre ambas, es
  `Descarte`/`Diferido_Temporal` inmediato — no hay estado clínico de
  "solo esperar". Contra ese criterio, la matriz VDRL×CLIA tenía tres
  huecos:
  - **R8** (`vdrl=Reactivo`, CLIA no informado) era `intermediate`: dejaba
    la unidad sin disposición (`null/null`) en vez de descartarla. Pasa a
    `terminal`, acotada con `clia=Pendiente` en el antecedente (antes no
    miraba `clia` en absoluto).
  - **Discordancia sin regla** (`vdrl=Reactivo, clia=No Reactivo`): ningún
    caso la representaba. Alta de **R22** (`OR` de dos grupos `AND` —
    primer uso de `OR` anidado en la KB), que también cubre el defecto
    original.
  - **Defecto original** (`vdrl` no informado, `clia=Reactivo` → `Apta`):
    R1 matcheaba sobre el centinela sintético (`sco`/`nat` derivados) sin
    que ninguna regla intermedia invalidara la candidatura, y la unidad se
    liberaba. Cerrado por R22.
  - **VDRL y CLIA ambos sin informar**: única celda de la matriz sin
    veredicto. Alta de **R23** (intermediate, bloquea vía la cláusula de
    anulación ya existente en `rule_engine.py` — cero cambios de motor).
  Ver `domain_model.md` §INV-05 para la matriz completa de 9 celdas y la
  nota de fragilidad de R23 (el bloqueo depende de que exista una regla
  intermedia para `vdrl=Pendiente AND clia=Pendiente`; si se elimina, R1
  vuelve a liberar sin lectura, la misma clase de dependencia implícita ya
  documentada para R20/INV-16).

  **Lo que esta sesión NO tocó — sigue abierto:** el hallazgo original
  era sobre una afirmación **falsa en el log**, no solo sobre disposición.
  R1 sigue matcheando (y su línea "tamizaje negativo completo... unidad
  apta" sigue apareciendo en `explanation_log`) en TODOS los casos de
  Sífilis reactiva, incluidos los que ahora arbitran a R8/R9/R10/R22 —
  simplemente ya no *gana* el arbitraje, pero la línea falsa sigue
  imprimiéndose. La pregunta pendiente al bioquímico sigue siendo la
  misma: ¿el `explanation_log` es registro completo de evidencia (toda
  regla que matcheó queda, y el defecto está en que R1 *matchee*) o
  justificación del veredicto (solo quedan las líneas que lo sostienen)?
  Ninguna variante de supresión de línea se implementó en esta sesión —
  sigue bloqueada, ahora exclusivamente por esa pregunta de diseño del
  log, ya no por la disposición clínica.

- **El redondeo de `certeza_sco` colapsa clasificaciones distintas en el
  mismo número.** En el borde exacto de umbral, dos casos que el motor
  clasifica **distinto** muestran el mismo porcentaje en pantalla:

  ```
  EV06 sco=1.01     certeza=45.00000000000002  -> "45.0"  -> R2_alta_certeza
  EV07 sco=1.010001 certeza=44.99950000000006  -> "45.0"  -> R2_baja_certeza
  EV08 sco=1.04     certeza=30.000000000000014 -> "30.0"  -> R2_baja_certeza
  EV09 sco=1.040001 certeza=29.999500000000058 -> "30.0"  -> R2_critica
  ```

  No es un bug: es el comportamiento documentado (comparación a precisión
  completa, redondeo solo para presentación, ver §2). Lo salva que el
  texto dice "alta"/"baja"/"crítica", así que la traza completa no es
  ambigua — solo el número lo es. Se registra porque cae justo en Zona
  Gris, el foco de la Consigna 3, y porque cualquier decisión futura
  sobre cómo se presenta la certeza debería conocerlo.

- **[PRIORIDAD ALTA] El `epidemiological_status` lo decide un desempate por
  prioridad que nadie especificó — 23 grupos abiertos.** Cuando dos reglas
  terminales empatan en peso de decisión (INV-07), el arbitraje lo resuelve
  la prioridad, y con ella **qué `epidemiological_status` se publica**. Ese
  desempate no está declarado regla por regla: es un efecto lateral del
  orden. Medido sobre la KB actual: **32 pares** de terminales empatan en
  peso con `epidemiological_status` distinto; 9 involucraban a R4 y quedaron
  resueltos al acotarla, **23 siguen abiertos** (sífilis interno R9/R10,
  R19 vs. las reglas por marcador, R18/R6/R3/R14).
  *Por qué sube a prioridad alta:* es el campo del veredicto que **MedGemma
  va a leer en fase post-analítica** — `verdict.schema.json` lo declara
  parte del único artefacto que el módulo neuronal puede consumir para
  redactar el reporte final. Un campo cuyo valor depende de un orden no
  especificado no es una base aceptable para el contrato neuro-simbólico.
  El golden de los 34 casos ya lo congela, así que hoy no puede cambiar en
  silencio; lo que falta es **decidirlo**, con consulta clínica.
  Sesión propia: es diseño, no limpieza.

- **El Eval Harness no ejercita el adaptador de narración.**
  `seitt_core/adapters/static_narration.py` es el adaptador **por defecto**
  (INV-13) y produce la prosa que el bioquímico lee en pantalla, pero
  ningún caso del arnés lo invoca: el harness llama a `evaluar_caso()` y
  compara el `InferenceVerdict`, nunca `narrate()`. El caso concreto que lo
  hizo visible es `epidemiological_status`: `StaticNarrationAdapter` lo
  imprime como *"Estado epidemiológico: …"* desde hace tiempo, o sea que
  **estaba en pantalla y era invisible al arnés** — exactamente la brecha
  que ya costó el bug de R20 y las tres líneas de Sífilis. Que el golden lo
  verifique ahora cubre el veredicto, no la narración.
  *Nota:* la narración tiene una segunda rama sin cubrir, la de veredicto
  pendiente (INV-15 forma ii).

- **`trace_match` en el Eval Harness usa `any`, no `all`.** Un caso que
  declara `expected_rule_ids: ["R2_alta_certeza", "R3"]` pasa aunque solo
  dispare una de las dos. Es una debilidad preexistente y distinta de la
  del contenido de la traza (que sí quedó cubierta): esta es sobre qué
  reglas se exigen, no sobre qué dice el texto. Endurecerla a `all`
  probablemente no rompa nada hoy, pero conviene hacerlo con el resto de
  los cambios del núcleo y no de forma suelta.

- ~~**`RuleEngine.load()` omite la validación si falta el schema.**~~
  **SALDADA.** La carga hacía `if schema_path.exists()` antes de validar
  la KB: sin el archivo, las reglas se cargaban **sin validar** y el motor
  seguía emitiendo veredictos. Ahora la ausencia del schema levanta
  `MalformedRuleError` **al construir el motor, no al evaluar** — la
  diferencia importa: fallando en `evaluar()`, un despliegue con la KB rota
  levanta sano, pasa el health check y falla por primera vez con una
  muestra real. Saltear la validación exige `require_schema=False`
  explícito, para que sea una decisión firmada y no la consecuencia de que
  falte un archivo. Tests en `seitt_core/tests/test_rule_engine.py`,
  incluido uno que corrompe una regla con un operador que el DSL no tiene.
  El chequeo de `_verificar_arranque()` en la API se conserva: ya no es la
  única línea de defensa (que era el problema — protegía solo a quien
  entraba por la API), pero falla en el import y no en la primera
  inferencia, y su mensaje habla del despliegue en vez del motor.

- **`_DEFAULT_RULES_PATH` / `_DEFAULT_SCHEMA_PATH` son privadas y las lee
  `app/`.** *(La ventana que esta deuda declaraba —"la próxima vez que se
  toque el núcleo"— se abrió y se dejó pasar a propósito: la sesión que
  corrigió `RuleEngine.load()` tenía alcance cerrado por commit y promover
  nombres a API pública cambia la superficie del módulo, que es decisión
  propia y no anexo de otra. Sigue abierta, ahora con el precedente de que
  el disparador ya sonó una vez.)* `app/api/main.py` importa esas dos constantes de
  `seitt_core.rule_engine` para el chequeo de arranque. Se eligió eso
  antes que reconstruir las rutas en el adaptador, porque una ruta
  duplicada se desincroniza en silencio del motor — que es justo el fallo
  que el arranque existe para impedir. Pero deja al borde HTTP acoplado a
  un nombre privado del núcleo.
  *Corrección pendiente:* promoverlas a API pública de `rule_engine` (o
  exponer un `RuleEngine.describe()` con rutas y cantidad de reglas) la
  próxima vez que se toque el núcleo.

- **El pineo de dependencias es por versión, no por hash.**
  `constraints.txt` fija versiones exactas de todo el árbol, lo que
  protege contra la deriva natural de PyPI. No protege contra que se
  reemplace el contenido de una versión ya publicada. El paso siguiente
  es `--require-hashes` con los digests generados por plataforma; se
  difiere porque la base ya está pineada por digest y el costo/beneficio
  no lo justifica todavía.

- **El Eval Harness escribe `eval_report.json` dentro del paquete.**
  `_REPORT_PATH = Path(__file__).parent / "eval_report.json"`, o sea que
  escribe en `site-packages` cuando corre desde una instalación real. Hoy
  no molesta porque el arnés solo corre en la etapa `test` de la imagen,
  que es root. Si algún día se corriera en el contenedor de runtime (no
  root, `read_only: true`), fallaría con `PermissionError`. Lo correcto
  sería un `--output` con default en el cwd.

## Pendiente / próximos frentes (en orden sugerido)

1. Reorganización del repo (`legacy/`, `spec/`, `seitt_core/` como hermanos
   en la raíz) — completa y validada (45/45 spec, 23/23 tests, 28/28 eval
   harness, corrido en Windows con .venv).
2. Dockerización + entorno reproducible (Consigna 4) — **completa**.
   Imagen multi-stage con base pineada por digest, usuario no-root,
   `HEALTHCHECK` contra `/api/health`, `constraints.txt` con todo el árbol
   cerrado, y perfiles `app`/`ci`/`dev` en Compose. Verificado desde un
   clon limpio: 87/87, 75 passed, 33/33 con kappa 1.0 dentro de la imagen,
   y veredicto + traza explicativa idénticos a los del host.
3. **Type checker (`mypy`) — lo único que falta de la Consigna 4.**
   Linter y formateador ya están cerrados (`ruff`, gate en la etapa
   `test`); `mypy` se difirió a propósito a una sesión propia, no por
   olvido. El motivo: `--strict` sobre el motor de reglas va a destapar
   problemas reales de tipado en la frontera difusa — las reglas de
   `kb_rules` circulan como `dict` sin tipar y `_resolve_fact_value`
   devuelve `Any`. Tiparlo de verdad implica modelar las reglas con
   Pydantic, es decir tocar el núcleo simbólico y revalidar el Eval
   Harness. Decidir antes de empezar: ¿estricto desde el día 1, o baseline
   con excepciones documentadas que se van cerrando? Lo que **no** hay que
   hacer es colarlo como anexo de otra sesión.
4. ~~**Caso golden para R13.**~~ **CERRADO.** R13 era la única de las 23
   entradas de la KB que ningún caso del Eval Harness ejercitaba. Se cerró
   con **EV34** (el `case_id` que estaba reservado), confirmado por la
   bioquímica de referencia y sobre R13 ya corregida: su antecedente exige
   ahora que la repetición por duplicado se haya cursado, precondición
   **operativa** (el NAT se deriva a laboratorio externo y su informe llega
   con el duplicado ya hecho) documentada en la nota de alcance de INV-04.
   Cobertura de la KB: **23/23**.

5. Contrato JSON MedGemma ↔ Motor Difuso (extiende `sample_input.schema.json`).
   El hueco del servicio ya está documentado en `docker-compose.yml`, en
   comentario y sin implementar, para no reestructurar el compose después.

### Decisión de interfaz (Fase 3, Paso 3A)

La GUI **no se adapta: se reemplaza**. Decisión explícita del titular del
proyecto — Tkinter quedó anticuado para la demo. `legacy/main.py` se
preserva sin cambios como referencia histórica del TP2, igual que el
resto de `legacy/`; no se adapta a la nueva firma de `evaluar_caso()`.

La interfaz nueva es web (FastAPI + frontend estático HTML/JS, sin
framework de build) y vive en `app/`, hermano de `spec/`, `seitt_core/` y
`legacy/`. La elección de FastAPI **no es cosmética**:

- **Dockeriza de forma directa** (Consigna 4, próximo frente): un
  contenedor headless sirve la API sin arrastrar ningún toolkit gráfico.
  Por eso `fastapi`/`uvicorn` van como extra opcional en `pyproject.toml`,
  no como dependencia principal — el núcleo se instala sin la capa de
  presentación.
- **Es el mismo tipo de borde por el que va a entrar la extracción
  MedGemma**: la API es el "puerto" en su forma más literal. La
  dependencia va siempre `app/ → seitt_core/`, nunca al revés, y
  `seitt_core/` no importa nada de `app/` ni del borde neuronal (INV-13,
  verificado por análisis AST en `tests/test_architecture.py`).

## Al recibir una tarea sobre este proyecto

Primero: confirmar con `git branch --show-current` que se está parado en
`refactor/spec-driven-v2`, no en `main`. Si no existe la rama o estás en
`main`, resolverlo antes de cualquier otra cosa (ver sección de git arriba).

Antes de escribir código: revisar `domain_model.md` si la tarea toca
reglas de negocio, invariantes o el modelo de dominio. Antes de tocar
`kb_rules.json`: correr `spec/validate_spec.py` después del cambio, nunca
asumir que un JSON manualmente editado sigue siendo válido. Antes de
declarar algo "listo": correr los tres comandos de la sección "Estado
actual" de arriba.