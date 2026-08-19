"""seitt_core.adapters — Implementaciones simbólicas de los puertos.

Contienen únicamente adaptadores que no cruzan la frontera neuronal: son
código determinístico del propio núcleo, sin dependencias externas. Los
adaptadores que involucren MedGemma viven fuera de `seitt_core/` por
INV-13.
"""

from .static_narration import StaticNarrationAdapter

__all__ = ["StaticNarrationAdapter"]
