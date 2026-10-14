"""Rota `GET /api/cs/metricas` (Painel_CS, somente Gestor) pela API real.

Passa pelo roteador, autenticador e matriz de perfis, com repositórios em memória.
Os helpers (`montar_cliente`, `criar_chamado`, `metricas`) são reutilizáveis pelos demais testes
desta rota.
"""

from __future__ import annotations

import itertools
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from repositorios.catalogo import CatalogoMemoria
from repositorios.modelos import Consentimento, EncerramentoChamado, Jornada
from servicos import senhas
from tests.test_repositorios_memoria import T0, chamado, decisao, gatilho, numero, pacote
from tests.test_rotas_cs_chamados import SENHA, Cliente

CAMINHO = "/api/cs/metricas"
CHAVES_PRIMEIRO_NIVEL = {"totais", "por_problema", "por_modelo", "por_prioridade", "por_desfecho"}

_contador = itertools.count(1)


@pytest.fixture(scope="module")
def hash_senha() -> str:
    return senhas.gerar_hash(SENHA)


def montar_cliente(hash_senha: str, *usuarios: str) -> Cliente:
    """App em memória com atendente `ana`, gestor `gil` e atendente `bia`; loga `usuarios`."""
    cliente = Cliente(hash_senha)
    for usuario in usuarios or ("ana", "gil"):
        cliente.entrar(usuario)
    return cliente


@pytest.fixture(scope="module")
def cliente(hash_senha: str) -> Cliente:
    """Cliente compartilhado (login é caro). Cada teste usa ids novos, sem limpar o estado."""
    return montar_cliente(hash_senha)


def criar_chamado(
    c: Cliente,
    *,
    prioridade: str = "P3",
    problema_id: int | None = None,
    modelo_id: str | None = None,
    resumo: str | None = None,
    desfecho: str | None = None,
) -> str:
    """Cria Jornada + Chamado (via escalada atômica) com ids únicos; opcionalmente o encerra."""
    i = next(_contador)
    jid, num = f"JM{i}", numero(i)
    repos = c.app.repos
    repos.jornadas.criar(
        Jornada(
            jid, T0, T0, "qr", "qr",
            modelo_id=modelo_id, problema_id=problema_id,
        )  # fmt: skip
    )
    base = chamado(num, jid, prioridade, T0 + timedelta(seconds=i))
    if resumo is not None:
        base = replace(base, pacote=replace(pacote(num, prioridade), resumo=resumo))
    resultado = repos.chamados.criar_com_escalada(base, gatilho(), decisao(prioridade))
    assert resultado.criado
    if desfecho is not None:
        enc = EncerramentoChamado(desfecho, "outra", "ok", T0, "gil")  # type: ignore[arg-type]
        assert repos.chamados.encerrar(num, enc).aplicado
    return num


def metricas(c: Cliente, quem: str | None = "gil"):
    """`(resposta, corpo)` de `GET /api/cs/metricas`; `quem=None` chama sem sessão."""
    return c.chamar("GET", CAMINHO, quem=quem)


# Marcadores únicos: dígitos de comprimento fixo (telefone/CEP) e tokens alfanuméricos.
telefones = st.integers(10**10, 10**11 - 1).map(str)
ceps = st.integers(10**7, 10**8 - 1).map(str)
tokens = st.text(alphabet="abcdefghjkmnpqrstvwxyz", min_size=8, max_size=12)


@st.composite
def chamados_com_dados(draw):
    """Lista de Chamados com telefone/CEP, mensagens e resumo distintivos."""
    n = draw(st.integers(1, 4))
    itens = []
    for k in range(n):
        itens.append(
            {
                "telefone": draw(telefones),
                "cep": draw(ceps),
                "textos": [f"msg-{k}-{draw(tokens)}" for _ in range(draw(st.integers(1, 3)))],
                "resumo": f"resumo-{k}-{draw(tokens)}",
                "prioridade": draw(st.sampled_from(("P1", "P2", "P3"))),
                "problema_id": draw(st.none() | st.integers(1, 5)),
                "modelo_id": draw(st.none() | st.sampled_from(("m1", "m2", "m3"))),
                "desfecho": draw(st.sampled_from((None, "falso_defeito", "defeito_real"))),
            }
        )
    return itens


