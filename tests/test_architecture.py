"""test_architecture.py — Evidencia empírica de INV-13 (Consigna 5).

Vive en `tests/` y no en `seitt_core/tests/` a propósito: no verifica el
comportamiento de un módulo, verifica una propiedad estructural del repo
completo.

**Para la memoria técnica del PFG:** este archivo es la prueba ejecutable
de la arquitectura no-wrapper. La Consigna 5 exige que MedGemma nunca
participe de la inferencia clínica; afirmarlo en el capítulo de diseño es
barato, porque nada impide que un import se cuele después. Acá la
afirmación se verifica: se recorre el AST de cada módulo de `seitt_core/`
y se falla el build ante cualquier import del borde neuronal. La frontera
deja de ser una convención documentada y pasa a ser una condición que el
CI puede romper.

Se analizan los imports REALES vía `ast`, no nombres de archivo ni
heurísticas de texto: un `import torch` dentro de una función, en un
módulo llamado `utils.py`, se detecta igual.

Cubre dos fronteras:

1. **Borde neuronal** (INV-13): el núcleo simbólico debe poder emitir un
   veredicto sin que exista MedGemma. Los adaptadores neuronales viven
   fuera de `seitt_core/`, detrás de los `Protocol` de `seitt_core/ports/`.
2. **Borde web**: `app/` depende de `seitt_core/`, nunca al revés. Si el
   núcleo importara FastAPI, el motor clínico dejaría de ser utilizable
   como biblioteca (por el Eval Harness, por un batch, por un test) sin
   levantar un servidor.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_NUCLEO = Path(__file__).resolve().parent.parent / "seitt_core"

# Módulos del borde neuronal. Si alguno aparece importado en seitt_core/,
# el sistema dejó de ser no-wrapper: el veredicto pasaría a depender de la
# disponibilidad del modelo.
_BORDE_NEURONAL = frozenset({
    "medgemma",
    "transformers",
    "torch",
    "ollama",
    "llama_cpp",
    "huggingface",
    "huggingface_hub",
})

# Módulos del borde web. El núcleo debe ser importable sin ellos.
_BORDE_WEB = frozenset({
    "fastapi",
    "starlette",
    "uvicorn",
    "jinja2",
})

_PROHIBIDOS = _BORDE_NEURONAL | _BORDE_WEB


def _modulos_del_nucleo() -> list[Path]:
    return sorted(p for p in _NUCLEO.rglob("*.py") if "__pycache__" not in p.parts)


def _imports_de(archivo: Path) -> set[str]:
    """Extrae los módulos raíz importados por un archivo, vía AST.

    Devuelve el primer segmento del nombre punteado ('torch.nn' -> 'torch')
    porque es el paquete cuya presencia delata el acoplamiento. Los imports
    relativos (`from .domain import ...`, nivel > 0) se ignoran: son
    internos al propio paquete por definición.
    """
    arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
    raices: set[str] = set()

    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                raices.add(alias.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level and nodo.level > 0:
                continue  # import relativo: interno al paquete
            if nodo.module:
                raices.add(nodo.module.split(".")[0])

    return raices


def test_hay_modulos_para_analizar():
    """Guarda contra un falso verde: si el glob no encuentra nada (por un
    rename de carpeta, por ejemplo), los tests de abajo pasarían vacíos."""
    modulos = _modulos_del_nucleo()
    assert len(modulos) >= 5, f"solo se encontraron {len(modulos)} módulos en {_NUCLEO}"


@pytest.mark.parametrize("archivo", _modulos_del_nucleo(), ids=lambda p: p.name)
def test_nucleo_sin_acoplamiento_al_borde(archivo: Path):
    """INV-13: ningún módulo de seitt_core/ importa el borde neuronal ni el web."""
    importados = _imports_de(archivo)
    infractores = importados & _PROHIBIDOS

    assert not infractores, (
        f"{archivo.relative_to(_NUCLEO.parent)} importa {sorted(infractores)}. "
        f"seitt_core/ no puede depender del borde neuronal ni del web (INV-13): "
        f"esas dependencias van detrás de los Protocol de seitt_core/ports/, "
        f"implementadas por adaptadores que viven fuera del núcleo."
    )


def test_nucleo_no_importa_la_capa_de_aplicacion():
    """La dependencia es app/ -> seitt_core/, nunca al revés."""
    infractores = [
        archivo.relative_to(_NUCLEO.parent)
        for archivo in _modulos_del_nucleo()
        if "app" in _imports_de(archivo)
    ]
    assert not infractores, (
        f"módulos de seitt_core/ que importan app/: {infractores}. "
        f"El núcleo no puede depender de la capa de presentación."
    )


def test_ports_declara_los_dos_protocolos():
    """La frontera existe como contrato, no solo como ausencia de imports."""
    from seitt_core.ports import ExtractionPort, NarrationPort

    assert hasattr(NarrationPort, "narrate")
    assert hasattr(ExtractionPort, "extract")


def test_adaptador_estatico_satisface_el_puerto():
    """El camino simbólico cumple NarrationPort sin ningún módulo neuronal:
    es la contracara positiva de INV-13 — no solo 'no importa MedGemma',
    sino 'ya funciona completo sin él'."""
    from seitt_core.adapters import StaticNarrationAdapter
    from seitt_core.ports import NarrationPort

    assert isinstance(StaticNarrationAdapter(), NarrationPort)
