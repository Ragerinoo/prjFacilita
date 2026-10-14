"""Testes unitários do Cache_Respostas puro (Req 7.1, 7.2, 7.6, 7.7, 16.3, 16.8)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dominio.cache import aceitar_insercao_cache, chave_cache, normalizar_pergunta
from dominio.tipos import EntradaCache, StatusInsercao

AGORA = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)


def _entrada(resposta: str = "Resposta A", aprovador: str | None = None) -> EntradaCache:
    return EntradaCache(
        modelo_id="M1",
        pergunta="Por que a máquina não liga?",
        resposta=resposta,
        aprovador_id=aprovador,
        aprovado_em=AGORA,
    )


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("  Por QUE a Máquina NÃO liga?!  ", "por que a maquina nao liga"),
        ("água,   quente...\n\tfria", "agua quente fria"),
        ("Ação", "acao"),
        ("", ""),
        ("?!...", ""),
    ],
)
def test_normalizar_pergunta(bruto: str, esperado: str) -> None:
    assert normalizar_pergunta(bruto) == esperado


def test_normalizacao_e_idempotente_em_casos_unicode() -> None:
    for texto in ["İstanbul", "ᴬ b", "ﬁnal  Çá", "Straße"]:
        uma_vez = normalizar_pergunta(texto)
        assert normalizar_pergunta(uma_vez) == uma_vez


def test_chave_cache_formato_e_unificacao_de_variacoes() -> None:
    chave = chave_cache("M1", "Não liga?")
    modelo, _, digest = chave.partition("#")
    assert modelo == "M1"
    assert len(digest) == 64
    assert chave == chave_cache("M1", "  NAO   liga ")
    assert chave != chave_cache("M2", "Não liga?")
    assert chave != chave_cache("M1", "Liga?")


def test_insercao_sem_aprovador_e_rejeitada() -> None:
    for aprovador in (None, "", "   "):
        r = aceitar_insercao_cache(_entrada(), aprovador, None)
        assert r.status is StatusInsercao.REJEITADA_SEM_APROVADOR
        assert r.entrada is None
        assert not r.aceita


def test_rejeicao_sem_aprovador_mantem_entrada_existente() -> None:
    existente = _entrada("Original", "ana")
    r = aceitar_insercao_cache(_entrada("Nova"), None, existente)
    assert r.status is StatusInsercao.REJEITADA_SEM_APROVADOR
    assert r.entrada is existente


def test_insercao_aprovada_e_aceita_com_aprovador_registrado() -> None:
    r = aceitar_insercao_cache(_entrada(), "ana", None)
    assert r.aceita
    assert r.entrada is not None
    assert r.entrada.aprovador_id == "ana"
    assert r.entrada.modelo_id == "M1"
    assert r.entrada.aprovado_em == AGORA


def test_duplicata_mantem_entrada_existente() -> None:
    existente = _entrada("Original", "ana")
    r = aceitar_insercao_cache(_entrada("Nova"), "beto", existente)
    assert r.status is StatusInsercao.DUPLICADA
    assert r.entrada is existente
    assert r.entrada.resposta == "Original"
