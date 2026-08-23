"""static_narration.py — Adaptador simbólico de `NarrationPort`.

**Es el adaptador POR DEFECTO, no un fallback.** La distinción no es
retórica: el camino simbólico ya produce una explicación correcta,
completa y auditable — `explanation_log` es la secuencia ordenada de
plantillas renderizadas de cada regla disparada, que es exactamente lo
que exige la trazabilidad de la Res. 1507/2015. MedGemma, cuando exista
su adaptador, será una **mejora opcional encima** de esto: redactará más
fluido, pero no agregará información que no esté ya acá.

Esa asimetría es INV-13 hecha código. Si este adaptador fuera un
"fallback para cuando el LLM no responde", el sistema sería un wrapper
con un plan B; siendo el default, el módulo neuronal es prescindible por
construcción.

No re-invoca `explicador.construir_explanation_log()` ni
`resolver_pending_action()`: ambos ya corrieron dentro de
`expert_system.evaluar_caso()` y sus resultados vienen materializados en
el `InferenceVerdict`. Este adaptador solo proyecta lo que el veredicto
ya trae — de hecho no podría reinvocarlos, porque esas funciones reciben
el `InferenceResult` interno del motor, que acá no está disponible.
"""

from __future__ import annotations

from ..domain import InferenceVerdict, UnitDisposition

_ENCABEZADO_POR_DISPOSICION = {
    UnitDisposition.APTA: "Unidad APTA para transfusión.",
    UnitDisposition.DESCARTE: "Unidad DESCARTADA.",
    UnitDisposition.CUARENTENA: "Unidad en CUARENTENA por rechazo técnico.",
}


class StaticNarrationAdapter:
    """Implementación determinística de `NarrationPort` (INV-13)."""

    def narrate(self, verdict: InferenceVerdict) -> str:
        """Proyecta el veredicto a prosa, sin agregar ni inferir nada.

        Cubre las dos formas de INV-15: terminal (con disposición) y
        pendiente (con `pending_action`).
        """
        lineas: list[str] = []

        if verdict.final_unit_disposition is None:
            # Forma (ii) de INV-15: el ciclo no alcanzó una regla terminal.
            lineas.append(
                "Evaluación NO CONCLUIDA: se requiere una acción antes de poder "
                "emitir un veredicto."
            )
            if verdict.pending_action:
                lineas.append(f"Acción requerida: {verdict.pending_action}")
        else:
            lineas.append(
                _ENCABEZADO_POR_DISPOSICION.get(
                    verdict.final_unit_disposition,
                    f"Disposición de unidad: {verdict.final_unit_disposition.value}.",
                )
            )
            if verdict.final_donor_disposition is not None:
                lineas.append(f"Disposición del donante: {verdict.final_donor_disposition.value}.")
            else:
                # Solo Cuarentena admite donante sin resolver (INV-07): la
                # muestra se rechaza técnicamente y al donante todavía no
                # se lo evaluó. Decirlo explícitamente evita que se lea
                # como un dato faltante.
                lineas.append(
                    "Disposición del donante: no evaluada (la muestra se rechazó "
                    "por criterio técnico, sin llegar a valorar al donante)."
                )

        if verdict.epidemiological_status:
            lineas.append(f"Estado epidemiológico: {verdict.epidemiological_status}.")

        lineas.append("")
        lineas.append("Fundamento (trazabilidad regla por regla):")
        lineas.extend(f"  {i}. {paso}" for i, paso in enumerate(verdict.explanation_log, 1))

        lineas.append("")
        lineas.append(
            f"Reglas aplicadas: {', '.join(verdict.triggered_rules)} "
            f"— motor {verdict.engine_version}."
        )

        return "\n".join(lineas)
