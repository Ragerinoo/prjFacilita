"""Testes unitários dos validadores de entrada (tarefa 5.1)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from dominio.validadores import (
    FUSO_BRASILIA,
    dados_pessoais_solicitados,
    validar_agendamento,
    validar_avaliacao,
    validar_cep,
    validar_email,
    validar_encerramento,
    validar_entrada_cache,
    validar_foto,
    validar_mensagem_atendente,
    validar_mensagem_consumidor,
    validar_nome,
    validar_telefone,
)

MB = 1024 * 1024


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("11987654321", True),
        ("(11) 98765-4321", True),
        ("11 3456-7890", True),
        ("1198765432", True),
        ("119876543", False),  # 9 dígitos
        ("119876543210", False),  # 12 dígitos
        ("11a87654321", False),
        ("+55 11 98765-4321", False),
        ("١١٩٨٧٦٥٤٣٢١", False),  # dígitos não ASCII
        ("", False),
    ],
)
def test_telefone(valor: str, esperado: bool) -> None:
    assert validar_telefone(valor) is esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("01310-100", True),
        ("01310100", True),
        (" 01310 100 ", True),
        ("0131010", False),
        ("013101000", False),
        ("01310.100", False),
        ("abcdefgh", False),
    ],
)
def test_cep(valor: str, esperado: bool) -> None:
    assert validar_cep(valor) is esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("Ana", True),
        ("  Ana Souza  ", True),
        ("Jo", True),
        ("A", False),
        ("", False),
        ("     ", False),
        (" A ", False),
        ("a" * 100, True),
        ("a" * 101, False),
        ("Ana\nSouza", False),
        ("Ana\x00", False),
    ],
)
def test_nome(valor: str, esperado: bool) -> None:
    assert validar_nome(valor) is esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("ana@exemplo.com", True),
        ("ana.souza+tres@mail.exemplo.com.br", True),
        ("", False),
        ("   ", False),
        ("ana.exemplo.com", False),
        ("ana@exemplo", False),
        ("ana@@exemplo.com", False),
        ("ana @exemplo.com", False),
        ("ana@exem plo.com", False),
        ("ana@.com", False),
        ("ana@exemplo..com", False),
        ("a" * 250 + "@b.co", False),
    ],
)
def test_email(valor: str, esperado: bool) -> None:
    assert validar_email(valor) is esperado


@pytest.mark.parametrize(
    ("mime", "tamanho", "anexadas", "aceita"),
    [
        ("image/jpeg", 1, 0, True),
        ("image/png", 5 * MB, 2, True),
        ("image/png", 5 * MB + 1, 0, False),
        ("image/gif", 10, 0, False),
        ("application/pdf", 10, 0, False),
        ("image/jpeg", 10, 3, False),
    ],
)
def test_foto(mime: str, tamanho: int, anexadas: int, aceita: bool) -> None:
    resultado = validar_foto(mime, tamanho, anexadas)
    assert resultado.aceita is aceita
    assert (resultado.motivo is None) is aceita


@pytest.mark.parametrize(
    ("texto", "aceita"),
    [
        ("oi", True),
        ("a" * 1000, True),
        ("a" * 1001, False),
        ("", False),
        ("   \n\t ", False),
    ],
)
def test_mensagem_consumidor(texto: str, aceita: bool) -> None:
    assert validar_mensagem_consumidor(texto).aceita is aceita


@pytest.mark.parametrize(
    ("prioridade", "informados", "esperado"),
    [
        ("P1", [], ("telefone",)),
        ("P1", ["telefone"], ()),
        ("P2", [], ("telefone", "cep")),
        ("P2", ["telefone"], ("cep",)),
        ("P2", ["cep"], ("telefone",)),
        ("P2", ["telefone", "cep"], ()),
        ("P3", [], ()),
        ("P3", ["cep"], ()),
    ],
)
def test_dados_pessoais_solicitados(prioridade, informados, esperado) -> None:
    assert dados_pessoais_solicitados(prioridade, informados) == esperado


def test_dados_pessoais_prioridade_desconhecida() -> None:
    with pytest.raises(ValueError):
        dados_pessoais_solicitados("P9", [])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("nota", "comentario", "aceita"),
    [
        (1, None, True),
        (5, "", True),
        (3, "x" * 500, True),
        (3, "x" * 501, False),
        (0, None, False),
        (6, None, False),
        (True, None, False),
        (2.0, None, False),
    ],
)
def test_avaliacao(nota, comentario, aceita) -> None:
    assert validar_avaliacao(nota, comentario).aceita is aceita


def test_avaliacao_repetida_na_mesma_jornada_e_recusada() -> None:
    assert not validar_avaliacao(5, None, ja_avaliada=True).aceita


@pytest.mark.parametrize(
    ("texto", "confirmada", "aceita"),
    [
        ("Olá", True, True),
        ("a" * 2000, True, True),
        ("a" * 2001, True, False),
        ("", True, False),
        ("Olá", False, False),
    ],
)
def test_mensagem_atendente(texto: str, confirmada: bool, aceita: bool) -> None:
    assert validar_mensagem_atendente(texto, confirmada).aceita is aceita


AGORA = datetime(2025, 3, 10, 12, 0, tzinfo=FUSO_BRASILIA)


def test_agendamento_futuro_dentro_do_limite() -> None:
    assert validar_agendamento(date(2025, 3, 10), time(12, 1), AGORA).aceita
    assert validar_agendamento(date(2025, 4, 9), time(12, 0), AGORA).aceita  # exatamente 30 dias


def test_agendamento_passado_ou_agora_e_rejeitado() -> None:
    assert not validar_agendamento(date(2025, 3, 10), time(12, 0), AGORA).aceita
    assert not validar_agendamento(date(2025, 3, 9), time(18, 0), AGORA).aceita


def test_agendamento_alem_de_30_dias_e_rejeitado() -> None:
    assert not validar_agendamento(date(2025, 4, 9), time(12, 1), AGORA).aceita


def test_agendamento_incompleto_aponta_o_campo() -> None:
    campos = {e.campo for e in validar_agendamento(None, None, AGORA).erros}
    assert campos == {"data", "hora"}
    assert [e.campo for e in validar_agendamento(date(2025, 3, 11), None, AGORA).erros] == ["hora"]


def test_agendamento_interpreta_data_e_hora_no_fuso_de_brasilia() -> None:
    # 12:00 UTC = 09:00 em Brasília. 09:30 de Brasília ainda é futuro; 08:30 já passou.
    agora_utc = datetime(2025, 3, 10, 12, 0, tzinfo=UTC)
    assert validar_agendamento(date(2025, 3, 10), time(9, 30), agora_utc).aceita
    assert not validar_agendamento(date(2025, 3, 10), time(8, 30), agora_utc).aceita


def test_fuso_de_brasilia_e_utc_menos_3() -> None:
    assert datetime(2025, 3, 10, 12, 0, tzinfo=FUSO_BRASILIA).utcoffset() == timedelta(hours=-3)


def test_encerramento() -> None:
    assert validar_encerramento("falso defeito", "instrução do manual", "Limpou o bico").aceita
    assert validar_encerramento("defeito real", "outra", "x" * 500).aceita
    assert not validar_encerramento(None, "outra", "ok").aceita
    assert not validar_encerramento("defeito real", "outra", "").aceita
    assert not validar_encerramento("defeito real", "outra", "x" * 501).aceita
    campos = {e.campo for e in validar_encerramento(None, None, "").erros}
    assert campos == {"desfecho", "tipo_solucao", "descricao_solucao"}


@pytest.mark.parametrize(
    ("pergunta", "resposta", "aceita"),
    [
        ("p", "r", True),
        ("p" * 300, "r" * 1000, True),
        ("p" * 301, "r", False),
        ("p", "r" * 1001, False),
        ("", "r", False),
        ("p", "", False),
    ],
)
def test_entrada_cache(pergunta: str, resposta: str, aceita: bool) -> None:
    assert validar_entrada_cache(pergunta, resposta).aceita is aceita
