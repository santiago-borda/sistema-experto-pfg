"""test_fuzzy_engine.py -- fija fuzzificar_sco() contra los valores de
referencia del docstring de fuzzy_engine.py legado (__main__), para que
la fórmula corregida en domain_model.md §2 quede versionada como test,
no solo como comentario."""

import pytest

from seitt_core.domain import SCOLabel
from seitt_core.fuzzy_engine import fuzzificar_sco


@pytest.mark.parametrize(
    "sco_valor,label_esperado,certeza_esperada",
    [
        (0.2, SCOLabel.NO_REACTIVO, 77.78),
        (0.9, SCOLabel.ZONA_GRIS, 100.0),   # borde inferior: certeza máxima
        (1.0, SCOLabel.ZONA_GRIS, 50.0),    # centro de la banda
        (1.1, SCOLabel.ZONA_GRIS, 0.0),     # borde superior: certeza mínima
        (4.5, SCOLabel.REACTIVO, 68.0),
    ],
)
def test_fuzzificar_sco_valores_referencia(sco_valor, label_esperado, certeza_esperada):
    label, certeza = fuzzificar_sco(sco_valor)
    assert label == label_esperado
    assert certeza == pytest.approx(certeza_esperada, abs=0.01)


def test_fuzzificar_sco_negativo_rechazado():
    with pytest.raises(ValueError):
        fuzzificar_sco(-0.1)
