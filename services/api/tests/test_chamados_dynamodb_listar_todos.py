"""Teste unitário de `ChamadosDynamoDB.listar_todos` (persistencia-local-demo, tarefa 1.5).

O adaptador só declara o método para satisfazer o Protocol `ChamadosRepo`; a consulta real
é pendência da camada AWS. O teste não usa moto, não cria cliente boto3 e não faz rede:
a instância é criada com `__new__`, sem `_t`, o que prova que o método não toca a tabela.
"""

from __future__ import annotations

import pytest

from repositorios.dynamodb import chamados as modulo_chamados
from repositorios.dynamodb.chamados import ChamadosDynamoDB
from repositorios.erros import ErroIndisponivelForaDoModoLocal, ErroRepositorio

OPERACAO = "ChamadosDynamoDB.listar_todos"


@pytest.fixture
def adaptador() -> ChamadosDynamoDB:
    # Sem __init__: não há `_t` (tabela) nem cliente. Qualquer acesso a ele daria AttributeError.
    instancia = ChamadosDynamoDB.__new__(ChamadosDynamoDB)
    assert not hasattr(instancia, "_t")
    return instancia


def test_listar_todos_levanta_erro_indisponivel_sem_tocar_a_tabela(
    adaptador: ChamadosDynamoDB,
) -> None:
    # Req 8.5, 8.6: erro explícito, e não AttributeError (que ocorreria se usasse `self._t`).
    with pytest.raises(ErroIndisponivelForaDoModoLocal) as info:
        adaptador.listar_todos()
    assert info.value.operacao == OPERACAO


def test_erro_indisponivel_e_um_erro_repositorio(adaptador: ChamadosDynamoDB) -> None:
    # Req 8.6: o código que já trata falhas de persistência continua valendo.
    assert issubclass(ErroIndisponivelForaDoModoLocal, ErroRepositorio)
    with pytest.raises(ErroRepositorio):
        adaptador.listar_todos()


def test_mensagem_indica_modo_local_e_nome_da_operacao(adaptador: ChamadosDynamoDB) -> None:
    # Req 8.6, 12.4
    with pytest.raises(ErroIndisponivelForaDoModoLocal) as info:
        adaptador.listar_todos()
    mensagem = str(info.value)
    assert "indisponível fora do modo local" in mensagem
    assert OPERACAO in mensagem


def test_docstring_do_metodo_registra_pendencia_da_camada_aws() -> None:
    # Req 8.7
    doc = ChamadosDynamoDB.listar_todos.__doc__ or ""
    assert "PENDÊNCIA" in doc
    assert "camada AWS" in doc


def test_docstring_do_modulo_registra_pendencia_da_camada_aws() -> None:
    # Req 8.7: a pendência também aparece junto da lista de garantias do módulo.
    doc = modulo_chamados.__doc__ or ""
    assert "Pendência (camada AWS)" in doc
    assert "listar_todos" in doc
