"""Teste de propriedade do Cache_Respostas: só entram respostas aprovadas.

Feature: tres-autoatendimento, Property 15: O cache só guarda respostas aprovadas e
nunca altera entradas existentes

**Validates: Requirements 7.6, 7.7, 16.3, 16.8**
"""

from __future__ import annotations

from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st

from dominio.cache import aceitar_insercao_cache, chave_cache
from dominio.tipos import EntradaCache, StatusInsercao

# Poucas perguntas/modelos para forçar colisões de chave dentro de uma sequência.
_modelos = st.sampled_from(["modelo-a", "modelo-b"])
_perguntas = st.sampled_from(
    ["Como resetar a senha?", "como resetar a senha", "Qual o horário?", "Trocar plano!"]
)
_textos = st.text(min_size=1, max_size=30)
# Aprovador ausente, em branco ou válido.
_aprovadores = st.one_of(
    st.none(),
    st.sampled_from(["", " ", "\t\n"]),
    st.text(alphabet=st.characters(categories=("L", "N")), min_size=1, max_size=10),
)
_datas = st.datetimes(
    min_value=datetime(2020, 1, 1), max_value=datetime(2030, 1, 1), timezones=st.just(UTC)
)


@st.composite
def _tentativas(draw):
    entrada = EntradaCache(
        modelo_id=draw(_modelos),
        pergunta=draw(_perguntas),
        resposta=draw(_textos),
        aprovador_id=None,
        aprovado_em=draw(_datas),
    )
    return entrada, draw(_aprovadores)


def _tem_aprovador(aprovador_id: str | None) -> bool:
    return aprovador_id is not None and bool(aprovador_id.strip())


@given(st.lists(_tentativas(), max_size=30))
def test_cache_so_guarda_aprovadas_e_nao_altera_existentes(tentativas):
    cache: dict[str, EntradaCache] = {}
    rejeicoes: list[EntradaCache] = []

    for entrada, aprovador_id in tentativas:
        chave = chave_cache(entrada.modelo_id, entrada.pergunta)
        existente = cache.get(chave)
        antes = dict(cache)

        resultado = aceitar_insercao_cache(entrada, aprovador_id, existente)

        if not _tem_aprovador(aprovador_id):
            # Req 7.6/7.7: sem aprovador é rejeitada e o cache não muda.
            assert resultado.status is StatusInsercao.REJEITADA_SEM_APROVADOR
            assert not resultado.aceita
            assert resultado.entrada is existente
            rejeicoes.append(entrada)
        elif existente is not None:
            # Req 16.8: chave já existente mantém o conteúdo original.
            assert resultado.status is StatusInsercao.DUPLICADA
            assert not resultado.aceita
            assert resultado.entrada is existente
        else:
            # Req 16.3: aceita guarda modelo, aprovador e data de aprovação.
            assert resultado.status is StatusInsercao.ACEITA
            assert resultado.aceita
            assert resultado.entrada is not None
            assert resultado.entrada.modelo_id == entrada.modelo_id
            assert resultado.entrada.aprovador_id == aprovador_id
            assert resultado.entrada.aprovado_em == entrada.aprovado_em
            assert resultado.entrada.resposta == entrada.resposta
            cache[chave] = resultado.entrada

        # Entradas anteriores permanecem idênticas; só pode surgir a chave atual.
        for k, v in antes.items():
            assert cache[k] == v
        assert set(cache) - set(antes) <= {chave}

    # Todo o conteúdo do cache foi aprovado e traz modelo, aprovador e data.
    for entrada_cache in cache.values():
        assert _tem_aprovador(entrada_cache.aprovador_id)
        assert entrada_cache.modelo_id
        assert entrada_cache.aprovado_em is not None
