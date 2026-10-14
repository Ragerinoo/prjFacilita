"""Autenticação do Painel_CS: login, bloqueio, sessão deslizante, cookie, CSRF e 401/403.

Cobre os Requisitos 13.2 a 13.8 pela API real (roteador + rotas de `routes/cs_auth.py` +
autenticador ligado por `criar_app`), com repositórios em memória e relógio controlado.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from core import Rota, Roteador, criar_app, criar_roteador
from core.processamento import processar
from repositorios.modelos import UsuarioCS
from servicos import senhas
from servicos.autenticacao import COOKIE_SESSAO, hash_token

INICIO = datetime(2025, 3, 10, 12, 0, 0, tzinfo=UTC)
SENHA = "senha-inicial-segura-1"
CSRF = {"x-requested-with": "tres-painel"}


@pytest.fixture(scope="module")
def hash_da_senha() -> str:
    return senhas.gerar_hash(SENHA)


class Cliente:
    """Chama a API como o navegador: guarda o cookie da sessão e usa um relógio manual."""

    def __init__(self, hash_da_senha: str) -> None:
        self.agora = INICIO
        self.app = criar_app({}, modo="local", relogio=lambda: self.agora)
        self.rotas = [
            *criar_roteador().rotas,
            # `/cache` e `/metricas` já existem de verdade em `criar_roteador()`; só `/config`
            # ainda não, então uma rota de teste a representa.
            Rota("PUT", "/config", lambda c: {"config": 1}, escopo="cs"),
        ]
        self.cookie: str | None = None
        for nome, perfil in (("ana", "atendente"), ("gil", "gestor")):
            self.app.repos.usuarios_cs.criar(
                UsuarioCS(nome, hash_da_senha, perfil, deve_trocar_senha=nome == "ana")  # type: ignore[arg-type]
            )

    def avancar(self, **delta: float) -> None:
        self.agora += timedelta(**delta)

    def chamar(self, metodo, caminho, corpo=None, *, csrf=True, cookie="__guardado__"):
        cabecalhos = dict(CSRF) if csrf else {}
        valor_cookie = self.cookie if cookie == "__guardado__" else cookie
        if valor_cookie is not None:
            cabecalhos["cookie"] = f"{COOKIE_SESSAO}={valor_cookie}"
        evento = {
            "rawPath": caminho,
            "headers": cabecalhos,
            "requestContext": {"requestId": "req-1", "http": {"method": metodo}},
        }
        if corpo is not None:
            evento["body"] = json.dumps(corpo)
        resposta = processar(self.app, Roteador(self.rotas), evento)
        corpo_resp = json.loads(resposta["body"]) if resposta["body"] else None
        return resposta, corpo_resp

    def entrar(self, usuario="ana", senha=SENHA):
        resposta, corpo = self.chamar(
            "POST", "/api/cs/login", {"usuario": usuario, "senha": senha}, cookie=None
        )
        if resposta["statusCode"] == 200:
            nome, _, resto = resposta["cookies"][0].partition("=")
            assert nome == COOKIE_SESSAO
            self.cookie = resto.split(";")[0]
        return resposta, corpo


@pytest.fixture
def cliente(hash_da_senha) -> Cliente:
    return Cliente(hash_da_senha)


def codigo(corpo) -> str:
    return corpo["erro"]["codigo"]


# --------------------------------------------------------------------------- login (13.6, 13.7)


def test_login_valido_cria_sessao_com_perfil_e_cookie_seguro(cliente):
    resposta, corpo = cliente.entrar("ana")
    assert resposta["statusCode"] == 200
    assert corpo["perfil"] == "atendente" and corpo["deve_trocar_senha"] is True
    assert corpo["usuario"] == "ana"
    (cookie,) = resposta["cookies"]
    atributos = [a.strip() for a in cookie.split(";")]
    assert {"HttpOnly", "Secure", "SameSite=Strict", "Path=/api/cs"} <= set(atributos)
    assert SENHA not in resposta["body"] and cliente.cookie not in resposta["body"]


def test_usuario_e_normalizado_sem_caixa_nem_espacos(cliente):
    resposta, corpo = cliente.entrar("  GIL ")
    assert resposta["statusCode"] == 200 and corpo["perfil"] == "gestor"


def test_token_opaco_de_256_bits_e_so_o_hash_fica_guardado(cliente):
    cliente.entrar("ana")
    assert len(cliente.cookie) == 43  # 32 bytes em base64 url-safe, sem preenchimento
    sessoes = cliente.app.repos.sessoes
    assert sessoes.obter(cliente.cookie) is None  # o token em claro não é chave de nada
    guardada = sessoes.obter(hash_token(cliente.cookie))
    assert guardada is not None and guardada.usuario == "ana" and guardada.perfil == "atendente"
    assert len(guardada.token_hash) == 64  # SHA-256 em hexadecimal


def test_tokens_de_logins_diferentes_sao_diferentes(cliente):
    cliente.entrar("ana")
    primeiro = cliente.cookie
    cliente.entrar("ana")
    assert cliente.cookie != primeiro


def test_mensagem_de_erro_e_igual_para_usuario_inexistente_e_senha_errada(cliente):
    r1, c1 = cliente.entrar("ana", "senha-errada")
    r2, c2 = cliente.entrar("fantasma", "senha-errada")
    assert r1["statusCode"] == r2["statusCode"] == 401
    assert c1 == c2 and codigo(c1) == "credenciais_invalidas"
    assert "cookies" not in r1 and "cookies" not in r2  # nenhuma sessão iniciada
    assert cliente.app.repos.sessoes._itens == {}  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "corpo",
    [{}, {"usuario": "ana"}, {"senha": SENHA}, {"usuario": 7, "senha": SENHA},
     {"usuario": "ana", "senha": ["x"]}, {"usuario": "ana", "senha": ""},
     {"usuario": "x" * 500, "senha": SENHA}, {"usuario": "ana", "senha": "x" * 5000}],
)  # fmt: skip
def test_campos_ausentes_ou_invalidos_dao_a_mesma_resposta_generica(cliente, corpo):
    resposta, envelope = cliente.chamar("POST", "/api/cs/login", corpo, cookie=None)
    assert resposta["statusCode"] == 401 and codigo(envelope) == "credenciais_invalidas"


def test_tempo_equalizado_usuario_inexistente_verifica_contra_hash_ficticio(cliente, monkeypatch):
    chamadas: list[str] = []
    real = senhas.verificar

    def espiao(senha, armazenado):
        chamadas.append(armazenado)
        return real(senha, armazenado)

    monkeypatch.setattr(senhas, "verificar", espiao)
    cliente.entrar("fantasma", "qualquer-senha")
    assert chamadas == [senhas.hash_ficticio()]
    # Para usuário existente com senha errada o custo é o mesmo: uma verificação.
    chamadas.clear()
    cliente.entrar("ana", "senha-errada")
    assert len(chamadas) == 1


def test_login_exige_cabecalho_x_requested_with(cliente):
    resposta, corpo = cliente.chamar(
        "POST", "/api/cs/login", {"usuario": "ana", "senha": SENHA}, csrf=False, cookie=None
    )
    assert resposta["statusCode"] == 403 and codigo(corpo) == "cabecalho_obrigatorio"
    assert "cookies" not in resposta


def test_hash_antigo_e_regravado_e_a_flag_de_troca_de_senha_e_mantida(cliente):
    from argon2 import PasswordHasher

    fraco = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(SENHA)
    cliente.app.repos.usuarios_cs.definir_senha("ana", fraco, deve_trocar_senha=True)
    assert cliente.entrar("ana")[0]["statusCode"] == 200
    atual = cliente.app.repos.usuarios_cs.obter("ana")
    assert atual.hash_senha != fraco and senhas.verificar(SENHA, atual.hash_senha)
    assert atual.deve_trocar_senha is True


# --------------------------------------------------------------------------- bloqueio (13.8)


def falhar(cliente, vezes):
    return [cliente.entrar("ana", "errada") for _ in range(vezes)]


def test_quinta_falha_em_15_minutos_bloqueia_por_15_minutos(cliente):
    resultados = falhar(cliente, 4)
    assert all(codigo(c) == "credenciais_invalidas" for _, c in resultados)
    resposta, corpo = cliente.entrar("ana", "errada")
    assert resposta["statusCode"] == 429 and codigo(corpo) == "login_bloqueado"
    assert "bloqueado" in corpo["erro"]["mensagem"].lower()
    assert resposta["headers"]["Retry-After"] == "900"
    # Durante o bloqueio, nem a senha certa entra.
    cliente.avancar(minutes=14, seconds=59)
    assert codigo(cliente.entrar("ana", SENHA)[1]) == "login_bloqueado"
    # Passados 15 minutos, volta a funcionar.
    cliente.avancar(seconds=1)
    assert cliente.entrar("ana", SENHA)[0]["statusCode"] == 200


def test_falhas_espalhadas_por_mais_de_15_minutos_nao_bloqueiam(cliente):
    falhar(cliente, 4)
    cliente.avancar(minutes=15, seconds=1)
    resposta, corpo = cliente.entrar("ana", "errada")
    assert resposta["statusCode"] == 401 and codigo(corpo) == "credenciais_invalidas"


def test_login_valido_zera_as_falhas_consecutivas(cliente):
    falhar(cliente, 4)
    assert cliente.entrar("ana", SENHA)[0]["statusCode"] == 200
    resultados = falhar(cliente, 4)  # recomeça do zero: 4 falhas ainda não bloqueiam
    assert all(codigo(c) == "credenciais_invalidas" for _, c in resultados)


def test_apos_o_bloqueio_a_contagem_recomeca(cliente):
    falhar(cliente, 5)
    cliente.avancar(minutes=15)
    resultados = falhar(cliente, 4)
    assert all(codigo(c) == "credenciais_invalidas" for _, c in resultados)
    assert codigo(falhar(cliente, 1)[0][1]) == "login_bloqueado"


def test_bloqueio_de_um_usuario_nao_afeta_outro(cliente):
    falhar(cliente, 5)
    assert cliente.entrar("gil", SENHA)[0]["statusCode"] == 200


# --------------------------------------------------------------------------- 401 (13.2)


def test_sem_cookie_responde_401_sem_dados(cliente):
    resposta, corpo = cliente.chamar("GET", "/api/cs/fila", cookie=None)
    assert resposta["statusCode"] == 401 and codigo(corpo) == "nao_autenticado"
    assert set(corpo) == {"erro"}


@pytest.mark.parametrize("cookie", ["", "abc", "x" * 43, "!" * 43, "a" * 44, "a" * 300])
def test_cookie_malformado_ou_desconhecido_responde_401(cliente, cookie):
    resposta, corpo = cliente.chamar("GET", "/api/cs/fila", cookie=cookie)
    assert resposta["statusCode"] == 401 and codigo(corpo) == "nao_autenticado"


def test_sessao_valida_acessa_a_rota(cliente):
    cliente.entrar("ana")
    resposta, corpo = cliente.chamar("GET", "/api/cs/fila")
    assert resposta["statusCode"] == 200 and corpo == {"itens": []}


def test_endpoint_sessao_devolve_perfil_e_flag(cliente):
    cliente.entrar("gil")
    resposta, corpo = cliente.chamar("GET", "/api/cs/sessao")
    assert resposta["statusCode"] == 200
    assert corpo["usuario"] == "gil" and corpo["perfil"] == "gestor"
    assert corpo["deve_trocar_senha"] is False and corpo["inatividade_maxima_s"] == 1800
    assert cliente.chamar("GET", "/api/cs/sessao", cookie=None)[0]["statusCode"] == 401


# --------------------------------------------------------------------------- sessão (13.5)


def test_sessao_expira_apos_mais_de_30_minutos_sem_atividade(cliente):
    cliente.entrar("ana")
    cliente.avancar(minutes=30)  # exatamente 30: ainda vale
    assert cliente.chamar("GET", "/api/cs/fila")[0]["statusCode"] == 200
    cliente.avancar(minutes=30, seconds=1)
    resposta, corpo = cliente.chamar("GET", "/api/cs/fila")
    assert resposta["statusCode"] == 401 and codigo(corpo) == "nao_autenticado"
    # Expirada é expirada: não ressuscita mesmo que o relógio "volte".
    cliente.agora = INICIO
    assert cliente.chamar("GET", "/api/cs/fila")[0]["statusCode"] == 401


def test_cada_requisicao_renova_a_expiracao_deslizante(cliente):
    cliente.entrar("ana")
    for _ in range(4):  # 4 × 29 min = quase 2 h, sempre com atividade
        cliente.avancar(minutes=29)
        assert cliente.chamar("GET", "/api/cs/fila")[0]["statusCode"] == 200
    guardada = cliente.app.repos.sessoes.obter(hash_token(cliente.cookie))
    assert guardada.ultima_atividade == cliente.agora
    assert guardada.ttl == int((cliente.agora + timedelta(minutes=30)).timestamp())


def test_logout_encerra_a_sessao_e_expira_o_cookie(cliente):
    cliente.entrar("ana")
    resposta, _ = cliente.chamar("POST", "/api/cs/logout")
    assert resposta["statusCode"] == 204
    assert "Max-Age=0" in resposta["cookies"][0]
    assert cliente.chamar("GET", "/api/cs/fila")[0]["statusCode"] == 401
    assert cliente.app.repos.sessoes.obter(hash_token(cliente.cookie)) is None


def test_logout_e_idempotente_e_exige_o_cabecalho(cliente):
    assert cliente.chamar("POST", "/api/cs/logout", cookie=None)[0]["statusCode"] == 204
    cliente.entrar("ana")
    assert cliente.chamar("POST", "/api/cs/logout", csrf=False)[0]["statusCode"] == 403
    assert cliente.chamar("GET", "/api/cs/fila")[0]["statusCode"] == 200  # sessão intacta


def test_usuario_removido_perde_a_sessao_na_hora(cliente):
    cliente.entrar("ana")
    cliente.app.repos.usuarios_cs._itens.pop("ana")  # type: ignore[attr-defined]
    assert cliente.chamar("GET", "/api/cs/fila")[0]["statusCode"] == 401
    assert cliente.app.repos.sessoes.obter(hash_token(cliente.cookie)) is None


def test_perfil_e_lido_do_cadastro_a_cada_requisicao(cliente):
    cliente.entrar("gil")
    assert cliente.chamar("GET", "/api/cs/metricas")[0]["statusCode"] == 200
    from dataclasses import replace

    repo = cliente.app.repos.usuarios_cs
    repo._itens["gil"] = replace(repo._itens["gil"], perfil="atendente")  # type: ignore[attr-defined]
    assert cliente.chamar("GET", "/api/cs/metricas")[0]["statusCode"] == 403


# --------------------------------------------------------------------------- 403 (13.3, 13.4)


def test_atendente_recebe_403_sem_dados_nas_rotas_de_metricas_e_config(cliente):
    cliente.entrar("ana")
    for metodo, caminho in (("GET", "/api/cs/metricas"), ("PUT", "/api/cs/config")):
        resposta, corpo = cliente.chamar(metodo, caminho, {})
        assert resposta["statusCode"] == 403 and codigo(corpo) == "sem_permissao"
        assert set(corpo) == {"erro"}


def test_gestor_acessa_metricas_e_config(cliente):
    cliente.entrar("gil")
    resposta, corpo = cliente.chamar("GET", "/api/cs/metricas")
    assert resposta["statusCode"] == 200 and "totais" in corpo
    assert cliente.chamar("PUT", "/api/cs/config", {})[1] == {"config": 1}


def test_atendente_acessa_as_rotas_comuns_do_painel(cliente):
    cliente.entrar("ana")
    assert cliente.chamar("GET", "/api/cs/fila")[0]["statusCode"] == 200
    # A rota real valida o corpo (422 para `{}`); o que importa aqui é não ser 401/403.
    assert cliente.chamar("POST", "/api/cs/cache", {})[0]["statusCode"] not in (401, 403)


def test_rota_autenticada_fora_da_matriz_falha_fechada(cliente):
    cliente.rotas.append(Rota("GET", "/nova", lambda c: {"x": 1}, escopo="cs"))
    cliente.entrar("gil")
    resposta, corpo = cliente.chamar("GET", "/api/cs/nova")
    assert resposta["statusCode"] == 403 and codigo(corpo) == "sem_permissao"


def test_rota_pode_declarar_perfis_e_isso_vale_sobre_a_matriz(cliente):
    cliente.rotas.append(
        Rota("GET", "/so-atendente", lambda c: {"x": 1}, escopo="cs",
             perfis=frozenset({"atendente"}))
    )  # fmt: skip
    cliente.entrar("ana")
    assert cliente.chamar("GET", "/api/cs/so-atendente")[0]["statusCode"] == 200
    cliente.entrar("gil")
    assert cliente.chamar("GET", "/api/cs/so-atendente")[0]["statusCode"] == 403


# --------------------------------------------------------------------------- anti-CSRF


def test_mutacao_autenticada_sem_x_requested_with_responde_403(cliente):
    casos = (("ana", "POST", "/api/cs/cache"), ("gil", "PUT", "/api/cs/config"))
    for usuario, metodo, caminho in casos:
        cliente.entrar(usuario)
        resposta, corpo = cliente.chamar(metodo, caminho, {}, csrf=False)
        assert resposta["statusCode"] == 403 and codigo(corpo) == "cabecalho_obrigatorio"
    # Leitura não exige o cabeçalho.
    assert cliente.chamar("GET", "/api/cs/fila", csrf=False)[0]["statusCode"] == 200


def test_sem_sessao_a_resposta_continua_401_mesmo_sem_o_cabecalho(cliente):
    resposta, corpo = cliente.chamar("POST", "/api/cs/cache", {}, csrf=False, cookie=None)
    assert resposta["statusCode"] == 401 and codigo(corpo) == "nao_autenticado"


# --------------------------------------------------------------------------- composição


def test_criar_app_liga_o_autenticador_e_a_falha_fechada_continua_sem_ele(cliente):
    assert cliente.app.autenticador is not None
    from dataclasses import replace

    sem = replace(cliente.app, autenticador=None)
    cliente.entrar("ana")
    evento = {
        "rawPath": "/api/cs/fila",
        "headers": {"cookie": f"{COOKIE_SESSAO}={cliente.cookie}"},
        "requestContext": {"http": {"method": "GET"}},
    }
    resposta = processar(sem, Roteador(cliente.rotas), evento)
    assert resposta["statusCode"] == 401


def test_logs_do_login_nao_vazam_senha_nem_token(cliente, caplog):
    with caplog.at_level("INFO", logger="tres"):
        cliente.entrar("ana", "senha-errada-secreta")
        cliente.entrar("ana")
    saida = " ".join(r.getMessage() for r in caplog.records)
    assert "senha-errada-secreta" not in saida and SENHA not in saida
    assert cliente.cookie not in saida
