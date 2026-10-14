"""Infraestrutura comum dos adaptadores DynamoDB (tarefa 9.2).

Reúne:
  * a configuração de cliente com timeouts curtos (Req 20.6);
  * a (de)serialização de horários e números (ISO UTC de largura fixa, `Decimal`);
  * `Tabela`, um invólucro fino sobre `Table` do boto3 que traduz erros de infraestrutura
    para `ErroRepositorio` e falhas de condição para um resultado (nunca exceção);
  * `executar_transacao`, o `TransactWriteItems` com leitura dos motivos de cancelamento.

As mensagens de erro citam só tabela, operação e código do erro: nunca valores de itens,
porque itens podem conter dados pessoais.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Final

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from repositorios.erros import ErroNaoEncontrado, ErroRepositorio

# ----------------------------------------------------------------------------- timeouts

# Req 20.6: gravação que falha ou passa de 10 s vira erro ao usuário. O orçamento de uma
# chamada ao DynamoDB é: tentativas × (conexão + leitura) + espera entre as tentativas.
TIMEOUT_CONEXAO_S: Final = 1.0
TIMEOUT_LEITURA_S: Final = 3.0
TENTATIVAS_MAX: Final = 2  # 1 chamada + 1 nova tentativa
ORCAMENTO_GRAVACAO_S: Final = 10.0

# Cache_Respostas: leitura com timeout de 2 s; falha ou timeout vale como "miss" (Req 7.8).
TIMEOUT_CONEXAO_CACHE_S: Final = 0.5
TIMEOUT_LEITURA_CACHE_S: Final = 1.5

# Quantas vezes uma operação otimista (ler, decidir, gravar com condição) é repetida
# quando outra escrita muda o item no meio do caminho.
TENTATIVAS_OTIMISTAS: Final = 3


def pior_caso_chamada_s(
    conexao_s: float = TIMEOUT_CONEXAO_S,
    leitura_s: float = TIMEOUT_LEITURA_S,
    tentativas: int = TENTATIVAS_MAX,
) -> float:
    """Tempo máximo de uma chamada ao DynamoDB com a configuração dada.

    O modo "standard" do botocore espera menos de `2 ** (n - 1)` s antes da n-ésima nova
    tentativa; contamos o teto.
    """
    espera = sum(2.0**i for i in range(max(0, tentativas - 1)))
    return tentativas * (conexao_s + leitura_s) + espera


def config_cliente_curta() -> Config:
    """Config do cliente: timeouts curtos e poucas tentativas (pior caso ~9 s, Req 20.6).

    Atenção: uma nova tentativa depois de timeout numa escrita condicional que na verdade
    chegou ao servidor volta como "condição não satisfeita". É o preço de respeitar os 10 s;
    `TransactWriteItems` não sofre disso (o boto3 reenvia o mesmo `ClientRequestToken`).
    """
    return Config(
        connect_timeout=TIMEOUT_CONEXAO_S,
        read_timeout=TIMEOUT_LEITURA_S,
        retries={"total_max_attempts": TENTATIVAS_MAX, "mode": "standard"},
        tcp_keepalive=True,
    )


def config_cliente_leitura_cache() -> Config:
    """Config para a leitura do cache: 2 s no total, sem nova tentativa (Req 7.8)."""
    return Config(
        connect_timeout=TIMEOUT_CONEXAO_CACHE_S,
        read_timeout=TIMEOUT_LEITURA_CACHE_S,
        retries={"total_max_attempts": 1, "mode": "standard"},
        tcp_keepalive=True,
    )


def criar_recurso_dynamodb(
    region_name: str | None = None,
    endpoint_url: str | None = None,
    config: Config | None = None,
) -> Any:
    """`boto3.resource("dynamodb")` com a config de timeouts curtos."""
    import boto3

    return boto3.resource(
        "dynamodb",
        region_name=region_name,
        endpoint_url=endpoint_url,
        config=config or config_cliente_curta(),
    )


# ----------------------------------------------------------------------------- horários


def dt_str(valor: datetime) -> str:
    """ISO 8601 em UTC, largura fixa com microssegundos: ordena como texto (chaves de GSI)."""
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ValueError("datetime deve ter fuso horário (datetime ciente de fuso)")
    return valor.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def str_dt(texto: str) -> datetime:
    return datetime.fromisoformat(texto)


def dt_opt(texto: str | None) -> datetime | None:
    return None if texto is None else str_dt(texto)


# ----------------------------------------------------------------------------- valores


def para_dynamo(valor: Any) -> Any:
    """Converte um valor Python "tipo JSON" para o que o boto3 aceita.

    `float` vira `Decimal` (o DynamoDB não aceita float) e `tuple` vira lista.
    """
    if valor is None or isinstance(valor, bool | str | int | Decimal):
        return valor
    if isinstance(valor, float):
        if not math.isfinite(valor):
            raise ValueError("número não finito não pode ser gravado")
        return Decimal(repr(valor))
    if isinstance(valor, Mapping):
        return {str(k): para_dynamo(v) for k, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [para_dynamo(v) for v in valor]
    raise TypeError(f"tipo não suportado para o DynamoDB: {type(valor).__name__}")


def de_dynamo(valor: Any, *, fracionario_como_float: bool = True) -> Any:
    """Inverso de `para_dynamo`: `Decimal` inteiro vira `int`; fracionário vira `float`
    (ou continua `Decimal` com `fracionario_como_float=False`)."""
    if isinstance(valor, Decimal):
        if valor == valor.to_integral_value():
            return int(valor)
        return float(valor) if fracionario_como_float else valor
    if isinstance(valor, Mapping):
        return {
            k: de_dynamo(v, fracionario_como_float=fracionario_como_float) for k, v in valor.items()
        }
    if isinstance(valor, list | tuple):
        return [de_dynamo(v, fracionario_como_float=fracionario_como_float) for v in valor]
    return valor


def sem_nulos(item: dict[str, Any]) -> dict[str, Any]:
    """Remove atributos `None` (atributo ausente, não NULL: mantém os índices esparsos)."""
    return {k: v for k, v in item.items() if v is not None}


# ----------------------------------------------------------------------------- erros

_CONDICAO_FALHOU: Final = "ConditionalCheckFailedException"
_TRANSACAO_CANCELADA: Final = "TransactionCanceledException"


def _codigo(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", "desconhecido"))


def _erro(tabela: str, operacao: str, exc: Exception) -> ErroRepositorio:
    detalhe = _codigo(exc) if isinstance(exc, ClientError) else type(exc).__name__
    return ErroRepositorio(f"{tabela}: {operacao} falhou ({detalhe})")


def _sem_vazios(
    nomes: Mapping[str, str] | None, valores: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Argumentos opcionais de expressão (o DynamoDB recusa mapas vazios)."""
    extra: dict[str, Any] = {}
    if nomes:
        extra["ExpressionAttributeNames"] = dict(nomes)
    if valores:
        extra["ExpressionAttributeValues"] = dict(valores)
    return extra


