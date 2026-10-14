"""Rotas do Painel_CS da tarefa 13.3: sugestão, mensagens, Ordem_Servico e agendamento."""
from __future__ import annotations

from datetime import timedelta

import pytest
from servicos import sugestao as mod_sugestao
from tests.test_rotas_cs_chamados import SENHA, T0, Cliente  # noqa: F401
from tests.test_rotas_cs_chamados import c, hash_senha  # noqa: F401


@pytest.fixture(autouse=True)
def _sem_agente():
    mod_sugestao.definir_agente(None)
    yield
    mod_sugestao.definir_agente(None)


def test_sugestao_local_ou_vazia_nunca_erro(c):
    n = c.escalar("J1")
    r, corpo = c.chamar("GET", f"/api/cs/chamados/{n}/sugestao")
    assert r["statusCode"] == 200
    assert corpo["sugestao"] and corpo["origem"] == "modelo_local"


def test_sugestao_falha_do_agente_devolve_campo_vazio(c):
    class Quebrado:
        def sugestao_atendente(self, pedido, *, timeout_s=None):
            raise TimeoutError("10s")

    mod_sugestao.definir_agente(Quebrado())
    n = c.escalar("J1")
    r, corpo = c.chamar("GET", f"/api/cs/chamados/{n}/sugestao")
    assert r["statusCode"] == 200
    assert corpo["sugestao"] is None and corpo["mensagem"] == "sugestão indisponível"


def test_sugestao_chamado_inexistente_404(c):
    assert c.chamar("GET", "/api/cs/chamados/TRES-X/sugestao")[0]["statusCode"] == 404


def test_mensagem_exige_confirmacao_e_grava(c):
    n = c.escalar("J1")
    c.app.repos.chamados.definir_resposta_nao_lida(n, True)
    r, corpo = c.chamar("POST", f"/api/cs/chamados/{n}/mensagens", {"texto": "Olá"})
    assert r["statusCode"] == 422 and c.app.repos.mensagens.listar(n) == []
    r, corpo = c.chamar(
        "POST", f"/api/cs/chamados/{n}/mensagens", {"texto": "Olá", "confirmada": True}
    )
    assert r["statusCode"] == 201 and corpo["autor"] == "atendente"
    assert [m.texto for m in c.app.repos.mensagens.listar(n)] == ["Olá"]
    assert c.app.repos.chamados.obter(n).resposta_nao_lida is False


@pytest.mark.parametrize("texto", ["", "   ", "x" * 2001])
def test_mensagem_invalida_422(c, texto):
    n = c.escalar("J1")
    r, _ = c.chamar(
        "POST", f"/api/cs/chamados/{n}/mensagens", {"texto": texto, "confirmada": True}
    )
    assert r["statusCode"] == 422 and c.app.repos.mensagens.listar(n) == []


def test_mensagem_de_outro_responsavel_409(c):
    n = c.escalar("J1")
    assert c.chamar("POST", f"/api/cs/chamados/{n}/assumir", quem="ana")[0]["statusCode"] == 200
    r, corpo = c.chamar(
        "POST", f"/api/cs/chamados/{n}/mensagens", {"texto": "oi", "confirmada": True}, quem="bia"
    )
    assert r["statusCode"] == 409 and corpo["erro"]["codigo"] == "outro_responsavel"


def test_ordem_servico_idempotente(c):
    n = c.escalar("J1")
    r1, a = c.chamar("POST", f"/api/cs/chamados/{n}/ordem-servico")
    r2, b = c.chamar("POST", f"/api/cs/chamados/{n}/ordem-servico")
    assert r1["statusCode"] == r2["statusCode"] == 200
    assert a["status"] == b["status"] == "aberta" and a["os_id"] == b["os_id"]
    assert b["criada_agora"] is False and b["confirmada_agora"] is False
    assert c.app.repos.chamados.obter(n).os_status == "ok"


def test_agendamento_valido_e_reagendar(c):
    n = c.escalar("J1")
    dia = (T0 + timedelta(days=2)).date().isoformat()
    r, corpo = c.chamar("POST", f"/api/cs/chamados/{n}/agendamento", {"data": dia, "hora": "14:30"})
    assert r["statusCode"] == 200 and corpo["agendamento"] == f"{dia}T14:30:00-03:00"
    dia2 = (T0 + timedelta(days=3)).date().isoformat()
    _, corpo = c.chamar("POST", f"/api/cs/chamados/{n}/agendamento", {"data": dia2, "hora": "09:00"})
    assert corpo["agendamento"].startswith(dia2)


@pytest.mark.parametrize(
    "corpo",
    [
        {},
        {"data": "2025-03-01", "hora": "10:00"},  # passado
        {"data": "2025-05-01", "hora": "10:00"},  # além de 30 dias
        {"data": "10/03/2025", "hora": "10:00"},
        {"data": "2025-03-12", "hora": "25:99"},
    ],
)
def test_agendamento_invalido_422_sem_gravar(c, corpo):
    n = c.escalar("J1")
    r, _ = c.chamar("POST", f"/api/cs/chamados/{n}/agendamento", corpo)
    assert r["statusCode"] == 422
    assert c.app.repos.chamados.obter(n).agendamento is None


def test_sem_sessao_401(c):
    for metodo, sufixo in (
        ("GET", "sugestao"),
        ("POST", "mensagens"),
        ("POST", "ordem-servico"),
        ("POST", "agendamento"),
    ):
        r, _ = c.chamar(metodo, f"/api/cs/chamados/TRES-X/{sufixo}", quem=None)
        assert r["statusCode"] == 401, sufixo
