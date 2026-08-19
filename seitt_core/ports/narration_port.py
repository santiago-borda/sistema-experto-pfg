"""narration_port.py — Puerto post-analítico de narración.

Traduce un `InferenceVerdict` ya decidido a lenguaje natural. El puerto
existe para que la fase post-analítica sea sustituible sin tocar el
núcleo: hoy lo satisface un adaptador simbólico
(`seitt_core.adapters.static_narration`), mañana puede satisfacerlo uno
que delegue en MedGemma.

Frontera (Consigna 5): un `NarrationPort` recibe el veredicto **ya
resuelto** y devuelve texto. No puede alterar la decisión clínica porque
no tiene por dónde: su firma no devuelve disposiciones, ni reglas, ni
hechos — solo un `str`. La restricción está en el tipo, no en la
convención.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain import InferenceVerdict


@runtime_checkable
class NarrationPort(Protocol):
    """Contrato de la fase post-analítica de traducción a lenguaje natural."""

    def narrate(self, verdict: InferenceVerdict) -> str:
        """Redacta el veredicto en prosa legible para el bioquímico.

        Args:
            verdict: veredicto ya resuelto por el motor simbólico, con
                `triggered_rules` y `explanation_log` completos.

        Returns:
            Texto narrativo. Nunca None: si no hay nada que agregar a la
            traza simbólica, se devuelve esa traza formateada.
        """
        ...
