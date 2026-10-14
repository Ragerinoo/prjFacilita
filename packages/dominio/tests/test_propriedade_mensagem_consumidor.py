"""Teste de propriedade da validação da mensagem do Consumidor (Req 6.11).

Feature: tres-autoatendimento, Property 24: Validação da mensagem do Consumidor

Para qualquer string, a mensagem é aceita se, e somente se, tem de 1 a 1000 caracteres e não
é composta só de espaços em branco. O validador é puro: rejeitar uma mensagem não produz
nenhum efeito (a camada de API é quem decide não registrar evento na Jornada).

**Validates: Requirements 6.11**
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from dominio.validadores import MENSAGEM_CONSUMIDOR_MAX, validar_mensagem_consumidor

_BRANCOS = " \t\n\r\f\v\u00a0\u2003\u3000"

# Texto arbitrário (inclui surrogates excluídos por padrão) com tamanhos em torno dos limites.
_texto_qualquer = st.text(max_size=MENSAGEM_CONSUMIDOR_MAX + 50)
_so_brancos = st.text(alphabet=_BRANCOS, max_size=MENSAGEM_CONSUMIDOR_MAX + 50)
_com_conteudo = st.builds(
    lambda pre, c, pos: f"{pre}{c}{pos}",
    st.text(alphabet=_BRANCOS, max_size=20),
    st.characters(blacklist_categories=("Cs", "Z", "Cc")),
    st.text(max_size=20),
)
_no_limite = st.integers(MENSAGEM_CONSUMIDOR_MAX - 2, MENSAGEM_CONSUMIDOR_MAX + 2).map(
    lambda n: "a" * n
)


def _esperado(texto: str) -> bool:
    """Oráculo independente: 1 a 1000 caracteres e ao menos um caractere não-branco."""
    return 1 <= len(texto) <= MENSAGEM_CONSUMIDOR_MAX and any(not c.isspace() for c in texto)


@given(st.one_of(_texto_qualquer, _so_brancos, _com_conteudo, _no_limite))
def test_mensagem_aceita_sse_tamanho_valido_e_nao_so_brancos(texto: str) -> None:
    resultado = validar_mensagem_consumidor(texto)

    assert resultado.aceita is _esperado(texto)
    if resultado.aceita:
        assert resultado.erros == ()
    else:
        assert [e.campo for e in resultado.erros] == ["mensagem"]
        assert resultado.motivo


@given(_so_brancos)
def test_mensagem_so_de_brancos_e_sempre_rejeitada(texto: str) -> None:
    assert not validar_mensagem_consumidor(texto).aceita


@given(st.integers(min_value=MENSAGEM_CONSUMIDOR_MAX + 1, max_value=MENSAGEM_CONSUMIDOR_MAX + 500))
def test_mensagem_acima_do_limite_e_sempre_rejeitada(tamanho: int) -> None:
    assert not validar_mensagem_consumidor("a" * tamanho).aceita
