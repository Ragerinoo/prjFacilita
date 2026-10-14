"""Raiz de composição da Lambda `api`: `criar_app()` monta repositórios, config e idempotência.

Repositórios:
  * ``modo="local"`` (ou ``TRES_MODO=local``): fakes em memória, para testes e uso local;
  * qualquer outro caso: adaptadores DynamoDB (tarefa 9.2), importados SOB DEMANDA. O contrato
    esperado do módulo ``repositorios.dynamodb`` é a função
    ``criar_repositorios_dynamodb(recurso=None, prefixo="tres", ...) -> Repositorios``; o
    `prefixo` vem de ``TRES_PREFIXO`` (e um parâmetro `ambiente`, se declarado, recebe o
    mapa). Se o módulo ainda não existe, `criar_app` falha com `ErroConfiguracao` clara: NUNCA
    cai em memória em silêncio, porque isso perderia dados.
  * ``repos=...`` e ``fabrica_dynamodb=...`` permitem injeção explícita.

Variáveis de ambiente lidas (definidas pela stack da API): ``TRES_MODO``, ``TRES_PREFIXO``,
``TRES_SEGREDO_APP_ARN``, ``TRES_LOG_NIVEL`` e as ``TRES_TABELA_*`` (usadas pelo adaptador).
"""

from __future__ import annotations

import importlib
import inspect
import os
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Final

from core.config import CarregadorConfig
from core.contexto import Aplicacao, agora_utc
from core.erros import ErroConfiguracao
from core.idempotencia import Idempotencia
from core.logs import Log, configurar_logging
from repositorios.interfaces import Repositorios
from repositorios.memoria import criar_repositorios_memoria
from servicos.autenticacao import criar_autenticador
from servicos.disparador_enriquecimento import criar_disparador
from servicos.encerramento import EncerradorDeJornada, EncerradorSqs, criar_encerrador
from servicos.escalada import DisparadorEnriquecimento, ServicoEscalada
from servicos.sqs_memoria import SqsMemoria

MODO_LOCAL: Final = "local"
MODO_AWS: Final = "aws"
MODULO_DYNAMODB: Final = "repositorios.dynamodb"
FABRICA_DYNAMODB: Final = "criar_repositorios_dynamodb"
PREFIXO_PADRAO: Final = "tres"

FabricaRepositorios = Callable[..., Repositorios]


def carregar_fabrica_dynamodb() -> FabricaRepositorios:
    """Importa o adaptador DynamoDB só quando preciso (a tarefa 9.2 pode não estar pronta)."""
    try:
        modulo = importlib.import_module(MODULO_DYNAMODB)
    except ImportError as exc:
        raise ErroConfiguracao(
            f"Adaptadores DynamoDB indisponíveis ({MODULO_DYNAMODB}). "
            f"Use TRES_MODO={MODO_LOCAL} apenas em testes e desenvolvimento local."
        ) from exc
    fabrica = getattr(modulo, FABRICA_DYNAMODB, None)
    if not callable(fabrica):
        raise ErroConfiguracao(f"{MODULO_DYNAMODB} não expõe {FABRICA_DYNAMODB}()")
    return fabrica


def _chamar_fabrica(fabrica: FabricaRepositorios, ambiente: Mapping[str, str]) -> Repositorios:
    """Chama a fábrica passando só o que ela declara.

    A fábrica real é ``criar_repositorios_dynamodb(recurso=None, prefixo="tres", ...)``: recebe
    o prefixo das tabelas (``TRES_PREFIXO``, padrão ``tres``) e cria o recurso boto3 sozinha.
    Fábricas que declaram ``ambiente`` (injetadas em testes) recebem o mapeamento inteiro.
    """
    try:
        parametros = inspect.signature(fabrica).parameters
    except (TypeError, ValueError):
        parametros = {}
    argumentos: dict[str, Any] = {}
    if "prefixo" in parametros:
        argumentos["prefixo"] = ambiente.get("TRES_PREFIXO") or PREFIXO_PADRAO
    if "ambiente" in parametros:
        argumentos["ambiente"] = ambiente
    return fabrica(**argumentos)


