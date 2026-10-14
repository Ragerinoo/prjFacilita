"""Rotas de resolução, vazamento, escalada e avaliação (tarefa 12.3)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from core import criar_app, criar_roteador, processar
from repositorios.ids import novo_ulid
from repositorios.modelos import Jornada

AGORA = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)
ROTEADOR = criar_roteador()
JID = "01JRESOL0000000000000000A"


@pytest.fixture
def app():
    app = criar_app({}, modo="local", relogio=lambda: AGORA)
    app.repos.jornadas.criar(
        Jornada(
            jornada_id=JID,
            criada_em=AGORA,
            ultima_interacao=AGORA,
            origem="qr",
            origem_inicial="qr",
            modelo_id="tres-passione",
        )
    )
    return app


def post(app, caminho: str, corpo: dict[str, Any], jid: str = JID):
    evento = {
        "rawPath": f"/api/pub/jornadas/{jid}/{caminho}",
        "headers": {},
        "requestContext": {"requestId": "r", "http": {"method": "POST"}},
        "body": json.dumps(corpo),
    }
    resposta = processar(app, ROTEADOR, evento)
    return resposta["statusCode"], (json.loads(resposta["body"]) if resposta["body"] else None)


def eid() -> str:
    return novo_ulid(AGORA)


def test_resolucao_sim_encerra_na_camada_guia(app):
    status, corpo = post(
        app, "resolucao", {"resolvido": True, "problema_id": 1, "evento_id": eid()}
    )
    assert status == 200
    assert corpo["jornada"]["estado"] == "encerrada_guia"
    j = app.repos.jornadas.obter(JID)
    assert j.encerramento.camada == "guia" and j.escalada is None


def test_resolucao_sim_repetida_e_idempotente(app):
    e = eid()
    for _ in range(2):
        status, _ = post(app, "resolucao", {"resolvido": True, "problema_id": "2", "evento_id": e})
        assert status == 200
    assert app.repos.jornadas.obter(JID).encerramento.camada == "guia"


def test_resolucao_nao_escala_p2_sem_assistente(app):
    status, corpo = post(
        app, "resolucao", {"resolvido": False, "problema_id": 1, "evento_id": eid()}
    )
    assert status == 200
    assert corpo["numero"] == corpo["chamado"]["numero"].strip()
    assert corpo["novo"] is True
    j = app.repos.jornadas.obter(JID)
    assert j.fatos().guia_respondeu_nao
    assert app.repos.chamados.obter(corpo["numero"]).prioridade == "P2"
    assert "P2" not in json.dumps(corpo)
    # Repetir: mesmo Chamado, sem criar outro.
    status2, corpo2 = post(
        app, "resolucao", {"resolvido": False, "problema_id": 1, "evento_id": eid()}
    )
    assert status2 == 200 and corpo2["numero"] == corpo["numero"] and corpo2["novo"] is False


def test_resolucao_nao_com_risco_vira_p1(app):
    post(app, "vazamento", {"tipo": "interno", "evento_id": eid()})
    _, corpo = post(app, "resolucao", {"resolvido": False, "problema_id": 1, "evento_id": eid()})
    assert app.repos.chamados.obter(corpo["numero"]).prioridade == "P1"


def test_resolucao_validacao(app):
    assert post(app, "resolucao", {"problema_id": 1})[0] == 422
    assert post(app, "resolucao", {"resolvido": True})[0] == 422
    assert post(app, "resolucao", {"resolvido": True, "problema_id": 1}, jid="naoexiste")[0] == 404


def test_vazamento_externo_nao_escala(app):
    status, corpo = post(app, "vazamento", {"tipo": "externo", "evento_id": eid()})
    assert status == 200 and corpo["variante"] == "externo"
    assert corpo["jornada"]["risco"]["marcado"] is False
    assert app.repos.jornadas.obter(JID).escalada is None


def test_vazamento_interno_marca_risco_guia_e_escala(app):
    status, corpo = post(app, "vazamento", {"tipo": "interno", "evento_id": eid()})
    assert status == 200
    j = app.repos.jornadas.obter(JID)
    assert j.risco.origem == "guia" and j.escalada is not None
    assert corpo["jornada"]["risco"] == {
        "marcado": True,
        "origem": "guia",
        "em": "2025-01-02T03:04:05Z",
    }
    assert corpo["jornada"]["contato_cs"] == "confirmado"
    assert app.repos.chamados.obter(corpo["numero"]).prioridade == "P1"
    # Repetido: ainda um só Chamado.
    _, corpo2 = post(app, "vazamento", {"tipo": "interno", "evento_id": eid()})
    assert corpo2["numero"] == corpo["numero"]
    assert post(app, "vazamento", {"tipo": "xis"})[0] == 422


def test_escalar_risco_e_idempotente(app):
    status, corpo = post(app, "escalar", {"motivo": "risco", "evento_id": eid()})
    assert status == 200 and corpo["novo"] is True
    assert app.repos.jornadas.obter(JID).risco.origem == "lista"
    _, corpo2 = post(app, "escalar", {"motivo": "risco", "evento_id": eid()})
    assert corpo2["numero"] == corpo["numero"] and corpo2["novo"] is False
    assert post(app, "escalar", {"motivo": "outro"})[0] == 422


def test_escalar_pedido_humano(app):
    status, corpo = post(app, "escalar", {"motivo": "pedido_humano", "evento_id": eid()})
    assert status == 200
    assert app.repos.chamados.obter(corpo["numero"]) is not None


def test_avaliacao_uma_por_jornada(app):
    status, corpo = post(app, "avaliacao", {"nota": 5, "comentario": "ótimo", "evento_id": eid()})
    assert status == 201 and corpo["registrada"] is True
    status, corpo = post(app, "avaliacao", {"nota": 1, "evento_id": eid()})
    assert status == 200 and corpo["registrada"] is False
    assert corpo["avaliacao"] == {"nota": 5, "comentario": "ótimo"}
    assert app.repos.avaliacoes.obter(JID).nota == 5


@pytest.mark.parametrize(
    "corpo",
    [{"nota": 0}, {"nota": 6}, {"nota": "3"}, {}, {"nota": 3, "comentario": "x" * 501}],
)
def test_avaliacao_invalida(app, corpo):
    assert post(app, "avaliacao", corpo)[0] == 422
    assert app.repos.avaliacoes.obter(JID) is None


def test_avaliacao_comentario_500_aceito(app):
    assert post(app, "avaliacao", {"nota": 3, "comentario": "x" * 500})[0] == 201
