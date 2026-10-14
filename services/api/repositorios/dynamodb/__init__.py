"""Adaptadores DynamoDB dos repositórios (tarefa 9.2).

Cada adaptador satisfaz o `Protocol` correspondente de `repositorios.interfaces` com as
mesmas garantias condicionais dos fakes em memória. Tabelas e índices: `infra/stacks/
dados_stack.py` (nomes `<prefixo>-<tabela>`, `gsi_ativas`, `gsi_encerradas`, `gsi_fila`).

Uso:

    recurso = criar_recurso_dynamodb(region_name="us-east-1")   # timeouts curtos (Req 20.6)
    repos = criar_repositorios_dynamodb(recurso, prefixo="tres")

O recurso é injetado, então os testes passam um `boto3.resource` sob `moto`. Condição de
escrita não satisfeita volta como resultado (`aplicado=False`); falha de infraestrutura
(timeout, indisponibilidade, limitação de vazão) levanta `ErroRepositorio`, sem confirmar
sucesso (Req 20.6).
"""

from __future__ import annotations

from typing import Any

from repositorios.dynamodb._base import (
    ORCAMENTO_GRAVACAO_S,
    TENTATIVAS_MAX,
    TIMEOUT_CONEXAO_S,
    TIMEOUT_LEITURA_S,
    config_cliente_curta,
    config_cliente_leitura_cache,
    criar_recurso_dynamodb,
    pior_caso_chamada_s,
)
from repositorios.dynamodb.atendimento import (
    AcessosPIIDynamoDB,
    DadosPessoaisDynamoDB,
    EventosDynamoDB,
    MensagensChamadoDynamoDB,
    OrdensServicoDynamoDB,
)
from repositorios.dynamodb.cache_metricas import (
    AgregadosDiaDynamoDB,
    AvaliacoesDynamoDB,
    CacheRespostasDynamoDB,
    ConfigDynamoDB,
)
from repositorios.dynamodb.catalogo import CatalogoDynamoDB
from repositorios.dynamodb.chamados import ChamadosDynamoDB
from repositorios.dynamodb.jornadas import JornadasDynamoDB
from repositorios.dynamodb.painel import SessoesCSDynamoDB, UsuariosCSDynamoDB
from repositorios.interfaces import Repositorios


def criar_repositorios_dynamodb(
    recurso: Any | None = None,
    prefixo: str = "tres",
    *,
    recurso_leitura_cache: Any | None = None,
) -> Repositorios:
    """Conjunto completo de repositórios sobre DynamoDB.

    `recurso`: `boto3.resource("dynamodb")` injetado. Sem ele, cria um com
    `config_cliente_curta()`. `prefixo`: prefixo dos nomes de tabela (`tres` -> `tres-jornadas`).
    `recurso_leitura_cache`: recurso com `config_cliente_leitura_cache()` (2 s) para a leitura
    do Cache_Respostas; sem ele, a leitura usa `recurso`.
    """
    if recurso is None:
        recurso = criar_recurso_dynamodb()
    return Repositorios(
        jornadas=JornadasDynamoDB(recurso, prefixo),
        eventos=EventosDynamoDB(recurso, prefixo),
        chamados=ChamadosDynamoDB(recurso, prefixo),
        mensagens=MensagensChamadoDynamoDB(recurso, prefixo),
        dados_pessoais=DadosPessoaisDynamoDB(recurso, prefixo),
        acessos_pii=AcessosPIIDynamoDB(recurso, prefixo),
        ordens_servico=OrdensServicoDynamoDB(recurso, prefixo),
        cache=CacheRespostasDynamoDB(recurso, prefixo, recurso_leitura_cache),
        avaliacoes=AvaliacoesDynamoDB(recurso, prefixo),
        agregados=AgregadosDiaDynamoDB(recurso, prefixo),
        usuarios_cs=UsuariosCSDynamoDB(recurso, prefixo),
        sessoes=SessoesCSDynamoDB(recurso, prefixo),
        config=ConfigDynamoDB(recurso, prefixo),
        catalogo=CatalogoDynamoDB(recurso, prefixo),
    )


__all__ = [
    "ORCAMENTO_GRAVACAO_S",
    "TENTATIVAS_MAX",
    "TIMEOUT_CONEXAO_S",
    "TIMEOUT_LEITURA_S",
    "AcessosPIIDynamoDB",
    "AgregadosDiaDynamoDB",
    "AvaliacoesDynamoDB",
    "CacheRespostasDynamoDB",
    "CatalogoDynamoDB",
    "ChamadosDynamoDB",
    "ConfigDynamoDB",
    "DadosPessoaisDynamoDB",
    "EventosDynamoDB",
    "JornadasDynamoDB",
    "MensagensChamadoDynamoDB",
    "OrdensServicoDynamoDB",
    "SessoesCSDynamoDB",
    "UsuariosCSDynamoDB",
    "config_cliente_curta",
    "config_cliente_leitura_cache",
    "criar_recurso_dynamodb",
    "criar_repositorios_dynamodb",
    "pior_caso_chamada_s",
]
