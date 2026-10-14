"""Camada de persistência: interfaces (Protocol), registros e fakes em memória.

Os adaptadores DynamoDB (tarefa 9.2) implementam as mesmas interfaces; o código de
negócio depende só de `repositorios.interfaces`.
"""

from repositorios.erros import ErroNaoEncontrado, ErroRepositorio
from repositorios.interfaces import Repositorios
from repositorios.memoria import criar_repositorios_memoria

__all__ = [
    "ErroNaoEncontrado",
    "ErroRepositorio",
    "Repositorios",
    "criar_repositorios_memoria",
]
