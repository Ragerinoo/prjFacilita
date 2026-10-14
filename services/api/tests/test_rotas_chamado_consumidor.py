"""Rotas do Chamado para o Consumidor (tarefa 12.4): fake em memória."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from core import criar_app, criar_roteador, processar
from repositorios import criar_repositorios_memoria
from repositorios.modelos import (
    Chamado,
    DecisaoRegistrada,
    EncerramentoChamado,
    GatilhoRegistrado,
    ItemJaTentado,
    Jornada,
    PacoteRepasse,
)
from servicos.fotos import ArmazenamentoLocal, definir_armazenamento

T0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
ROTEADOR = criar_roteador()
NUM = "TRES-7K3M9QX2PD"
JID = "01JTESTJORNADA0000000000AA"


def _chamado(num: str, prioridade: str) -> Chamado:
    pacote = PacoteRepasse(
        numero_chamado=num,
        modelo="Máquina Café — Modelo X",
        numero_serie="não informado",
        origem="qr",
        categoria="nao_liga",
        resumo="Resumo indisponível — ver histórico da Jornada",
        ja_tentado=(ItemJaTentado("Problema 1, passo 2", "guia", "não"),),
        classificacao="provável uso",
        prioridade=prioridade,  # type: ignore[arg-type]
        canal_recomendado="chat assíncrono",
        sentimento="neutro",
        anexos=(),
        proxima_acao="Revisar o histórico da Jornada",
    )
    return Chamado(
        numero=num,
        jornada_id=JID,
        criado_em=T0,
        prioridade=prioridade,  # type: ignore[arg-type]
        classificacao="provável uso",
        canal="ligação imediata",
        decisao_criterio=2,
        pacote=pacote,
    )


@pytest.fixture
def app():
    repos = criar_repositorios_memoria()
    repos.jornadas.criar(
        Jornada(jornada_id=JID, criada_em=T0, ultima_interacao=T0, origem="qr", origem_inicial="qr")
    )
    repos.chamados.criar_com_escalada(
        _chamado(NUM, "P2"),
        GatilhoRegistrado("pedido_humano", T0),  # type: ignore[arg-type]
        DecisaoRegistrada("P2", "provável uso", "canal", 2, T0),  # type: ignore[arg-type]
    )
    return criar_app({}, modo="local", repos=repos, relogio=lambda: T0 + timedelta(minutes=5))


@pytest.fixture(autouse=True)
def fotos():
    armazenamento = ArmazenamentoLocal(confiar_declarado=False)
    definir_armazenamento(armazenamento)
    yield armazenamento
    definir_armazenamento(None)


def chamar(app, metodo, caminho, corpo=None):
    evento = {
        "rawPath": f"/api/pub{caminho}",
        "headers": {},
        "requestContext": {"requestId": "r", "http": {"method": metodo}},
    }
    if corpo is not None:
        evento["body"] = json.dumps(corpo)
    resposta = processar(app, ROTEADOR, evento)
    return resposta["statusCode"], (json.loads(resposta["body"]) if resposta["body"] else None)


def test_get_devolve_contrato_sem_dados_pessoais(app) -> None:
    status, corpo = chamar(app, "GET", f"/chamados/{NUM}")
    assert status == 200
    assert corpo["numero"] == NUM and corpo["prioridade"] == "P2"
    assert corpo["status"] == "aberto" and corpo["canal"] == "ligação imediata"
    assert corpo["dados_solicitados"] == ["telefone", "cep"]
    assert corpo["anexos_total"] == 0 and corpo["mensagens"] == []
    assert corpo["agendamento"] is None and corpo["avaliacao_pendente"] is False
    assert "jornada_id" not in corpo and JID not in json.dumps(corpo)


def test_get_inexistente_404_sem_dados(app) -> None:
    status, corpo = chamar(app, "GET", "/chamados/TRES-NAOEXISTE")
    assert status == 404
    assert corpo["erro"]["codigo"] == "chamado_nao_encontrado"
    assert set(corpo) == {"erro"}


def test_contato_valida_e_nao_pede_de_novo(app) -> None:
    status, corpo = chamar(
        app,
        "POST",
        f"/chamados/{NUM}/contato",
        {"telefone": "(11) 91234-5678", "consentimento": True, "evento_id": "e1"},
    )
    assert status == 200 and corpo == {"dados_solicitados": ["cep"]}
    registro = app.repos.dados_pessoais.obter(NUM)
    assert registro.telefone == "(11) 91234-5678" and registro.consentimento.versao_finalidade
    _, chamado = chamar(app, "GET", f"/chamados/{NUM}")
    assert chamado["dados_solicitados"] == ["cep"]
    assert "91234" not in json.dumps(chamado)
    status, corpo = chamar(
        app, "POST", f"/chamados/{NUM}/contato", {"cep": "01310-100", "consentimento": True}
    )
    assert corpo == {"dados_solicitados": []}
    assert app.repos.dados_pessoais.obter(NUM).telefone == "(11) 91234-5678"  # preservado


def test_contato_sem_consentimento_ou_invalido_422_com_campos(app) -> None:
    status, corpo = chamar(
        app,
        "POST",
        f"/chamados/{NUM}/contato",
        {"telefone": "123", "cep": "1", "consentimento": False},
    )
    assert status == 422
    assert {c["campo"] for c in corpo["erro"]["campos"]} == {"telefone", "cep", "consentimento"}
    assert app.repos.dados_pessoais.obter(NUM) is None


def test_mensagem_mascara_pii_e_sinaliza_nao_lida(app) -> None:
    status, _ = chamar(
        app,
        "POST",
        f"/chamados/{NUM}/mensagens",
        {"texto": "Me ligue em (11) 91234-5678", "evento_id": "m1"},
    )
    assert status == 201
    assert app.repos.chamados.obter(NUM).resposta_nao_lida is True
    _, corpo = chamar(app, "GET", f"/chamados/{NUM}")
    assert [m["autor"] for m in corpo["mensagens"]] == ["consumidor"]
    assert "91234" not in corpo["mensagens"][0]["texto"]
    # repetição do mesmo evento_id é ignorada
    chamar(app, "POST", f"/chamados/{NUM}/mensagens", {"texto": "oi", "evento_id": "m1"})
    assert len(app.repos.mensagens.listar(NUM)) == 1


@pytest.mark.parametrize("texto", ["", "   ", "x" * 2001])
def test_mensagem_invalida_422(app, texto) -> None:
    status, corpo = chamar(
        app, "POST", f"/chamados/{NUM}/mensagens", {"texto": texto, "evento_id": "m2"}
    )
    assert status == 422 and corpo["erro"]["campos"][0]["campo"] == "texto"


def test_avaliacao_so_encerrado_e_uma_por_jornada(app) -> None:
    status, _ = chamar(app, "POST", f"/chamados/{NUM}/avaliacao", {"nota": 5, "evento_id": "a1"})
    assert status == 409
    app.repos.chamados.encerrar(
        NUM, EncerramentoChamado("falso_defeito", "outra", "ok", T0, "bruno")
    )
    _, corpo = chamar(app, "GET", f"/chamados/{NUM}")
    assert corpo["status"] == "encerrado" and corpo["avaliacao_pendente"] is True
    status, _ = chamar(app, "POST", f"/chamados/{NUM}/avaliacao", {"nota": 0, "evento_id": "a2"})
    assert status == 422
    status, _ = chamar(
        app,
        "POST",
        f"/chamados/{NUM}/avaliacao",
        {"nota": 4, "comentario": "ótimo", "evento_id": "a3"},
    )
    assert status == 200
    av = app.repos.avaliacoes.obter(JID)
    assert av.nota == 4 and av.camada == "humano"
    chamar(app, "POST", f"/chamados/{NUM}/avaliacao", {"nota": 1, "evento_id": "a4"})
    assert app.repos.avaliacoes.obter(JID).nota == 4
    _, corpo = chamar(app, "GET", f"/chamados/{NUM}")
    assert corpo["avaliacao_pendente"] is False


def _anexar(app, fotos, mime="image/jpeg", tamanho=1000):
    status, corpo = chamar(
        app, "POST", f"/chamados/{NUM}/anexos", {"mime": mime, "bytes": tamanho, "evento_id": "f"}
    )
    if status == 201:
        chave = f"chamados/{NUM}/{corpo['anexo_id']}"
        fotos.simular_envio(chave, tamanho, mime)
    return status, corpo


def test_fotos_fluxo_limite_e_rejeicao_isolada(app, fotos) -> None:
    status, corpo = chamar(
        app, "POST", f"/chamados/{NUM}/anexos", {"mime": "image/gif", "bytes": 10, "evento_id": "f"}
    )
    assert status == 422 and corpo["erro"]["codigo"] == "foto_invalida"
    status, corpo = chamar(
        app,
        "POST",
        f"/chamados/{NUM}/anexos",
        {"mime": "image/png", "bytes": 5 * 1024 * 1024 + 1, "evento_id": "f"},
    )
    assert status == 422 and corpo["erro"]["codigo"] == "foto_invalida"

    totais = []
    for _ in range(3):
        status, corpo = _anexar(app, fotos)
        assert status == 201 and corpo["upload"]["url"] and corpo["upload"]["campos"]["key"]
        status, conf = chamar(
            app, "POST", f"/chamados/{NUM}/anexos/{corpo['anexo_id']}/confirmacao", {}
        )
        assert status == 200
        totais.append(conf["anexos_total"])
    assert totais == [1, 2, 3]
    # confirmação repetida não duplica
    status, conf = chamar(
        app, "POST", f"/chamados/{NUM}/anexos/{corpo['anexo_id']}/confirmacao", {}
    )
    assert conf["anexos_total"] == 3
    status, corpo = chamar(
        app, "POST", f"/chamados/{NUM}/anexos", {"mime": "image/png", "bytes": 10, "evento_id": "f"}
    )
    assert status == 409 and corpo["erro"]["codigo"] == "limite_fotos"
    _, chamado = chamar(app, "GET", f"/chamados/{NUM}")
    assert chamado["anexos_total"] == 3


def test_confirmacao_sem_objeto_422(app, fotos) -> None:
    _, corpo = chamar(
        app, "POST", f"/chamados/{NUM}/anexos", {"mime": "image/png", "bytes": 10, "evento_id": "f"}
    )
    status, erro = chamar(
        app, "POST", f"/chamados/{NUM}/anexos/{corpo['anexo_id']}/confirmacao", {}
    )
    assert status == 422 and erro["erro"]["codigo"] == "foto_invalida"
    assert app.repos.chamados.obter(NUM).anexos == ()


def test_confirmacao_objeto_grande_demais_e_descartado(app, fotos) -> None:
    _, corpo = chamar(
        app, "POST", f"/chamados/{NUM}/anexos", {"mime": "image/png", "bytes": 10, "evento_id": "f"}
    )
    chave = f"chamados/{NUM}/{corpo['anexo_id']}"
    fotos.simular_envio(chave, 6 * 1024 * 1024, "image/png")
    status, erro = chamar(
        app, "POST", f"/chamados/{NUM}/anexos/{corpo['anexo_id']}/confirmacao", {}
    )
    assert status == 422 and chave in fotos.descartados
