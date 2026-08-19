"""extraction_port.py — Puerto pre-analítico de extracción.

Contrato de la capa que convierte un reporte no estructurado (texto libre,
PDF, HL7) en hechos validables. Es la única vía por la que un módulo
neuronal puede entrar al sistema.

Estado: **contrato declarado, sin adaptador**. En este paso (Fase 3, Paso
3A) el puerto se define para fijar la forma de la frontera; la extracción
en sí es el frente de integración siguiente. Que exista el Protocol sin
implementación es deliberado, no una omisión: es lo que permite escribir y
verificar el resto de la arquitectura (INV-13) antes de que haya un solo
byte de MedGemma en el repo.

Frontera (Consigna 5): un `ExtractionPort` produce un `ExtractionEnvelope`,
nunca un veredicto. Lo que emita debe validar contra
`spec/schemas/extraction_envelope.schema.json` y, a partir de ahí, contra
`sample_input.schema.json` — el LLM solo puede proponer hechos de entrada,
y esos hechos pasan por los mismos invariantes de dominio que los de un
analizador químico directo.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# TODO(frente de integración MedGemma): `ExtractionEnvelope` todavía no
# existe como modelo Pydantic — hoy solo está el JSON Schema
# (spec/schemas/extraction_envelope.schema.json, registrado en el bloque
# [1] de validate_spec.py). Cuando se materialice en spec/contracts.py,
# reemplazar esta forward reference por el import real y agregar los
# round-trips schema<->contracts correspondientes, igual que se hizo con
# SampleInputFacts e InferenceVerdict en el Paso 1.


@runtime_checkable
class ExtractionPort(Protocol):
    """Contrato de la fase pre-analítica de extracción NLP."""

    def extract(self, raw: bytes | str) -> "ExtractionEnvelope":  # noqa: F821
        """Convierte un reporte no estructurado en hechos candidatos.

        Args:
            raw: contenido crudo del reporte (bytes para PDF/binario, str
                para texto plano o HL7).

        Returns:
            Un `ExtractionEnvelope` con los campos extraídos y su
            confianza por campo. La confianza es metadato de auditoría:
            por INV-09 no puede ser antecedente de ninguna regla ni
            combinarse aritméticamente con la certeza difusa.
        """
        ...
