"""test_rule_engine.py — La KB no se carga sin validar.

`RuleEngine.load()` hacía `if schema_path.exists()` antes de validar las
reglas contra `rule.schema.json`. Si el archivo no estaba, la KB se cargaba
**sin validar** y el motor seguía emitiendo veredictos como si nada: reglas
clínicas nunca verificadas sirviendo decisiones en un CDSS. Es el mismo
patrón de degradación silenciosa que tenía el montaje del frontend, y se
detectó al empaquetar (Consigna 4), porque una wheel sin los JSON Schema
entra exactamente por ese camino.

Lo que estos tests fijan es *cuándo* falla: al CONSTRUIR el motor, no al
evaluar un caso. La diferencia no es de estilo. Si el error apareciera
recién en `evaluar()`, un despliegue con la KB rota levantaría sano,
pasaría el health check y fallaría por primera vez con una muestra real
de un donante real.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from seitt_core.rule_engine import (
    _DEFAULT_RULES_PATH,
    _DEFAULT_SCHEMA_PATH,
    MalformedRuleError,
    RuleEngine,
)


@pytest.fixture
def kb_valida(tmp_path: Path) -> Path:
    """Copia intacta de la KB real, para aislar la variable del schema."""
    destino = tmp_path / "kb_rules.json"
    destino.write_text(_DEFAULT_RULES_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return destino


def test_sin_schema_el_motor_no_se_construye(kb_valida: Path, tmp_path: Path) -> None:
    """El caso de la wheel sin JSON Schema: antes cargaba en silencio."""
    schema_ausente = tmp_path / "no_existe" / "rule.schema.json"
    assert not schema_ausente.exists()

    with pytest.raises(MalformedRuleError) as exc:
        RuleEngine.load(kb_valida, schema_ausente)

    # El mensaje tiene que nombrar la ruta buscada: sin eso, diagnosticar un
    # contenedor mal armado obliga a leer el código del motor.
    assert str(schema_ausente) in str(exc.value)


def test_una_kb_que_no_conforma_falla_al_construir_no_al_evaluar(
    tmp_path: Path,
) -> None:
    """Criterio central: el rojo aparece en load(), antes de cualquier caso.

    Se corrompe una regla de un modo que el schema rechaza pero que Python
    aceptaría sin chistar — un operador que no existe en el DSL. Si la
    validación no corriera, el motor se construiría igual y el error saldría
    recién al evaluar la primera muestra.
    """
    reglas = json.loads(_DEFAULT_RULES_PATH.read_text(encoding="utf-8"))
    reglas[0]["antecedent"] = {
        "fact_path": "sco",
        "operator": "SE_PARECE_BASTANTE_A",
        "value": "No Reactivo",
    }
    kb_rota = tmp_path / "kb_rules.json"
    kb_rota.write_text(json.dumps(reglas), encoding="utf-8")

    with pytest.raises(MalformedRuleError) as exc:
        RuleEngine.load(kb_rota, _DEFAULT_SCHEMA_PATH)

    assert reglas[0]["rule_id"] in str(exc.value)


def test_require_schema_false_permite_saltear_pero_hay_que_pedirlo(
    kb_valida: Path, tmp_path: Path
) -> None:
    """La salida de emergencia existe, pero es explícita.

    El punto del cambio no es prohibir cargar sin validar: es que dejar de
    validar sea una decisión que alguien toma y firma, en vez de una
    consecuencia de que falte un archivo.
    """
    schema_ausente = tmp_path / "no_existe" / "rule.schema.json"

    motor = RuleEngine.load(kb_valida, schema_ausente, require_schema=False)

    assert motor.evaluar is not None


def test_la_carga_por_defecto_del_repo_sigue_validando() -> None:
    """Control positivo: con el schema en su lugar, la KB real carga."""
    motor = RuleEngine.load()
    assert motor is not None
