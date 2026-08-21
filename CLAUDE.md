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
4. **IDE fijo / entorno controlado**: linting, formateador estandarizado,
   Docker Compose, reproducibilidad de builds. **Pendiente.**
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
  schemas/*.schema.json    5 JSON Schemas (Draft 2020-12)
  rules/kb_rules.json      KB declarativa: 20 reglas reales (22 entradas,
                            R2 desdoblada en 3 variantes de certeza)

seitt_core/   Fase 1: refactor del motor, DSL-driven (reemplaza a legacy/).
  domain.py, fuzzy_engine.py, rule_engine.py, explicador.py,
  expert_system.py
  rules/kb_rules.json       (copia sincronizada de spec/rules/)
  tests/                    23 tests pytest (regresión + fuzzy engine)
  eval/                     Fase 2: Eval Harness
    eval_dataset.json       28 casos con criterio experto (ground truth)
    eval_harness.py         Corre el dataset, mide métricas
    eval_report.json        Último reporte generado

app/          Fase 3: interfaz de usuario nueva, arquitectura web.
  api/                      Backend FastAPI. Adaptador HTTP sobre
                            expert_system.evaluar_caso() — no reexporta
                            el dominio directo: tiene sus propios modelos
                            de request/response (app/api/schemas.py).
  web/                      Frontend estático (HTML/CSS/JS plano, sin
                            paso de build), servido por FastAPI.

docs/         Papers académicos ya existentes (Poster, PIF, TP2) — leer
              con cautela, tienen discrepancias documentadas vs. el código
              real (ver domain_model.md §4bis).
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
python spec/validate_spec.py              # esperado: 45/45 OK
python -m pytest seitt_core/tests/ -v     # esperado: 23/23 passed
python seitt_core/eval/eval_harness.py    # esperado: 28/28, Tasa de Acierto 100%, kappa 1.0
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

- **`certainty_index = 1.0` en rechazo técnico (R20).** `expert_system`
  sintetiza un S/CO centinela (`0.0`) cuando hay interferencia física,
  para que R20 pueda cortar el ciclo; `fuzzificar_sco(0.0)` devuelve 100%
  de certeza. Resultado: un veredicto de Cuarentena llega con la certeza
  más alta del sistema, en el único caso donde nadie fuzzificó un S/CO
  real. Es un artefacto del centinela, no un dato clínico.
  *Corrección de fondo pendiente:* dejar `certainty_index = None` en ese
  camino. Fuera de alcance de la Fase 3 Paso 3A por tocar el núcleo
  simbólico y requerir revalidar el Eval Harness.
  *Contención actual (solo en el borde, no es la solución):* la API marca
  `certeza_es_significativa = false` cuando la disposición es Cuarentena,
  y el frontend oculta el bloque de certeza. Ver el comentario en
  `app/web/app.js`, función `mostrarVeredicto()`.

- **El Eval Harness no cubre la traza explicativa.** El bug de la
  plantilla de R20 (documentaba `{sco_label}` —el centinela `No Reactivo`—
  donde debía nombrar la calidad de muestra) convivió con **33/33 y
  kappa 1.0**: el harness compara `final_unit_disposition`,
  `final_donor_disposition`, presencia de acción pendiente y trazabilidad
  de `rule_id`, pero **nunca el contenido de `explanation_log`**. O sea
  que el argumento central del CDSS —la explicación auditable— es hoy la
  única salida del sistema sin ninguna verificación automatizada, y un
  error ahí no pone nada en rojo. Lo detectó una lectura humana al
  construir el adaptador de narración, no el arnés.
  *Extensión candidata (después de la demo):* assertions sobre el
  `explanation_log` esperado en `eval_dataset.json`, al menos para los
  casos cuya traza cita el valor de un campo (R20 con `calidad_muestra`,
  R2_* con `certeza_sco`, las reglas por marcador con `marcador`) — que
  son justamente donde un placeholder equivocado pasa desapercibido.

## Pendiente / próximos frentes (en orden sugerido)

1. Reorganización del repo (`legacy/`, `spec/`, `seitt_core/` como hermanos
   en la raíz) — completa y validada (45/45 spec, 23/23 tests, 28/28 eval
   harness, corrido en Windows con .venv).
2. Dockerización + entorno reproducible (Consigna 4).
3. Contrato JSON MedGemma ↔ Motor Difuso (extiende `sample_input.schema.json`).

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