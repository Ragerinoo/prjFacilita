"""Teste de propriedade do fallback do Pacote_Repasse (Req 10.2, 10.4).

Feature: tres-autoatendimento, Property 10: Pacote com falha do assistente continua válido

Para quaisquer campos determinísticos e qualquer resultado do Assistente_IA (erro, tempo
esgotado, resumo vazio ou com mais de 300 caracteres, sentimento ou próxima ação inválidos,
saída ausente ou saída válida), `montar_pacote` produz um Pacote que passa em
`validar_pacote`, preserva todos os campos determinísticos e usa os textos de fallback
se, e somente se, a saída do assistente é inválida.

**Validates: Requirements 10.2, 10.4**
"""

from __future__ import annotations

import string

from hypothesis import given
from hypothesis import strategies as st

from dominio.pacote import (
    NAO_INFORMADO,
    PROXIMA_ACAO_FALLBACK,
    RESUMO_FALLBACK,
    SENTIMENTO_FALLBACK,
    Anexo,
    CamposDeterministicos,
    ItemJaTentado,
    SaidaAssistente,
    montar_pacote,
    pacote_para_dict,
    validar_pacote,
)

# --- Texto: unicode sem surrogates isolados (não são UTF-8 válido) ----------------------------
_caractere = st.one_of(
    st.characters(blacklist_categories=("Cs",)),
    st.sampled_from(list("áéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇ") + ["😀", "🔥", "☕", "💧"]),
)


def _texto(min_size: int, max_size: int) -> st.SearchStrategy[str]:
    return st.text(alphabet=_caractere, min_size=min_size, max_size=max_size)


def _texto_com_conteudo(max_size: int) -> st.SearchStrategy[str]:
    """Texto com 1..max_size caracteres e ao menos um caractere não-espaço."""
    return _texto(1, max_size).filter(lambda s: bool(s.strip()))


# --- Campos determinísticos ------------------------------------------------------------------
_ALFABETO_ULID = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_CATEGORIAS = [
    "nao_liga",
    "luz_vermelha_fixa",
    "alerta_vermelho_piscando",
    "teclas_e_sensor_vermelho_piscando",
    "luz_amarela",
    "nao_extrai",
    "bebida_aguada",
    "bebida_fria",
    "alavanca_travada",
    "vazamento",
    "nao_puxa_agua",
    "bico_entupido",
    "alavanca_nao_fecha_com_capsula",
    "outro",
]
_CANAIS = [
    "ligação imediata",
    "chat ou ligação, à escolha do Consumidor",
    "chat assíncrono",
]

campos_deterministicos = st.builds(
    CamposDeterministicos,
    numero_chamado=st.text(alphabet=_ALFABETO_ULID, min_size=10, max_size=10).map(
        lambda s: f"TRES-{s}"
    ),
    modelo=_texto(1, 80),
    # None e "" significam "ausente" (Req 10.9).
    numero_serie=st.one_of(
        st.none(),
        st.just(""),
        st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=30),
    ),
    origem=st.sampled_from(["qr", "busca"]),
    categoria=st.sampled_from(_CATEGORIAS),
    classificacao=st.sampled_from(["provável defeito", "provável uso"]),
    prioridade=st.sampled_from(["P1", "P2", "P3"]),
    canal_recomendado=st.sampled_from(_CANAIS),
    ja_tentado=st.lists(
        st.builds(
            ItemJaTentado,
            passo=_texto(1, 200),
            camada=st.sampled_from(["guia", "ia"]),
            resultado=st.sampled_from(["sim", "não", "sem resposta"]),
        ),
        max_size=10,
    ).map(tuple),
    anexos=st.lists(
        st.builds(Anexo, chave=_texto(1, 60), mime=st.sampled_from(["image/jpeg", "image/png"])),
        max_size=3,
    ).map(tuple),
)

# --- Resultados do assistente ----------------------------------------------------------------
_SENTIMENTOS = ["neutro", "frustração moderada", "frustração alta"]

