"""test_packaging.py — El artefacto distribuible contiene lo que el veredicto necesita.

Este archivo existe por un defecto real, detectado al abrir la Consigna 4:
`pip install .` producía una instalación **completamente no funcional**. La
wheel llevaba once `.py` y nada más — sin `kb_rules.json` (la KB), sin los
JSON Schema, sin el dataset del Eval Harness y sin `app/web/`. El motor no
podía emitir un solo veredicto y `app.api.main` ni siquiera importaba.

Nada de eso aparecía en rojo porque el entorno de desarrollo usa una
instalación **editable**: el finder que genera setuptools mapea `spec`,
`seitt_core` y `app` de vuelta al árbol fuente, así que `Path(__file__)`
siempre cae dentro del repo y todos los recursos están ahí. Los 87/65/33 en
verde nunca ejercitaron el artefacto que se distribuye.

De ahí que las pruebas de acá vayan en dos capas, porque miden cosas
distintas:

1. **Resolución desde un cwd arbitrario.** Verifica que ningún recurso
   dependa del directorio de trabajo. Es la propiedad que hace que el
   contenedor pueda ejecutar sin `cd` en el entrypoint ni `PYTHONPATH`
   inyectado.

2. **Cobertura de `package-data`.** Verifica que cada recurso de runtime esté
   declarado en `pyproject.toml`. Ésta es la capa que de verdad protege la
   wheel: bajo instalación editable la capa 1 pasa aunque no se declare un
   solo archivo, porque los lee del repo. Sin la capa 2, el defecto original
   volvería a pasar desapercibido exactamente igual que la primera vez.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

import app as app_pkg
import seitt_core
import spec
from seitt_core.expert_system import evaluar_caso
from seitt_core.rule_engine import RuleEngine

# Las rutas se derivan de la UBICACIÓN DEL PAQUETE IMPORTADO, no del repo:
# es la misma resolución que hace el código productivo, así que en una
# instalación no-editable estas constantes apuntan a site-packages y el test
# mide la wheel, no el árbol fuente.
_SEITT_CORE_DIR = Path(seitt_core.__file__).resolve().parent
_SPEC_DIR = Path(spec.__file__).resolve().parent
_APP_DIR = Path(app_pkg.__file__).resolve().parent

_KB_PATH = _SEITT_CORE_DIR / "rules" / "kb_rules.json"
_SCHEMAS_DIR = _SPEC_DIR / "schemas"
_DATASET_PATH = _SEITT_CORE_DIR / "eval" / "eval_dataset.json"
_WEB_DIR = _APP_DIR / "web"

# Inventario explícito de recursos no-Python leídos en runtime, como pares
# (paquete, ruta relativa al paquete). Se enumera a mano a propósito: si
# alguien agrega un recurso nuevo y no lo suma acá, el test no lo cubre — y
# esa omisión queda visible en el diff, que es donde se puede discutir.
_RECURSOS_DE_RUNTIME: list[tuple[str, str]] = [
    ("seitt_core", "rules/kb_rules.json"),
    ("spec", "rules/kb_rules.json"),
    ("spec", "schemas/rule.schema.json"),
    ("spec", "schemas/eval_case.schema.json"),
    ("spec", "schemas/sample_input.schema.json"),
    ("spec", "schemas/working_memory_facts.schema.json"),
    ("spec", "schemas/verdict.schema.json"),
    ("spec", "schemas/extraction_envelope.schema.json"),
    ("spec", "schemas/extraction_gate_report.schema.json"),
    ("spec", "schemas/validation_attestation.schema.json"),
    ("seitt_core.eval", "eval_dataset.json"),
    ("app", "web/index.html"),
    ("app", "web/app.js"),
    ("app", "web/styles.css"),
]

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _REPO_ROOT / "pyproject.toml"


# ── Capa 1: resolución independiente del directorio de trabajo ───────────

@pytest.fixture()
def cwd_arbitrario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Sitúa el proceso en un directorio vacío, sin relación con el repo."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_kb_carga_desde_cwd_arbitrario(cwd_arbitrario: Path) -> None:
    """La KB es el recurso cuya ausencia rompía todo: sin ella, cero veredictos."""
    motor = RuleEngine.load()
    assert motor is not None
    assert _KB_PATH.is_file(), f"KB ausente en {_KB_PATH}"
    assert len(json.loads(_KB_PATH.read_text(encoding="utf-8"))) > 0


def test_schemas_cargan_desde_cwd_arbitrario(cwd_arbitrario: Path) -> None:
    """`rule.schema.json` se lee en CADA arranque de `RuleEngine.load()`."""
    esquemas = sorted(_SCHEMAS_DIR.glob("*.json"))
    assert esquemas, f"no hay JSON Schemas en {_SCHEMAS_DIR}"
    for esquema in esquemas:
        json.loads(esquema.read_text(encoding="utf-8"))


def test_dataset_del_eval_carga_desde_cwd_arbitrario(cwd_arbitrario: Path) -> None:
    """El ground truth de la Consigna 3 viaja con el paquete."""
    assert _DATASET_PATH.is_file(), f"dataset ausente en {_DATASET_PATH}"
    casos = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert len(casos) > 0


def test_frontend_presente_desde_cwd_arbitrario(cwd_arbitrario: Path) -> None:
    """Su ausencia era el fallo silencioso: servidor sano, 404 en `/`."""
    assert _WEB_DIR.is_dir(), f"frontend ausente en {_WEB_DIR}"
    for archivo in ("index.html", "app.js", "styles.css"):
        assert (_WEB_DIR / archivo).is_file(), f"falta app/web/{archivo}"


def test_inferencia_completa_desde_cwd_arbitrario(cwd_arbitrario: Path) -> None:
    """Extremo a extremo: si faltara algún recurso, esto no llega al veredicto.

    Se informa `nat` explícitamente para alcanzar un veredicto TERMINAL. Sin
    ese dato, HIV queda con NAT en 'Pendiente' y R1 no dispara — la unidad no
    se libera con NAT no informado, que es el comportamiento correcto pero
    dejaría el camino de renderizado de la traza sin ejercitar.

    Este test no verifica criterio clínico (de eso se ocupan el Eval Harness
    y `seitt_core/tests/`): verifica que la cadena completa
    fuzzy -> KB -> arbitraje -> explicación funcione sin depender del cwd.
    """
    veredicto = evaluar_caso(
        sample_id="PKG-001",
        calidad_muestra="Normal",
        marcador="HIV",
        riesgo=False,
        sco_inicial_valor=0.2,
        nat="No Reactivo",
    )
    assert veredicto.final_unit_disposition is not None
    assert veredicto.triggered_rules
    assert veredicto.explanation_log


def test_api_arranca_desde_cwd_arbitrario(cwd_arbitrario: Path) -> None:
    """El arranque fail-fast pasa en verde y `/api/health` reporta readiness real."""
    from fastapi.testclient import TestClient

    from app.api.main import app as fastapi_app

    respuesta = TestClient(fastapi_app).get("/api/health")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["kb_cargada"] is True
    assert cuerpo["kb_schema_validado"] is True
    assert cuerpo["web_montado"] is True
    assert cuerpo["kb_reglas"] > 0


# ── Capa 2: lo declarado en pyproject.toml cubre lo que se lee ───────────

def _declaracion_setuptools() -> dict:
    if not _PYPROJECT.is_file():
        pytest.skip("sin pyproject.toml: se corre contra un árbol instalado, no el repo")
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["tool"]["setuptools"]


def test_packages_declara_los_subpaquetes_del_nucleo() -> None:
    """`adapters`, `ports` y `eval` faltaban: `app.api.main` no importaba."""
    declarados = set(_declaracion_setuptools()["packages"])
    for paquete in ("seitt_core.adapters", "seitt_core.ports", "seitt_core.eval"):
        assert paquete in declarados, (
            f"{paquete} no está en [tool.setuptools].packages — no viajaría en la wheel"
        )


def test_package_data_cubre_todo_recurso_de_runtime() -> None:
    """Cada recurso del inventario tiene que caer bajo algún glob declarado.

    Los globs se expanden con `Path.glob`, que es la misma semántica que usa
    setuptools para resolver `package-data`; así el test mide la declaración
    real y no una reinterpretación de ella.
    """
    package_data = _declaracion_setuptools().get("package-data", {})
    assert package_data, "no hay [tool.setuptools.package-data]: la wheel iría sin recursos"

    incluidos: set[Path] = set()
    for paquete, patrones in package_data.items():
        dir_paquete = _REPO_ROOT / Path(*paquete.split("."))
        for patron in patrones:
            incluidos.update(p.resolve() for p in dir_paquete.glob(patron) if p.is_file())

    faltantes = [
        f"{paquete}/{relativa}"
        for paquete, relativa in _RECURSOS_DE_RUNTIME
        if (_REPO_ROOT / Path(*paquete.split(".")) / relativa).resolve() not in incluidos
    ]
    assert not faltantes, (
        "recursos leídos en runtime que package-data NO declara "
        f"(no viajarían en la wheel): {faltantes}"
    )


def test_el_reporte_del_eval_no_se_empaqueta() -> None:
    """`eval_report.json` es una SALIDA del arnés, no un insumo.

    Empaquetar el resultado de una corrida dentro del artefacto que se va a
    evaluar invita a confundir evidencia con dato de entrada, y además haría
    que dos builds difieran según si alguien corrió el arnés antes.
    """
    patrones = _declaracion_setuptools().get("package-data", {}).get("seitt_core.eval", [])
    incluidos = {
        p.name
        for patron in patrones
        for p in (_REPO_ROOT / "seitt_core" / "eval").glob(patron)
        if p.is_file()
    }
    assert "eval_report.json" not in incluidos
