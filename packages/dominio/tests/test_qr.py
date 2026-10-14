"""Testes de unidade de `interpretar_qr` (Req 1.2, 1.4, 1.5, 1.6)."""
from __future__ import annotations

import pytest

from dominio.qr import NAO_LEGIVEL, InterpretacaoQR, interpretar_qr


@pytest.mark.parametrize(
    "url, esperado",
    [
        ("/m/tres-passione?s=ABC123", InterpretacaoQR(True, "tres-passione", "ABC123")),
        (
            "https://tres.exemplo.com.br/m/tres-passione?s=ABC123",
            InterpretacaoQR(True, "tres-passione", "ABC123"),
        ),
        ("/m/tres-passione", InterpretacaoQR(True, "tres-passione", None)),
        ("/m/tres-passione/", InterpretacaoQR(True, "tres-passione", None)),
        ("/m/tres-passione?s=" + "A" * 30, InterpretacaoQR(True, "tres-passione", "A" * 30)),
        ("/m/tres-passione?s=ABC#frag", InterpretacaoQR(True, "tres-passione", "ABC")),
    ],
)
def test_url_valida(url: str, esperado: InterpretacaoQR) -> None:
    assert interpretar_qr(url) == esperado


@pytest.mark.parametrize(
    "query",
    ["s=", "s=" + "A" * 31, "s=AB-12", "s=AB%2012", "s=%C3%A9", "x=ABC", "s=a%00b"],
)
def test_serie_invalida_e_descartada_sem_invalidar_o_modelo(query: str) -> None:
    assert interpretar_qr(f"/m/tres-passione?{query}") == InterpretacaoQR(
        True, "tres-passione", None
    )


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "tres-passione",
        "/",
        "/m",
        "/m/",
        "/m//",
        "/m/Tres-Passione",
        "/m/tres_passione",
        "/m/-tres",
        "/m/tres-",
        "/m/tres--passione",
        "/m/tres passione",
        "/m/tres-passione/p/1",
        "/m/" + "a" * 65,
        "/x/tres-passione?s=ABC",
        "http://[invalido/m/tres-passione",
        "/m/tres\npassione",
        "/m/%74res",
    ],
)
def test_url_ilegivel(url: str) -> None:
    assert interpretar_qr(url) == NAO_LEGIVEL


@pytest.mark.parametrize("entrada", [None, 123, b"/m/tres-passione", ["/m/x"], object()])
def test_entrada_que_nao_e_texto_nao_lanca_excecao(entrada: object) -> None:
    assert interpretar_qr(entrada) == NAO_LEGIVEL