@given(itens=chamados_com_dados())
def test_propriedade_resposta_de_metricas_nao_vaza_dados(cliente: Cliente, itens) -> None:
    """Feature: persistencia-local-demo, Property 13: A resposta de métricas não vaza dados
    **Validates: Requirements 9.13, 9.14**
    """
    repos = cliente.app.repos
    segredos: list[str] = []
    for item in itens:
        num = criar_chamado(
            cliente,
            prioridade=item["prioridade"],
            problema_id=item["problema_id"],
            modelo_id=item["modelo_id"],
            resumo=item["resumo"],
            desfecho=item["desfecho"],
        )
        repos.dados_pessoais.salvar(
            num, Consentimento(T0, "v1"), telefone=item["telefone"], cep=item["cep"]
        )
        for texto in item["textos"]:
            repos.mensagens.adicionar(num, "consumidor", texto, T0)
        segredos += [item["telefone"], item["cep"], item["resumo"], *item["textos"]]

    resposta, corpo = metricas(cliente)

    assert resposta["statusCode"] == 200
    for segredo in segredos:
        assert segredo not in resposta["body"]
    assert set(corpo) == CHAVES_PRIMEIRO_NIVEL


# Credenciais inválidas: cookie ausente, valor arbitrário/malformado ou token válido adulterado.
valores_cookie = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.=~%:/+", max_size=80
)
credenciais_invalidas = st.one_of(
    st.just(("ausente", "")),
    valores_cookie.map(lambda v: ("arbitrario", v)),
    valores_cookie.map(lambda v: ("adulterado", v)),
)


@given(
    itens=chamados_com_dados(),
    credencial=st.one_of(
        st.just(("gestor", "")), st.just(("atendente", "")), credenciais_invalidas
    ),
)
def test_propriedade_autorizacao_da_rota_de_metricas(cliente: Cliente, itens, credencial) -> None:
    """Feature: persistencia-local-demo, Property 14: Autorização da rota de métricas
    **Validates: Requirements 9.11, 9.12, 9.15**
    """
    for item in itens:
        criar_chamado(
            cliente,
            prioridade=item["prioridade"],
            problema_id=item["problema_id"],
            modelo_id=item["modelo_id"],
            resumo=item["resumo"],
            desfecho=item["desfecho"],
        )

    tipo, valor = credencial
    if tipo == "gestor":
        quem = "gil"
    elif tipo == "atendente":
        quem = "ana"
    elif tipo == "ausente":
        quem = None
    else:
        base = cliente.cookies["gil"] if tipo == "adulterado" else ""
        cliente.cookies["invalido"] = base + valor
        quem = "invalido"
        # A propriedade só vale para credenciais realmente inválidas.
        assume(cliente.cookies["invalido"] not in (cliente.cookies["gil"], cliente.cookies["ana"]))

    resposta, corpo = metricas(cliente, quem=quem)

    if tipo == "gestor":
        assert resposta["statusCode"] == 200
        assert set(corpo) == CHAVES_PRIMEIRO_NIVEL
    else:
        assert resposta["statusCode"] == (403 if tipo == "atendente" else 401)
        # Sem nenhuma contagem: o corpo não traz totais nem agrupamentos.
        assert not (CHAVES_PRIMEIRO_NIVEL & set(corpo or {}))
        for chave in CHAVES_PRIMEIRO_NIVEL:
            assert chave not in resposta["body"]

    # Matriz de autorização: rota exclusiva do perfil gestor.
    # Import tardio: `servicos.autorizacao` só importa limpo depois de `core` (ciclo existente).
    from servicos import autorizacao

    assert autorizacao.perfis_permitidos("GET", "/metricas") == frozenset({"gestor"})


