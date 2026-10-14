"""Erros da camada de persistência.

Falhas de condição de escrita (por exemplo "já existe", "já tem responsável") NÃO são
erros: voltam como resultado (`ResultadoCondicional.aplicado = False`), porque são
desfechos esperados do negócio. Erros são só para registro inexistente numa mutação e
para falhas de infraestrutura.
"""

from __future__ import annotations


class ErroRepositorio(Exception):
    """Falha de persistência (infraestrutura indisponível, timeout, dado inválido)."""


MENSAGEM_INDISPONIVEL_FORA_DO_MODO_LOCAL = (
    "{operacao}: indisponível fora do modo local "
    "(pendência da camada AWS: a consulta real ainda não foi implementada)"
)


class ErroIndisponivelForaDoModoLocal(ErroRepositorio):
    """Operação que só existe no Modo_Local (repositórios em memória)."""

    def __init__(self, operacao: str) -> None:
        super().__init__(MENSAGEM_INDISPONIVEL_FORA_DO_MODO_LOCAL.format(operacao=operacao))
        self.operacao = operacao


class ErroNaoEncontrado(ErroRepositorio):
    """A mutação pedida mira um registro que não existe."""

    def __init__(self, tabela: str, chave: str) -> None:
        super().__init__(f"{tabela}: registro não encontrado ({chave})")
        self.tabela = tabela
        self.chave = chave
