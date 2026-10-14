"""Matriz de autorização perfil × rota (função pura) e decorator `exigir_perfil` (Req 13.2-13.4)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.erros import ErroApi
from servicos.autorizacao import (
    MATRIZ,
    Acesso,
    decidir_acesso,
    exigir_perfil,
    normalizar_caminho,
    perfis_permitidos,
)

ROTAS_DO_DESIGN = [
    ("GET", "/fila"),
    ("GET", "/chamados/{numero}"),
    ("POST", "/chamados/{numero}/assumir"),
    ("GET", "/chamados/{numero}/dados-pessoais"),
    ("GET", "/chamados/{numero}/anexos/{indice}"),
    ("GET", "/chamados/{numero}/sugestao"),
    ("POST", "/chamados/{numero}/mensagens"),
    ("POST", "/chamados/{numero}/ordem-servico"),
    ("POST", "/chamados/{numero}/agendamento"),
    ("POST", "/chamados/{numero}/encerrar"),
    ("POST", "/cache"),
    ("GET", "/sessao"),
]
ROTAS_DO_GESTOR = [("GET", "/metricas"), ("PUT", "/config")]


@pytest.mark.parametrize(("metodo", "caminho"), ROTAS_DO_DESIGN)
def test_rotas_comuns_aceitam_os_dois_perfis(metodo, caminho):
    for perfil in ("atendente", "gestor"):
        assert decidir_acesso(True, perfil, metodo, caminho) is Acesso.PERMITIDO


@pytest.mark.parametrize(("metodo", "caminho"), ROTAS_DO_GESTOR)
def test_metricas_e_config_so_para_gestor(metodo, caminho):
    assert decidir_acesso(True, "gestor", metodo, caminho) is Acesso.PERMITIDO
    assert decidir_acesso(True, "atendente", metodo, caminho) is Acesso.SEM_PERMISSAO


@pytest.mark.parametrize(("metodo", "caminho"), ROTAS_DO_DESIGN + ROTAS_DO_GESTOR)
@pytest.mark.parametrize("perfil", ["atendente", "gestor", None, "", "admin"])
def test_credencial_invalida_e_sempre_401(metodo, caminho, perfil):
    assert decidir_acesso(False, perfil, metodo, caminho) is Acesso.NAO_AUTENTICADO


def test_perfil_desconhecido_ou_ausente_nunca_passa():
    assert decidir_acesso(True, None, "GET", "/fila") is Acesso.NAO_AUTENTICADO
    assert decidir_acesso(True, "admin", "GET", "/fila") is Acesso.SEM_PERMISSAO
    assert decidir_acesso(True, "admin", "GET", "/fila", frozenset({"admin"})) is (
        Acesso.SEM_PERMISSAO
    )


def test_rota_fora_da_matriz_nega_a_todos_e_perfis_da_rota_prevalecem():
    assert perfis_permitidos("GET", "/inexistente") == frozenset()
    assert decidir_acesso(True, "gestor", "GET", "/inexistente") is Acesso.SEM_PERMISSAO
    assert decidir_acesso(True, "atendente", "GET", "/x", frozenset({"atendente"})) is (
        Acesso.PERMITIDO
    )


def test_metodo_faz_parte_da_chave_da_rota():
    assert decidir_acesso(True, "atendente", "DELETE", "/config") is Acesso.SEM_PERMISSAO
    assert decidir_acesso(True, "atendente", "GET", "/config") is Acesso.SEM_PERMISSAO
    assert decidir_acesso(True, "atendente", "get", "/fila") is Acesso.PERMITIDO


def test_nome_do_parametro_nao_importa_no_casamento():
    assert normalizar_caminho("/chamados/{n}/assumir") == normalizar_caminho(
        "/chamados/{numero}/assumir"
    )
    assert perfis_permitidos("POST", "/chamados/{n}/assumir")


def test_matriz_cobre_exatamente_as_rotas_do_design():
    esperadas = {(m, normalizar_caminho(c)) for m, c in ROTAS_DO_DESIGN + ROTAS_DO_GESTOR}
    assert set(MATRIZ) == esperadas


# --------------------------------------------------------------------------- decorator


def ctx(perfil):
    usuario = None if perfil is None else SimpleNamespace(perfil=perfil)
    return SimpleNamespace(usuario=usuario)


def test_decorator_deixa_passar_o_perfil_certo():
    @exigir_perfil("gestor")
    def handler(c):
        return "ok"

    assert handler(ctx("gestor")) == "ok"
    assert handler.__name__ == "handler"


def test_decorator_recusa_com_403_e_401():
    @exigir_perfil("gestor")
    def handler(c):
        raise AssertionError("não deveria executar")

    with pytest.raises(ErroApi) as erro:
        handler(ctx("atendente"))
    assert erro.value.status == 403
    with pytest.raises(ErroApi) as erro:
        handler(ctx(None))
    assert erro.value.status == 401


def test_decorator_rejeita_perfil_invalido_na_declaracao():
    with pytest.raises(ValueError):
        exigir_perfil("admin")
    with pytest.raises(ValueError):
        exigir_perfil()