# --------------------------------------------------------------------------------------------
# Testes por exemplo (Req 9.1, 9.9, 9.10, 9.11, 9.12, 12.5). Cada um usa um app novo, para que
# as contagens sejam exatas (o `cliente` compartilhado acumula Chamados dos testes de propriedade).
# --------------------------------------------------------------------------------------------
def _catalogo_com(*problemas: tuple[int, str]) -> CatalogoMemoria:
    return CatalogoMemoria.de_itens(
        problemas=[
            {"problema_id": pid, "ordem": pid, "titulo": titulo, "icone": "i", "icone_alt": "a"}
            for pid, titulo in problemas
        ]
    )


def _cliente_novo(hash_senha: str, *usuarios: str) -> Cliente:
    """App isolado, com catálogo de dois Problemas (1 e 2); o id 3 fica fora do catálogo."""
    c = montar_cliente(hash_senha, *usuarios)
    object.__setattr__(
        c.app.repos, "catalogo", _catalogo_com((1, "Não liga"), (2, "Não esquenta"))
    )
    return c


def _linhas(corpo: dict, dimensao: str) -> dict[str, tuple[str, int]]:
    return {x["chave"]: (x["rotulo"], x["quantidade"]) for x in corpo[dimensao]}


def _cenario_misto(c: Cliente) -> None:
    """5 Chamados: 3 abertos (P1, P2, P2) e 2 encerrados (P3 falso_defeito, P3 defeito_real)."""
    criar_chamado(c, prioridade="P1", problema_id=1, modelo_id="m1")
    criar_chamado(c, prioridade="P2", problema_id=1, modelo_id="m1")
    criar_chamado(c, prioridade="P2", problema_id=2, modelo_id="m2")
    criar_chamado(c, prioridade="P3", problema_id=3, modelo_id=None, desfecho="falso_defeito")
    criar_chamado(c, prioridade="P3", problema_id=None, modelo_id="m1", desfecho="defeito_real")


def test_gestor_200_com_contagens_esperadas(hash_senha: str) -> None:
    c = _cliente_novo(hash_senha, "gil")
    _cenario_misto(c)

    resposta, corpo = metricas(c)

    assert resposta["statusCode"] == 200
    assert set(corpo) == CHAVES_PRIMEIRO_NIVEL
    assert corpo["totais"] == {"abertos": 3, "encerrados": 2}
    # Título do catálogo; id fora do catálogo vira "Problema N"; sem problema, "nao_informado".
    assert _linhas(corpo, "por_problema") == {
        "1": ("Não liga", 2),
        "2": ("Não esquenta", 1),
        "3": ("Problema 3", 1),
        "nao_informado": ("nao_informado", 1),
    }
    assert _linhas(corpo, "por_modelo") == {
        "m1": ("m1", 3),
        "m2": ("m2", 1),
        "nao_informado": ("nao_informado", 1),
    }
    assert [x["quantidade"] for x in corpo["por_modelo"]] == [3, 1, 1]  # decrescente
    assert corpo["por_problema"][0]["rotulo"] == "Não liga"
    assert [(x["chave"], x["quantidade"]) for x in corpo["por_prioridade"]] == [
        ("P1", 1), ("P2", 2), ("P3", 2),
    ]  # fmt: skip
    assert [(x["chave"], x["quantidade"]) for x in corpo["por_desfecho"]] == [
        ("falso_defeito", 1), ("defeito_real", 1),
    ]  # fmt: skip


def test_prioridades_sem_chamados_aparecem_com_zero(hash_senha: str) -> None:
    c = _cliente_novo(hash_senha, "gil")
    criar_chamado(c, prioridade="P2", problema_id=1, modelo_id="m1")

    _, corpo = metricas(c)

    assert [(x["chave"], x["quantidade"]) for x in corpo["por_prioridade"]] == [
        ("P1", 0), ("P2", 1), ("P3", 0),
    ]  # fmt: skip
    # Sem encerrados, os dois desfechos fixos continuam presentes, com zero.
    assert [(x["chave"], x["quantidade"]) for x in corpo["por_desfecho"]] == [
        ("falso_defeito", 0), ("defeito_real", 0),
    ]  # fmt: skip


