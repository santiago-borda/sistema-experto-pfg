"""main.py — Aplicación FastAPI del SE-ITT.

Adaptador HTTP sobre `expert_system.evaluar_caso()`. No contiene ni una
regla clínica: traduce JSON a los kwargs del núcleo, y el veredicto de
vuelta a JSON. Toda decisión sigue viviendo en la KB declarativa.

La narración se obtiene por el `NarrationPort` inyectado, nunca llamando
a `explicador.py` en directo. Cuando exista el adaptador MedGemma se
cambia la inyección en `_narrador()` y no se toca nada más — que es
exactamente lo que INV-13 promete.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from seitt_core.adapters import StaticNarrationAdapter
from seitt_core.domain import (
    NAT_APPLICABLE_MARKERS,
    SEITTDomainError,
    DomainInvariantViolation,
    Marker,
    UnitDisposition,
    certainty_to_percent,
)
from seitt_core.expert_system import evaluar_caso
from seitt_core.ports import NarrationPort

from .schemas import (
    ErrorInvariante,
    EvaluacionRequest,
    EvaluacionResponse,
    MarcadorInfo,
)

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(
    title="SE-ITT — Sistema Experto para Infecciones Transmisibles por Transfusión",
    description=(
        "CDSS basado en lógica difusa y reglas declarativas. Apoya, no reemplaza, "
        "al bioquímico responsable."
    ),
    version="0.1.0",
)


def _narrador() -> NarrationPort:
    """Punto único de inyección del puerto de narración.

    Hoy devuelve el adaptador simbólico, que es el DEFAULT (no un
    fallback): el camino simbólico ya produce una explicación completa.
    Un adaptador MedGemma se enchufa acá, y solo acá.
    """
    return StaticNarrationAdapter()


@app.exception_handler(SEITTDomainError)
async def _manejar_error_de_dominio(_: Request, exc: SEITTDomainError) -> JSONResponse:
    """Mapea toda violación de invariante a un 400 con cuerpo estructurado.

    Explícito, no genérico (Consigna 2): sin este handler una entrada que
    viola INV-08 saldría como 500 con traceback, que para el usuario del
    CDSS no es accionable y para el sistema es una fuga de internals.
    """
    invariant_id = getattr(exc, "invariant_id", "SEITT-DOMAIN-ERROR")
    detail = getattr(exc, "detail", str(exc))
    return JSONResponse(
        status_code=400,
        content=ErrorInvariante(invariant_id=invariant_id, detail=detail).model_dump(),
    )


@app.get("/api/marcadores", response_model=list[MarcadorInfo])
def listar_marcadores() -> list[MarcadorInfo]:
    """Aplicabilidad de ensayos por marcador (INV-08 e INV-05 extendido).

    La fuente es el propio dominio (`NAT_APPLICABLE_MARKERS`,
    `Marker.SIFILIS`), no una lista repetida en el frontend: si mañana se
    agrega un marcador NAT-aplicable, la UI se entera sola.
    """
    return [
        MarcadorInfo(
            marcador=m,
            nat_aplicable=m in NAT_APPLICABLE_MARKERS,
            sifilis_aplicable=(m == Marker.SIFILIS),
        )
        for m in Marker
    ]


@app.post(
    "/api/evaluar",
    response_model=EvaluacionResponse,
    responses={400: {"model": ErrorInvariante}},
)
def evaluar(payload: EvaluacionRequest) -> EvaluacionResponse:
    """Evalúa un marcador de una muestra y devuelve el veredicto completo.

    Una violación de invariante sale como 400 vía el exception handler; un
    cuerpo malformado sale como 422, tal cual lo produce FastAPI.
    """
    verdict = evaluar_caso(
        sample_id=payload.sample_id,
        calidad_muestra=payload.calidad_muestra.value,
        marcador=payload.marcador.value,
        riesgo=payload.riesgo,
        sco_inicial_valor=payload.sco_inicial_valor,
        sco_repeticion_valor=payload.sco_repeticion_valor,
        nat=payload.nat.value if payload.nat is not None else None,
        vdrl=payload.vdrl.value if payload.vdrl is not None else None,
        clia=payload.clia.value if payload.clia is not None else None,
    )

    # La certeza se convierte acá, con la única función permitida
    # (certainty_to_percent), para que el frontend no haga aritmética sobre
    # un valor clínico. Ver domain_model.md §2.
    certeza_pct = (
        certainty_to_percent(verdict.certainty_index)
        if verdict.certainty_index is not None
        else None
    )

    # Ante interferencia física, expert_system sintetiza un S/CO centinela
    # (0.0) para que R20 pueda cortar el ciclo, y ese centinela produce una
    # certeza de 100% que NO corresponde a ninguna lectura real: nadie leyó
    # el S/CO de una muestra hemolizada. Se marca como no significativa
    # para que el frontend no muestre el número más confiado del sistema
    # justo donde no hubo medición.
    certeza_significativa = verdict.final_unit_disposition != UnitDisposition.CUARENTENA

    dump = verdict.model_dump(mode="json")
    return EvaluacionResponse(
        sample_id=dump["sample_id"],
        final_unit_disposition=verdict.final_unit_disposition,
        final_donor_disposition=verdict.final_donor_disposition,
        pending_action=verdict.pending_action,
        epidemiological_status=verdict.epidemiological_status,
        triggered_rules=verdict.triggered_rules,
        explanation_log=verdict.explanation_log,
        certainty_index=verdict.certainty_index,
        certeza_porcentaje=certeza_pct,
        certeza_es_significativa=certeza_significativa,
        timestamp=dump["timestamp"],
        engine_version=verdict.engine_version,
        narrative=_narrador().narrate(verdict),
    )


class _EstaticosSinCache(StaticFiles):
    """StaticFiles que fuerza revalidación en cada carga.

    Starlette envía `ETag` y `Last-Modified` pero NO `Cache-Control`. Sin
    esa cabecera el navegador aplica *caché heurística*: decide por su
    cuenta cuánto tiempo considerar fresco el archivo (habitualmente una
    fracción del tiempo desde su última modificación) y lo sirve desde
    disco **sin preguntarle al servidor**. El síntoma es desconcertante:
    el HTML se actualiza pero el JS no, así que la página se ve nueva y
    se comporta como la vieja — un botón nuevo queda sin su listener.

    `no-cache` no significa "no cachear": significa "cachealo, pero
    revalidá siempre antes de usarlo". El navegador sigue mandando
    `If-None-Match` y el servidor sigue respondiendo 304, así que no se
    retransmite nada — solo se elimina la ventana en la que el navegador
    decide por su cuenta.

    Importa para la defensa del PFG: durante una demo en vivo, un cambio
    que no aparece por caché del navegador es indistinguible de un bug.
    """

    def file_response(self, *args, **kwargs):  # type: ignore[override]
        respuesta = super().file_response(*args, **kwargs)
        respuesta.headers["Cache-Control"] = "no-cache"
        return respuesta


# El frontend estático se monta al final para que no tape las rutas /api/*.
if _WEB_DIR.is_dir():
    app.mount("/", _EstaticosSinCache(directory=str(_WEB_DIR), html=True), name="web")
