"""Fluxo do formulário "Abrir chamado" da área do cliente (rotas públicas existentes):
criar Jornada -> escalar (pedido_humano) -> mensagem -> contato. O Chamado entra na fila do CS."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from core import criar_app, criar_roteador, processar

AGORA = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)
ROTEADOR = criar_roteador()


def chamar(app, caminho: str, corpo: dict):
    evento = {
        "rawPath": f"/api/pub{caminho}",
        "headers": {},
        "requestContext": {"requestId": "r", "http": {"method": "POST"}},
        "body": json.dumps(corpo),
    }
    resposta = processar(app, ROTEADOR, evento)
    return resposta["statusCode"], json.loads(resposta["body"])


def test_formulario_abre_chamado_na_fila_do_cs():
    app = criar_app({}, modo="local", relogio=lambda: AGORA)
    status, jornada = chamar(app, "/jornadas", {"origem": "busca"})
    assert status == 201
    status, escalada = chamar(
        app,
        f"/jornadas/{jornada['jornada_id']}/escalar",
        {"motivo": "pedido_humano", "evento_id": "01JABERTURA000000000000001"},
    )
    assert status == 200
    numero = escalada["numero"]
    texto = "Assunto: Vazamento\nUrgência: Alta\nCliente: Ana\nDescrição: pinga água"
    status, _ = chamar(app, f"/chamados/{numero}/mensagens", {"texto": texto})
    assert status == 201
    status, _ = chamar(
        app, f"/chamados/{numero}/contato", {"telefone": "11 91234-5678", "consentimento": True}
    )
    assert status == 200

    assert numero in [c.numero for c in app.repos.chamados.listar_fila()]
    mensagens = app.repos.mensagens.listar(numero)
    assert [m.autor for m in mensagens] == ["consumidor"]
    assert "Vazamento" in mensagens[0].texto
