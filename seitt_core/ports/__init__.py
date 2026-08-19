"""seitt_core.ports — Puertos de la frontera neuro-simbólica (INV-13).

Inversión de dependencias: el núcleo declara acá los *contratos* que un
módulo del borde debe satisfacer, como `typing.Protocol`, y nunca importa
una implementación concreta. Los adaptadores viven afuera del núcleo
(`seitt_core/adapters/` para los simbólicos, el borde neuronal para los
que involucren MedGemma).

INV-13 — Independencia de disponibilidad respecto del módulo neuronal: la
capacidad del sistema de emitir un veredicto clínico es independiente de
la disponibilidad, latencia o corrección de MedGemma. Toda funcionalidad
del módulo neuronal es una mejora opcional sobre un camino simbólico que
ya es completo y correcto. Verificado empíricamente por análisis AST en
`tests/test_architecture.py`, no afirmado en prosa.
"""

from .extraction_port import ExtractionPort
from .narration_port import NarrationPort

__all__ = ["ExtractionPort", "NarrationPort"]
