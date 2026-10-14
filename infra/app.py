#!/usr/bin/env python3
"""App CDK do TRES Autoatendimento.

Contexto opcional (cdk.json ou ``-c chave=valor``):
- ``prefixo``: prefixo dos nomes dos recursos (padrão ``tres``).
- ``destruir_ao_remover``: ``true`` para ambientes descartáveis (padrão ``false``, retém dados).
- ``agente_runtime_arn``: ARN do AgentCore Runtime (existe só a partir da tarefa 17.4). Sem ele,
  as Lambdas não recebem permissão de invocar o agente (nunca ``*``).
- ``origens_cors_fotos``: origens (separadas por vírgula) aceitas no POST pré-assinado de fotos.
  Padrão ``https://*.cloudfront.net``; depois do primeiro deploy, informe o domínio exato da
  distribuição (saída ``DominioCloudFront`` da stack de borda).
- ``empacotar_dependencias``: ``true`` (padrão) instala as dependências binárias das Lambdas
  (argon2-cffi etc.) com pip, sem Docker. ``false`` empacota só o código (sem rede).
"""

import os

import aws_cdk as cdk
from stacks.api_stack import ApiStack
from stacks.armazenamento_stack import ArmazenamentoStack
from stacks.borda_stack import BordaStack
from stacks.conhecimento_stack import ConhecimentoStack
from stacks.dados_stack import DadosStack


def _como_bool(valor: object) -> bool:
    return str(valor).strip().lower() in {"1", "true", "sim", "yes"}


app = cdk.App()

prefixo = app.node.try_get_context("prefixo") or "tres"
destruir = _como_bool(app.node.try_get_context("destruir_ao_remover") or False)
agente_runtime_arn = app.node.try_get_context("agente_runtime_arn") or None
empacotar = _como_bool(
    "true"
    if app.node.try_get_context("empacotar_dependencias") is None
    else app.node.try_get_context("empacotar_dependencias")
)
origens_cors_fotos = tuple(
    o.strip()
    for o in str(
        app.node.try_get_context("origens_cors_fotos") or "https://*.cloudfront.net"
    ).split(",")
    if o.strip()
)

ambiente = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("CDK_DEFAULT_REGION"),
)

dados = DadosStack(
    app,
    f"{prefixo}-dados",
    prefixo=prefixo,
    destruir_ao_remover=destruir,
    env=ambiente,
)

armazenamento = ArmazenamentoStack(
    app,
    f"{prefixo}-armazenamento",
    chave=dados.chave,
    prefixo=prefixo,
    destruir_ao_remover=destruir,
    origens_cors_fotos=origens_cors_fotos,
    env=ambiente,
)
ConhecimentoStack(
    app,
    f"{prefixo}-conhecimento",
    chave=dados.chave,
    bucket_manuais=armazenamento.bucket_manuais,
    prefixo=prefixo,
    destruir_ao_remover=destruir,
    env=ambiente,
)
api = ApiStack(
    app,
    f"{prefixo}-api",
    dados=dados,
    armazenamento=armazenamento,
    prefixo=prefixo,
    destruir_ao_remover=destruir,
    agente_runtime_arn=agente_runtime_arn,
    empacotar_dependencias=empacotar,
    env=ambiente,
)
BordaStack(
    app,
    f"{prefixo}-borda",
    bucket_site=armazenamento.bucket_site,
    bucket_fotos=armazenamento.bucket_fotos,
    dominio_api=api.dominio_api,
    nome_segredo_origem=api.nome_segredo_origem,
    prefixo=prefixo,
    env=ambiente,
)

app.synth()
