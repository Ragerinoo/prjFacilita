"""Rotas do Painel_CS da tarefa 13.2: fila, card, assumir, Dados_Pessoais e anexos.

Passam pela API real (roteador + autenticador + matriz de perfis) com repositórios em memória.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta

import pytest

from core import Roteador, criar_app, criar_roteador
from core.processamento import processar
from repositorios import ErroRepositorio
from repositorios.modelos import AnexoChamado, Consentimento, Jornada, UsuarioCS
from servicos import senhas
from servicos.anexos import definir_porta_anexos
from servicos.autenticacao import COOKIE_SESSAO
from servicos.escalada import ServicoEscalada

T0 = datetime(2025, 3, 10, 12, 0, 0, tzinfo=UTC)
SENHA = "senha-inicial-segura-1"
TEL = "11987654321"
CEP = "01310100"


@pytest.fixture(scope="module")
def hash_senha() -> str:
    return senhas.gerar_hash(SENHA)


class Cliente:
    def __init__(self, hash_senha: str) -> None:
        self.agora = T0
        self.app = criar_app({}, modo="local", relogio=lambda: self.agora)
        self.roteador = Roteador(criar_roteador().rotas)
        for nome, perfil in (("ana", "atendente"), ("gil", "gestor"), ("bia", "atendente")):
            self.app.repos.usuarios_cs.criar(
                UsuarioCS(nome, hash_senha, perfil, deve_trocar_senha=False)  # type: ignore[arg-type]
            )
        self.cookies: dict[str, str] = {}

    def entrar(self, usuario: str) -> None:
        r = self.chamar("POST", "/api/cs/login", {"usuario": usuario, "senha": SENHA}, quem=None)[0]
        assert r["statusCode"] == 200
        self.cookies[usuario] = r["cookies"][0].partition("=")[2].split(";")[0]

    def chamar(self, metodo, caminho, corpo=None, *, quem="ana"):
        cab = {"x-requested-with": "tres-painel"}
        if quem is not None:
            cab["cookie"] = f"{COOKIE_SESSAO}={self.cookies[quem]}"
        evento = {
            "rawPath": caminho,
            "headers": cab,
            "requestContext": {"requestId": "r", "http": {"method": metodo}},
        }
        if corpo is not None:
            evento["body"] = json.dumps(corpo)
        r = processar(self.app, self.roteador, evento)
        return r, (json.loads(r["body"]) if r["body"] else None)

    def escalar(self, jid="J1", gatilho="pedido_humano", **jornada) -> str:
        repos = self.app.repos
        repos.jornadas.criar(
            Jornada(jid, T0, T0, "qr", "qr", modelo_id="m", numero_serie="X1", **jornada)
        )
        servico = ServicoEscalada(repos, relogio=lambda: self.agora)
        return servico.escalar(jid, gatilho).chamado.numero


@pytest.fixture
def c(hash_senha):
    cliente = Cliente(hash_senha)
    for u in ("ana", "gil", "bia"):
        cliente.entrar(u)
    yield cliente
    definir_porta_anexos(None)


def test_sem_sessao_401_em_todas_as_rotas(c):
    c.cookies["x"] = "invalido"
    for metodo, caminho in (
        ("GET", "/api/cs/fila"),
        ("GET", "/api/cs/chamados/TRES-X"),
        ("POST", "/api/cs/chamados/TRES-X/assumir"),
        ("GET", "/api/cs/chamados/TRES-X/dados-pessoais"),
        ("GET", "/api/cs/chamados/TRES-X/anexos/0"),
    ):
        r, corpo = c.chamar(metodo, caminho, quem=None)
        assert r["statusCode"] == 401, caminho
        assert TEL not in r["body"]


def test_atendente_e_gestor_acessam_fila(c):
    for quem in ("ana", "gil"):
        r, corpo = c.chamar("GET", "/api/cs/fila", quem=quem)
        assert r["statusCode"] == 200 and corpo == {"itens": []}


def test_fila_ordenada_com_flags_e_sem_pii(c):
    n_p3 = c.escalar("J1")
    c.agora += timedelta(seconds=90)
    n_p1 = c.escalar("J2", "risco_seguranca")
    c.app.repos.dados_pessoais.salvar(n_p3, Consentimento(T0, "v1"), telefone=TEL, cep=CEP)
    c.app.repos.mensagens.adicionar(n_p3, "consumidor", f"me liga {TEL}", T0)

    r, corpo = c.chamar("GET", "/api/cs/fila")
    assert r["statusCode"] == 200
    itens = corpo["itens"]
    assert [i["numero"] for i in itens] == [n_p1, n_p3]
    p1, p3 = itens
    assert p1["prioridade"] == "P1" and p1["alerta_p1"] is True and p1["alerta_p1_visto"] is False
    assert p3["alerta_p1"] is False and p3["tempo_espera_s"] == 90
    assert {"classificacao", "status", "responsavel", "resposta_nao_lida", "resumo"} <= set(p1)
    assert TEL not in r["body"] and CEP not in r["body"]


def test_card_completo_sem_pii_e_reconhece_alerta_p1(c):
    n = c.escalar("J1", "risco_seguranca")
    c.app.repos.dados_pessoais.salvar(n, Consentimento(T0, "v1"), telefone=TEL, cep=CEP)
    c.app.repos.mensagens.adicionar(n, "consumidor", f"meu numero {TEL}", T0)

    r, card = c.chamar("GET", f"/api/cs/chamados/{n}", quem="gil")
    assert r["statusCode"] == 200
    assert card["numero"] == n and card["pacote"]["numero_chamado"] == n
    assert card["prioridade"] == "P1" and card["status"] == "aberto"
    assert {"os_status", "agendamento", "responsavel", "historico", "mensagens"} <= set(card)
    assert len(card["mensagens"]) == 1 and TEL not in r["body"] and CEP not in r["body"]
    # abrir o card reconhece o alerta P1 para todos
    _, fila = c.chamar("GET", "/api/cs/fila")
    assert fila["itens"][0]["alerta_p1"] is False and fila["itens"][0]["alerta_p1_visto"] is True


def test_card_inexistente_404(c):
    r, corpo = c.chamar("GET", "/api/cs/chamados/TRES-NAOEXISTE")
    assert r["statusCode"] == 404 and corpo["erro"]["codigo"] == "nao_encontrado"


def test_assumir_e_corrida_devolve_409_com_nome_do_vencedor(c):
    n = c.escalar()
    r, corpo = c.chamar("POST", f"/api/cs/chamados/{n}/assumir", quem="ana")
    assert r["statusCode"] == 200 and corpo["responsavel"]["usuario"] == "ana"
    assert corpo["status"] == "em_atendimento"
    r, corpo = c.chamar("POST", f"/api/cs/chamados/{n}/assumir", quem="bia")
    assert r["statusCode"] == 409 and corpo["erro"]["codigo"] == "ja_assumido"
    assert "ana" in corpo["erro"]["mensagem"] and corpo["responsavel"]["usuario"] == "ana"


def test_assumir_concorrente_so_um_vence(c):
    n = c.escalar()
    codigos: list[int] = []

    def tentar(quem):
        codigos.append(
            c.chamar("POST", f"/api/cs/chamados/{n}/assumir", quem=quem)[0]["statusCode"]
        )

    ts = [threading.Thread(target=tentar, args=(q,)) for q in ("ana", "bia", "gil")]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(codigos) == [200, 409, 409]


def test_dados_pessoais_registra_acesso_e_devolve_dados(c):
    n = c.escalar()
    c.app.repos.dados_pessoais.salvar(n, Consentimento(T0, "v1"), telefone=TEL, cep=CEP)
    r, corpo = c.chamar("GET", f"/api/cs/chamados/{n}/dados-pessoais", quem="ana")
    assert r["statusCode"] == 200 and corpo["telefone"] == TEL and corpo["cep"] == CEP
    (acesso,) = c.app.repos.acessos_pii.listar(n)
    assert acesso.atendente_id == "ana"


def test_dados_pessoais_grava_acesso_antes_de_ler_os_dados(c):
    n = c.escalar()
    ordem: list[str] = []
    repos = c.app.repos
    reg, obter = repos.acessos_pii.registrar, repos.dados_pessoais.obter
    repos.acessos_pii.registrar = lambda *a, **k: (ordem.append("log"), reg(*a, **k))[1]  # type: ignore[method-assign]
    repos.dados_pessoais.obter = lambda *a, **k: (ordem.append("dados"), obter(*a, **k))[1]  # type: ignore[method-assign]
    r, _ = c.chamar("GET", f"/api/cs/chamados/{n}/dados-pessoais")
    assert r["statusCode"] == 200 and ordem == ["log", "dados"]


def test_dados_pessoais_falha_do_log_devolve_403_sem_dados(c):
    n = c.escalar()
    c.app.repos.dados_pessoais.salvar(n, Consentimento(T0, "v1"), telefone=TEL, cep=CEP)

    def falha(*_a, **_k):
        raise ErroRepositorio("indisponível")

    c.app.repos.acessos_pii.registrar = falha  # type: ignore[method-assign]
    r, corpo = c.chamar("GET", f"/api/cs/chamados/{n}/dados-pessoais")
    assert r["statusCode"] == 403 and corpo["erro"]["codigo"] == "log_acesso_indisponivel"
    assert TEL not in r["body"] and CEP not in r["body"]


def test_rota_dados_pessoais_usa_a_lambda_dedicada(c):
    destinos = {r.caminho: r.destino for r in criar_roteador().rotas if r.escopo == "cs"}
    assert destinos["/chamados/{numero}/dados-pessoais"] == "dados_pessoais"
    assert destinos["/fila"] == "api"


def test_anexo_devolve_url_curta_e_valida_indice(c):
    n = c.escalar()
    chamado = c.app.repos.chamados.obter(n)
    anexo = AnexoChamado("fotos/J1/a.jpg", "image/jpeg", 1234)
    c.app.repos.chamados.adicionar_anexo(n, anexo)
    assert chamado is not None
    r, corpo = c.chamar("GET", f"/api/cs/chamados/{n}/anexos/0")
    assert r["statusCode"] == 200 and "fotos/J1/a.jpg" in corpo["url"]
    assert corpo["expira_em_s"] <= 60 and corpo["mime"] == "image/jpeg"
    for ruim in ("1", "abc", "-1"):
        r, _ = c.chamar("GET", f"/api/cs/chamados/{n}/anexos/{ruim}")
        assert r["statusCode"] == 404
    # o card lista o anexo por índice, sem expor a chave
    _, card = c.chamar("GET", f"/api/cs/chamados/{n}")
    assert card["anexos"] == [{"indice": 0, "mime": "image/jpeg", "bytes": 1234}]
