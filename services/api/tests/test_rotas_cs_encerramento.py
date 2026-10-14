"""Rotas da tarefa 13.4: encerrar Chamado e Cache_Respostas pelo Painel_CS (Req 16.1 a 16.8)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from core import Roteador, criar_app, criar_roteador
from core.processamento import processar
from dominio import chave_cache
from repositorios import ErroRepositorio
from repositorios.modelos import Jornada, UsuarioCS
from servicos import senhas
from servicos.autenticacao import COOKIE_SESSAO
from servicos.escalada import ServicoEscalada

T0 = datetime(2025, 3, 10, 12, 0, 0, tzinfo=UTC)
SENHA = "senha-inicial-segura-1"


@pytest.fixture(scope="module")
def hash_senha() -> str:
    return senhas.gerar_hash(SENHA)


class Cliente:
    def __init__(self, hash_senha: str) -> None:
        self.app = criar_app({}, modo="local", relogio=lambda: T0)
        self.roteador = Roteador(criar_roteador().rotas)
        self.app.repos.usuarios_cs.criar(
            UsuarioCS("ana", hash_senha, "atendente", deve_trocar_senha=False)  # type: ignore[arg-type]
        )
        r = self.chamar("POST", "/api/cs/login", {"usuario": "ana", "senha": SENHA}, logado=False)[0]
        self.cookie = r["cookies"][0].partition("=")[2].split(";")[0]

    def chamar(self, metodo, caminho, corpo=None, *, logado=True):
        cab = {"x-requested-with": "tres-painel"}
        if logado:
            cab["cookie"] = f"{COOKIE_SESSAO}={self.cookie}"
        evento = {
            "rawPath": caminho,
            "headers": cab,
            "requestContext": {"requestId": "r", "http": {"method": metodo}},
        }
        if corpo is not None:
            evento["body"] = json.dumps(corpo)
        r = processar(self.app, self.roteador, evento)
        return r, (json.loads(r["body"]) if r["body"] else None)

    def escalar(self, jid="J1", modelo_id="m") -> str:
        self.app.repos.jornadas.criar(
            Jornada(jid, T0, T0, "qr", "qr", modelo_id=modelo_id, numero_serie="X1", problema_id=2)
        )
        return ServicoEscalada(self.app.repos, relogio=lambda: T0).escalar(jid, "pedido_humano").chamado.numero


@pytest.fixture
def c(hash_senha):
    return Cliente(hash_senha)


CORPO_OK = {"desfecho": "falso_defeito", "solucao_tipo": "instrução do manual", "solucao": "Limpar o filtro."}


def test_sem_sessao_401(c):
    assert c.chamar("POST", "/api/cs/chamados/TRES-X/encerrar", CORPO_OK, logado=False)[0]["statusCode"] == 401
    assert c.chamar("POST", "/api/cs/cache", {}, logado=False)[0]["statusCode"] == 401


def test_encerrar_registra_chamado_e_camada_humano(c):
    n = c.escalar()
    r, corpo = c.chamar("POST", f"/api/cs/chamados/{n}/encerrar", CORPO_OK)
    assert r["statusCode"] == 200
    assert corpo["status"] == "encerrado" and corpo["desfecho"] == "falso_defeito"
    assert corpo["por"] == "ana" and corpo["oferecer_cache"] is True
    chamado = c.app.repos.chamados.obter(n)
    assert chamado.status == "encerrado" and chamado.encerramento.solucao == "Limpar o filtro."
    enc = c.app.repos.jornadas.obter("J1").encerramento
    assert enc.camada == "humano" and enc.desfecho == "falso_defeito" and enc.problema_id == 2


def test_encerrar_defeito_real_nao_oferece_cache_e_aceita_desfecho_com_espaco(c):
    n = c.escalar()
    r, corpo = c.chamar(
        "POST",
        f"/api/cs/chamados/{n}/encerrar",
        {"desfecho": "defeito real", "solucao_tipo": "outra", "solucao": "Troca de peça."},
    )
    assert r["statusCode"] == 200 and corpo["desfecho"] == "defeito_real"
    assert corpo["oferecer_cache"] is False


@pytest.mark.parametrize(
    "corpo,campo",
    [
        ({**CORPO_OK, "desfecho": None}, "desfecho"),
        ({**CORPO_OK, "desfecho": "talvez"}, "desfecho"),
        ({**CORPO_OK, "solucao": ""}, "descricao_solucao"),
        ({**CORPO_OK, "solucao": "x" * 501}, "descricao_solucao"),
        ({**CORPO_OK, "solucao_tipo": "xyz"}, "tipo_solucao"),
    ],
)
def test_encerrar_invalido_422_mantem_aberto(c, corpo, campo):
    n = c.escalar()
    r, resp = c.chamar("POST", f"/api/cs/chamados/{n}/encerrar", corpo)
    assert r["statusCode"] == 422
    assert campo in json.dumps(resp)
    assert c.app.repos.chamados.obter(n).status == "aberto"
    assert c.app.repos.jornadas.obter("J1").encerramento is None


def test_encerrar_duas_vezes_409_e_inexistente_404(c):
    n = c.escalar()
    assert c.chamar("POST", f"/api/cs/chamados/{n}/encerrar", CORPO_OK)[0]["statusCode"] == 200
    r, corpo = c.chamar("POST", f"/api/cs/chamados/{n}/encerrar", CORPO_OK)
    assert r["statusCode"] == 409 and corpo["erro"]["codigo"] == "chamado_encerrado"
    assert c.chamar("POST", "/api/cs/chamados/TRES-NAO/encerrar", CORPO_OK)[0]["statusCode"] == 404


def test_cache_cria_e_duplicata_mantem_existente(c):
    n = c.escalar()
    c.chamar("POST", f"/api/cs/chamados/{n}/encerrar", CORPO_OK)
    corpo = {"numero": n, "pergunta": "Máquina não liga?", "resposta": "Limpe o filtro."}
    r, resp = c.chamar("POST", "/api/cs/cache", corpo)
    assert r["statusCode"] == 201 and resp["criada"] is True and resp["aprovador_id"] == "ana"
    chave = chave_cache("m", "maquina nao liga")
    assert resp["chave"] == chave
    reg = c.app.repos.cache.obter(chave)
    assert reg.aprovador_id == "ana" and reg.aprovado_em == T0 and reg.resposta == "Limpe o filtro."
    r2, resp2 = c.chamar("POST", "/api/cs/cache", {**corpo, "resposta": "Outra resposta"})
    assert r2["statusCode"] == 200 and resp2["ja_existe"] is True and resp2["aviso"]
    assert c.app.repos.cache.obter(chave).resposta == "Limpe o filtro."
    assert c.app.repos.chamados.obter(n).status == "encerrado"


@pytest.mark.parametrize(
    "extra,campo",
    [
        ({"pergunta": ""}, "pergunta"),
        ({"pergunta": "x" * 301}, "pergunta"),
        ({"resposta": ""}, "resposta"),
        ({"resposta": "y" * 1001}, "resposta"),
        ({"resposta": "Ligue para 11987654321"}, "resposta"),
        ({"pergunta": "Meu e-mail é a@b.com"}, "pergunta"),
    ],
)
def test_cache_invalido_422_nao_grava(c, extra, campo):
    n = c.escalar()
    corpo = {"numero": n, "pergunta": "Pergunta", "resposta": "Resposta", **extra}
    r, resp = c.chamar("POST", "/api/cs/cache", corpo)
    assert r["statusCode"] == 422 and campo in json.dumps(resp)
    assert c.app.repos.cache.obter(chave_cache("m", corpo["pergunta"])) is None


def test_cache_chamado_inexistente_404_e_sem_modelo_422(c):
    assert c.chamar("POST", "/api/cs/cache", {"numero": "TRES-NAO", "pergunta": "a", "resposta": "b"})[0][
        "statusCode"
    ] == 404
    n = c.escalar("J9", modelo_id=None)
    r, resp = c.chamar("POST", "/api/cs/cache", {"numero": n, "pergunta": "a", "resposta": "b"})
    assert r["statusCode"] == 422 and "numero" in json.dumps(resp)


def test_cache_falha_de_armazenamento_503_sem_reabrir(c, monkeypatch):
    n = c.escalar()
    c.chamar("POST", f"/api/cs/chamados/{n}/encerrar", CORPO_OK)

    def falha(*_a, **_k):
        raise ErroRepositorio("fora do ar")

    monkeypatch.setattr(c.app.repos.cache, "inserir", falha)
    r, resp = c.chamar("POST", "/api/cs/cache", {"numero": n, "pergunta": "a", "resposta": "b"})
    assert r["statusCode"] == 503 and resp["erro"]["codigo"] == "cache_indisponivel"
    assert c.app.repos.chamados.obter(n).status == "encerrado"