_resumo_valido = _texto_com_conteudo(300)
_resumo_invalido = st.one_of(
    st.none(),
    st.just(""),
    st.text(alphabet=" \t\n", min_size=1, max_size=20),
    _texto(301, 400),
)
_sentimento_valido = st.sampled_from(_SENTIMENTOS)
_sentimento_invalido = st.one_of(
    st.none(),
    st.just(""),
    st.just("Neutro"),
    st.just("frustração extrema"),
    _texto(1, 30).filter(lambda s: s not in _SENTIMENTOS),
)
_acao_valida = _texto_com_conteudo(200)
_acao_invalida = st.one_of(
    st.none(),
    st.just(""),
    st.text(alphabet=" \t\n", min_size=1, max_size=20),
    _texto(201, 300),
)

_saida_valida = st.builds(
    SaidaAssistente,
    resumo=_resumo_valido,
    sentimento=_sentimento_valido,
    proxima_acao=_acao_valida,
)
# Erro e tempo esgotado invalidam a saída mesmo quando os campos de texto são válidos.
_saida_com_falha = st.builds(
    SaidaAssistente,
    resumo=st.one_of(st.none(), _resumo_valido),
    sentimento=st.one_of(st.none(), _sentimento_valido),
    proxima_acao=st.one_of(st.none(), _acao_valida),
    erro=st.booleans(),
    tempo_esgotado=st.booleans(),
).filter(lambda s: s.erro or s.tempo_esgotado)
# Ao menos um dos três campos de IA é inválido (os demais podem ser válidos ou inválidos).
_saida_campo_invalido = st.builds(
    SaidaAssistente,
    resumo=st.one_of(_resumo_valido, _resumo_invalido),
    sentimento=st.one_of(_sentimento_valido, _sentimento_invalido),
    proxima_acao=st.one_of(_acao_valida, _acao_invalida),
).filter(lambda s: not _oraculo_valida(s))

saidas_assistente = st.one_of(
    st.none(),
    _saida_valida,
    _saida_com_falha,
    _saida_campo_invalido,
)


def _oraculo_valida(s: SaidaAssistente | None) -> bool:
    """Regra do Req 10.3/10.4 escrita de forma independente da implementação."""
    if s is None or s.erro or s.tempo_esgotado:
        return False
    if s.resumo is None or s.resumo.strip() == "" or len(s.resumo) > 300:
        return False
    if s.sentimento not in _SENTIMENTOS:
        return False
    return not (s.proxima_acao is None or s.proxima_acao.strip() == "" or len(s.proxima_acao) > 200)


@given(det=campos_deterministicos, saida=saidas_assistente)
def test_pacote_com_falha_do_assistente_continua_valido(
    det: CamposDeterministicos, saida: SaidaAssistente | None
) -> None:
    # Feature: tres-autoatendimento, Property 10: Pacote com falha do assistente continua válido
    pacote = montar_pacote(det, saida)

    # O Pacote é sempre válido perante o esquema versão 1 (Req 10.4).
    assert validar_pacote(pacote_para_dict(pacote)) == []

    # Campos determinísticos preservados (Req 10.2); série ausente vira "não informado".
    assert pacote.numero_chamado == det.numero_chamado
    assert pacote.modelo == det.modelo
    assert pacote.numero_serie == (det.numero_serie or NAO_INFORMADO)
    assert pacote.origem == det.origem
    assert pacote.categoria == det.categoria
    assert pacote.classificacao == det.classificacao
    assert pacote.prioridade == det.prioridade
    assert pacote.canal_recomendado == det.canal_recomendado
    assert pacote.ja_tentado == det.ja_tentado
    assert pacote.anexos == det.anexos

    # Fallback se, e somente se, a saída do assistente é inválida (Req 10.4).
    if _oraculo_valida(saida):
        assert saida is not None
        assert pacote.resumo == saida.resumo
        assert pacote.sentimento == saida.sentimento
        assert pacote.proxima_acao == saida.proxima_acao
    else:
        assert pacote.resumo == RESUMO_FALLBACK
        assert pacote.sentimento == SENTIMENTO_FALLBACK
        assert pacote.proxima_acao == PROXIMA_ACAO_FALLBACK
