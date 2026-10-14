"""Núcleo da Lambda `api`: roteador, envelope de erro, validação, idempotência, logs e config."""

from core.app import criar_app
from core.contexto import Aplicacao, Contexto
from core.erros import ErroApi, ErroConfiguracao
from core.http import Requisicao, Resposta
from core.processamento import processar
from core.roteador import Rota, Roteador, criar_roteador, descobrir_rotas

__all__ = [
    "Aplicacao",
    "Contexto",
    "ErroApi",
    "ErroConfiguracao",
    "Requisicao",
    "Resposta",
    "Roteador",
    "Rota",
    "criar_app",
    "criar_roteador",
    "descobrir_rotas",
    "processar",
]