def _nome_do_modelo(repos: Repositorios, log: Log) -> Callable[[str | None], str | None]:
    """Nome do catálogo para o Pacote_Repasse; sem catálogo, o próprio `modelo_id`.

    Lê `repos.catalogo` na hora da chamada. Falha do catálogo NUNCA atrasa nem impede a
    escalada: o Pacote usa o `modelo_id` (Req 9.10 pede escalar mesmo com dados faltando).
    """

    def nome(modelo_id: str | None) -> str | None:
        if not modelo_id:
            return None
        try:
            modelo = repos.catalogo.obter_modelo(modelo_id)
        except Exception as exc:  # noqa: BLE001
            log.aviso("nome_modelo_indisponivel", erro=exc)
            return modelo_id
        return modelo.nome if modelo is not None else modelo_id

    return nome


def criar_app(
    ambiente: Mapping[str, str] | None = None,
    *,
    modo: str | None = None,
    repos: Repositorios | None = None,
    fabrica_dynamodb: FabricaRepositorios | None = None,
    ssm: Any | None = None,
    secrets: Any | None = None,
    relogio: Callable[[], datetime] = agora_utc,
    log: Log | None = None,
    escalada: ServicoEscalada | None = None,
    encerrador: EncerradorDeJornada | None = None,
    sqs: Any | None = None,
    disparador: DisparadorEnriquecimento | None = None,
) -> Aplicacao:
    """Monta a aplicação.

    `escalada`, `encerrador`, `sqs` e `disparador` são pontos de injeção (testes):
      * `encerrador`: porta `encerrar_jornada`. Padrão: SQS real em AWS
        (``TRES_FILA_ENCERRAMENTOS_URL``; sem a variável a porta registra a falha e segue) e
        `SqsMemoria` (fake) no modo local; `sqs` substitui o cliente SQS nos dois casos.
      * `disparador`: aciona o enriquecimento do Pacote. Padrão: Lambda em AWS
        (``TRES_FUNCAO_ENRIQUECIMENTO``) e nulo no modo local.
      * `escalada`: serviço pronto; sem ele, é montado com os repositórios e o relógio da app.
    """
    env = os.environ if ambiente is None else ambiente
    modo_efetivo = modo or env.get("TRES_MODO") or MODO_AWS
    if modo_efetivo not in (MODO_LOCAL, MODO_AWS):
        raise ErroConfiguracao(f"TRES_MODO inválido: {modo_efetivo!r}")

    configurar_logging(env.get("TRES_LOG_NIVEL", "INFO"))
    log = log or Log(agora=relogio)

    if repos is None:
        if modo_efetivo == MODO_LOCAL:
            repos = criar_repositorios_memoria()
        else:
            fabrica = fabrica_dynamodb or carregar_fabrica_dynamodb()
            repos = _chamar_fabrica(fabrica, env)

    config = CarregadorConfig(
        prefixo=env.get("TRES_PREFIXO", PREFIXO_PADRAO),
        ssm=ssm,
        secrets=secrets,
        repo=repos.config,
        # Local: nunca tenta a AWS, a menos que clientes tenham sido injetados.
        usar_aws=modo_efetivo == MODO_AWS or ssm is not None or secrets is not None,
        arn_segredo_app=env.get("TRES_SEGREDO_APP_ARN") or None,
        log=log,
    )
    if encerrador is None:
        if modo_efetivo == MODO_LOCAL:
            fila = sqs if sqs is not None else SqsMemoria()
            url = env.get("TRES_FILA_ENCERRAMENTOS_URL") or getattr(fila, "fila_url", None)
            encerrador = EncerradorSqs(
                fila, url, relogio=relogio, agregados=repos.agregados, log=log
            )
        else:
            encerrador = criar_encerrador(
                env, sqs=sqs, agregados=repos.agregados, relogio=relogio, log=log
            )
    if escalada is None:
        if disparador is None and modo_efetivo == MODO_AWS:
            disparador = criar_disparador(env)
        escalada = ServicoEscalada(
            repos,
            relogio=relogio,
            disparador=disparador,
            nome_modelo=_nome_do_modelo(repos, log),
            log=log,
        )
    return Aplicacao(
        repos=repos,
        config=config,
        idempotencia=Idempotencia(repos.eventos, relogio),
        log=log,
        relogio=relogio,
        modo=modo_efetivo,
        autenticador=criar_autenticador(),  # Painel_CS (Req 13): sessão opaca + matriz de perfis
        escalada=escalada,
        encerrador=encerrador,
    )