# ----------------------------------------------------------------------------- Tabela


class Tabela:
    """Tabela do DynamoDB com tradução de erros.

    Leituras da tabela base são fortemente consistentes por padrão. Operações condicionais
    devolvem "aplicado" (bool) em vez de levantar quando a condição falha.
    """

    def __init__(
        self, recurso: Any, nome_fisico: str, logico: str, pk: str, sk: str | None = None
    ) -> None:
        self.nome = nome_fisico
        self.logico = logico
        self.pk = pk
        self.sk = sk
        self.cliente = recurso.meta.client
        self._t = recurso.Table(nome_fisico)

    # -- auxiliares ---------------------------------------------------------------------

    def chave(self, pk: Any, sk: Any = None) -> dict[str, Any]:
        chave = {self.pk: pk}
        if self.sk is not None:
            chave[self.sk] = sk
        return chave

    def chave_texto(self, chave: Mapping[str, Any]) -> str:
        return "/".join(str(chave[n]) for n in (self.pk, self.sk) if n is not None)

    def nao_encontrado(self, chave: Mapping[str, Any]) -> ErroNaoEncontrado:
        return ErroNaoEncontrado(self.logico, self.chave_texto(chave))

    # -- leitura ------------------------------------------------------------------------

    def obter(
        self,
        chave: Mapping[str, Any],
        *,
        consistente: bool = True,
        projecao: str | None = None,
        nomes: Mapping[str, str] | None = None,
    ) -> dict[str, Any] | None:
        args: dict[str, Any] = {"Key": dict(chave), "ConsistentRead": consistente}
        if projecao:
            args["ProjectionExpression"] = projecao
            args.update(_sem_vazios(nomes, None))
        try:
            resposta = self._t.get_item(**args)
        except (ClientError, BotoCoreError) as exc:
            raise _erro(self.logico, "get_item", exc) from exc
        return resposta.get("Item")

    def consultar(
        self,
        condicao: str,
        nomes: Mapping[str, str],
        valores: Mapping[str, Any],
        *,
        indice: str | None = None,
        ascendente: bool = True,
        consistente: bool | None = None,
        filtro: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query com paginação completa. Índices secundários não aceitam leitura consistente."""
        args: dict[str, Any] = {
            "KeyConditionExpression": condicao,
            "ScanIndexForward": ascendente,
            **_sem_vazios(nomes, valores),
        }
        if indice:
            args["IndexName"] = indice
        else:
            args["ConsistentRead"] = True if consistente is None else consistente
        if filtro:
            args["FilterExpression"] = filtro
        itens: list[dict[str, Any]] = []
        while True:
            try:
                resposta = self._t.query(**args)
            except (ClientError, BotoCoreError) as exc:
                raise _erro(self.logico, "query", exc) from exc
            itens.extend(resposta.get("Items", []))
            ultima = resposta.get("LastEvaluatedKey")
            if not ultima:
                return itens
            args["ExclusiveStartKey"] = ultima

    def varrer(
        self,
        filtro: str | None = None,
        nomes: Mapping[str, str] | None = None,
        valores: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Scan com paginação completa (só para tabelas pequenas: config, métricas)."""
        args: dict[str, Any] = {"ConsistentRead": True, **_sem_vazios(nomes, valores)}
        if filtro:
            args["FilterExpression"] = filtro
        itens: list[dict[str, Any]] = []
        while True:
            try:
                resposta = self._t.scan(**args)
            except (ClientError, BotoCoreError) as exc:
                raise _erro(self.logico, "scan", exc) from exc
            itens.extend(resposta.get("Items", []))
            ultima = resposta.get("LastEvaluatedKey")
            if not ultima:
                return itens
            args["ExclusiveStartKey"] = ultima

    # -- escrita ------------------------------------------------------------------------

    def gravar(
        self,
        item: Mapping[str, Any],
        condicao: str | None = None,
        nomes: Mapping[str, str] | None = None,
        valores: Mapping[str, Any] | None = None,
    ) -> bool:
        """`PutItem`. Devolve False se a condição de escrita não foi satisfeita."""
        args: dict[str, Any] = {"Item": dict(item), **_sem_vazios(nomes, valores)}
        if condicao:
            args["ConditionExpression"] = condicao
        try:
            self._t.put_item(**args)
        except ClientError as exc:
            if _codigo(exc) == _CONDICAO_FALHOU:
                return False
            raise _erro(self.logico, "put_item", exc) from exc
        except BotoCoreError as exc:
            raise _erro(self.logico, "put_item", exc) from exc
        return True

    def atualizar(
        self,
        chave: Mapping[str, Any],
        expressao: str,
        nomes: Mapping[str, str] | None = None,
        valores: Mapping[str, Any] | None = None,
        condicao: str | None = None,
        *,
        criar_se_ausente: bool = False,
    ) -> tuple[bool, dict[str, Any]]:
        """`UpdateItem` que NUNCA cria item por engano.

        Acrescenta `attribute_exists(<pk>)` à condição (salvo `criar_se_ausente`, para
        upserts de propósito). Devolve `(aplicado, item)`: o item novo se aplicado; se a
        condição falhou, o item como está agora. Item inexistente levanta
        `ErroNaoEncontrado`.
        """
        todos_nomes = dict(nomes or {})
        partes = [condicao] if condicao else []
        if not criar_se_ausente:
            todos_nomes["#_pk"] = self.pk
            partes.insert(0, "attribute_exists(#_pk)")
        args: dict[str, Any] = {
            "Key": dict(chave),
            "UpdateExpression": expressao,
            "ReturnValues": "ALL_NEW",
            **_sem_vazios(todos_nomes, valores),
        }
        if partes:
            args["ConditionExpression"] = " AND ".join(f"({p})" for p in partes)
        try:
            resposta = self._t.update_item(**args)
        except ClientError as exc:
            if _codigo(exc) != _CONDICAO_FALHOU:
                raise _erro(self.logico, "update_item", exc) from exc
            atual = self.obter(chave)
            if atual is None:
                raise self.nao_encontrado(chave) from exc
            return False, atual
        except BotoCoreError as exc:
            raise _erro(self.logico, "update_item", exc) from exc
        return True, resposta["Attributes"]

    def remover(
        self,
        chave: Mapping[str, Any],
        condicao: str | None = None,
        nomes: Mapping[str, str] | None = None,
        valores: Mapping[str, Any] | None = None,
    ) -> bool:
        """`DeleteItem`. Devolve True se removeu um item (False: não existia ou a condição
        falhou)."""
        args: dict[str, Any] = {
            "Key": dict(chave),
            "ReturnValues": "ALL_OLD",
            **_sem_vazios(nomes, valores),
        }
        if condicao:
            args["ConditionExpression"] = condicao
        try:
            resposta = self._t.delete_item(**args)
        except ClientError as exc:
            if _codigo(exc) == _CONDICAO_FALHOU:
                return False
            raise _erro(self.logico, "delete_item", exc) from exc
        except BotoCoreError as exc:
            raise _erro(self.logico, "delete_item", exc) from exc
        return bool(resposta.get("Attributes"))


# ----------------------------------------------------------------------------- transação


def put_transacao(
    tabela: Tabela,
    item: Mapping[str, Any],
    condicao: str | None = None,
    nomes: Mapping[str, str] | None = None,
    valores: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    corpo: dict[str, Any] = {
        "TableName": tabela.nome,
        "Item": dict(item),
        **_sem_vazios(nomes, valores),
    }
    if condicao:
        corpo["ConditionExpression"] = condicao
    return {"Put": corpo}


def update_transacao(
    tabela: Tabela,
    chave: Mapping[str, Any],
    expressao: str,
    condicao: str,
    nomes: Mapping[str, str],
    valores: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "Update": {
            "TableName": tabela.nome,
            "Key": dict(chave),
            "UpdateExpression": expressao,
            "ConditionExpression": condicao,
            **_sem_vazios(nomes, valores),
        }
    }


def executar_transacao(
    tabela: Tabela, itens: Sequence[Mapping[str, Any]], operacao: str = "transact_write"
) -> list[bool] | None:
    """`TransactWriteItems`, tudo ou nada.

    Devolve `None` se a transação foi aplicada. Se foi cancelada por falha de condição,
    devolve, na ordem de `itens`, quais itens falharam a condição. Qualquer outro
    cancelamento (conflito de transação, limitação de vazão) e erros de infraestrutura
    levantam `ErroRepositorio`.
    """
    try:
        tabela.cliente.transact_write_items(TransactItems=[dict(i) for i in itens])
    except ClientError as exc:
        if _codigo(exc) != _TRANSACAO_CANCELADA:
            raise _erro(tabela.logico, operacao, exc) from exc
        motivos = exc.response.get("CancellationReasons") or []
        falhas = [m.get("Code") == "ConditionalCheckFailed" for m in motivos]
        if not any(falhas):
            raise _erro(tabela.logico, operacao, exc) from exc
        return falhas
    except BotoCoreError as exc:
        raise _erro(tabela.logico, operacao, exc) from exc
    return None