def test_atendente_recebe_403_sem_contagens(hash_senha: str) -> None:
    c = _cliente_novo(hash_senha, "ana", "gil")
    _cenario_misto(c)

    resposta, corpo = metricas(c, quem="ana")

    assert resposta["statusCode"] == 403
    assert not (CHAVES_PRIMEIRO_NIVEL & set(corpo or {}))
    for chave in CHAVES_PRIMEIRO_NIVEL:
        assert chave not in resposta["body"]


def test_sem_sessao_recebe_401_sem_contagens(cliente: Cliente) -> None:
    resposta, corpo = metricas(cliente, quem=None)

    assert resposta["statusCode"] == 401
    assert not (CHAVES_PRIMEIRO_NIVEL & set(corpo or {}))
    for chave in CHAVES_PRIMEIRO_NIVEL:
        assert chave not in resposta["body"]


def test_sem_chamados_devolve_200_com_totais_zero(hash_senha: str) -> None:
    c = _cliente_novo(hash_senha, "gil")  # app novo: nenhum Chamado criado

    resposta, corpo = metricas(c)

    assert resposta["statusCode"] == 200
    assert corpo["totais"] == {"abertos": 0, "encerrados": 0}
    assert corpo["por_problema"] == []
    assert corpo["por_modelo"] == []
    assert [x["quantidade"] for x in corpo["por_prioridade"]] == [0, 0, 0]
    assert [x["quantidade"] for x in corpo["por_desfecho"]] == [0, 0]


def test_soma_das_dimensoes_bate_com_os_totais(hash_senha: str) -> None:
    c = _cliente_novo(hash_senha, "gil")
    _cenario_misto(c)

    _, corpo = metricas(c)

    total = corpo["totais"]["abertos"] + corpo["totais"]["encerrados"]
    assert total == 5
    for dimensao in ("por_problema", "por_modelo", "por_prioridade"):
        assert sum(x["quantidade"] for x in corpo[dimensao]) == total, dimensao
    assert sum(x["quantidade"] for x in corpo["por_desfecho"]) == corpo["totais"]["encerrados"]


def test_chamado_encerrado_entra_em_encerrados_e_no_desfecho(hash_senha: str) -> None:
    c = _cliente_novo(hash_senha, "gil")
    criar_chamado(c, prioridade="P1", problema_id=1, modelo_id="m1")
    antes = metricas(c)[1]
    assert antes["totais"] == {"abertos": 1, "encerrados": 0}

    criar_chamado(c, prioridade="P1", problema_id=1, modelo_id="m1", desfecho="defeito_real")
    depois = metricas(c)[1]

    assert depois["totais"] == {"abertos": 1, "encerrados": 1}
    assert _linhas(depois, "por_desfecho") == {
        "falso_defeito": ("falso_defeito", 0),
        "defeito_real": ("defeito_real", 1),
    }
    assert _linhas(depois, "por_prioridade")["P1"] == ("P1", 2)  # encerrado ainda conta aqui


def test_contagens_refletem_estado_recarregado_do_snapshot(hash_senha: str, tmp_path) -> None:
    # `scripts/` não está no sys.path dos testes da API; o módulo faz o próprio bootstrap do resto.
    raiz = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(raiz / "scripts"))
    try:
        from estado_demo import Persistencia, aplicar_estado
    finally:
        sys.path.remove(str(raiz / "scripts"))

    origem = _cliente_novo(hash_senha, "gil")
    _cenario_misto(origem)
    esperado = metricas(origem)[1]
    persistencia = Persistencia(tmp_path)
    assert persistencia.gravar(origem.app.repos)

    reiniciado = _cliente_novo(hash_senha, "gil")  # app novo e vazio, como após reiniciar a API
    assert metricas(reiniciado)[1]["totais"] == {"abertos": 0, "encerrados": 0}
    aplicar_estado(reiniciado.app.repos, persistencia.carregar())

    resposta, corpo = metricas(reiniciado)

    assert resposta["statusCode"] == 200
    assert corpo == esperado
