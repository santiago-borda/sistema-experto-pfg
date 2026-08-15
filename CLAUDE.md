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
legacy/       Código original (main.py CustomTkinter, expert_system.py,
              knowledge_base.py con reglas embebidas en lambdas, etc.)
              Se preserva intacto como referencia histórica — NO se edita.

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

docs/         Papers académicos ya existentes (Poster, PIF, TP2) — leer
              con cautela, tienen discrepancias documentadas vs. el código
              real (ver domain_model.md §4bis).
```

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

## Pendiente / próximos frentes (en orden sugerido)

1. Reorganización del repo (`legacy/`, `spec/`, `seitt_core/` como hermanos
   en la raíz) — en curso.
2. Dockerización + entorno reproducible (Consigna 4).
3. Contrato JSON MedGemma ↔ Motor Difuso (extiende `sample_input.schema.json`).
4. Adaptación de `main.py` (GUI) al nuevo `expert_system.evaluar_caso()` —
   deliberadamente diferida hasta que el contrato MedGemma esté cerrado,
   para no reescribir la UI dos veces.

## Al recibir una tarea sobre este proyecto

Antes de escribir código: revisar `domain_model.md` si la tarea toca
reglas de negocio, invariantes o el modelo de dominio. Antes de tocar
`kb_rules.json`: correr `spec/validate_spec.py` después del cambio, nunca
asumir que un JSON manualmente editado sigue siendo válido. Antes de
declarar algo "listo": correr los tres comandos de la sección "Estado
actual" de arriba.
