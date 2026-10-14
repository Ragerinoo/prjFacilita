"""Serviço de encerramento de Jornada (tarefa 9.4; Req 5.2, 6.7, 16.4, 17.1, 17.12).

Duas metades, ligadas por uma fila SQS (`tres-encerramentos`, com DLQ):

  PRODUTOR  `encerrar_jornada(...)`: a porta que as rotas chamam ao resolver a Jornada no guia
            (Req 5.2), no assistente (Req 6.7) ou ao encerrar o Chamado (Req 16.4). Só enfileira
            uma mensagem JSON. NUNCA levanta exceção para quem chamou e tem timeouts curtos,
            então o fluxo do Consumidor não espera nem quebra por causa do registro (Req 17.12).

  CONSUMIDOR  `processar_lote(...)`: usado por `handlers/encerramento.py`. Grava o
              `encerramento` na Jornada com `JornadasRepo.encerrar` (regra `aplicar_encerramento`
              do domínio, condição `estado <> encerrada`: a primeira camada vence, Req 17.1).
              Falha de uma mensagem a devolve à fila (resposta parcial do lote). A fila tenta
              até 3 vezes e depois manda para a DLQ.

Mensagem (JSON UTF-8, sem PII: só identificadores opacos, enumerações e números)::

    {"v": 1, "jornada_id": "...", "camada": "guia|ia|humano", "em": "2025-01-01T12:00:00.123456Z",
     "custo_brl": "0.0500", "problema_id": 3, "desfecho": "falso_defeito|defeito_real|null"}

`em` é o instante em que o fluxo encerrou, definido pelo PRODUTOR. Assim a nova tentativa e o
atraso da fila não mudam `tempo_s` nem o dia da métrica, e reprocessar é idempotente.
`abandonada` não passa por aqui: só a varredura (`JornadasRepo.marcar_abandono`) a produz.

Sinalização de falha ao Painel_Metricas (Req 17.12). Há dois pontos em que o registro pode se
perder, cada um com seu indicador, e `consultar_falhas_encerramento` os reúne para a tela:

  1. Mensagem esgotou as 3 tentativas -> vai para a DLQ. Indicador: quantidade de mensagens na
     DLQ (a API já tem `sqs:GetQueueAttributes` nela e a variável `TRES_DLQ_ENCERRAMENTOS_URL`).
     A DLQ é a fonte de verdade: não dependemos de adivinhar a "última tentativa" no consumidor
     (o SQS é quem move a mensagem) e o papel da Lambda `encerramento` não precisa de acesso
     a mais tabelas. A DLQ guarda as mensagens por 14 dias.
  2. O envio à fila falhou (SQS indisponível, timeout): a mensagem nunca existiu. Indicador:
     contador `encerramento_falhou` em `agregados_dia` (incrementado pelo produtor, a Lambda
     `api` tem escrita nessa tabela), mais log de erro.

Limitações conhecidas:
  * O contador (2) é "no máximo uma vez": se também a gravação do contador falhar, resta o log.
  * A contagem da DLQ é aproximada (atributo do SQS) e não é por período; mostra o que está
    pendente de análise. Quem esvazia a DLQ (ou o fim da retenção) zera o indicador.
  * Mensagem malformada (veneno) também é tentada 3 vezes e vai à DLQ, onde fica visível.
  * Jornada encerrada pela varredura de abandono antes da mensagem chegar mantém "abandonada"
    (a primeira camada vence); o consumidor registra o fato em log e conclui com sucesso.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final, Protocol

from core.contexto import agora_utc
from core.logs import Log
from dominio import Camada
from repositorios.interfaces import AgregadosDiaRepo, JornadasRepo

VERSAO_ESQUEMA: Final = 1
METRICA_FALHA_ENCERRAMENTO: Final = "encerramento_falhou"
MAX_TENTATIVAS: Final = 3  # igual a `ENCERRAMENTO_MAX_TENTATIVAS` da stack de armazenamento

#: Camadas que passam pela fila. `abandonada` é exclusiva da varredura (Req 17.2).
CAMADAS_ENFILEIRAVEIS: Final[tuple[str, ...]] = ("guia", "ia", "humano")
DESFECHOS: Final[tuple[str, ...]] = ("falso_defeito", "defeito_real")

# Motivos curtos devolvidos em `ResultadoEnfileiramento.motivo` (estáveis, sem dados do usuário).
MOTIVO_MENSAGEM_INVALIDA: Final = "mensagem_invalida"
MOTIVO_FILA_NAO_CONFIGURADA: Final = "fila_nao_configurada"
MOTIVO_FALHA_ENVIO: Final = "falha_envio"

# Timeouts do cliente SQS do produtor: o envio roda no caminho da requisição do Consumidor.
# Uma tentativa só: no pior caso 1 s (conexão) + 2 s (leitura) = 3 s.
SQS_TIMEOUT_CONEXAO_S: Final = 1
SQS_TIMEOUT_LEITURA_S: Final = 2
SQS_TENTATIVAS: Final = 1

_RE_JORNADA_ID: Final = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


class MensagemInvalida(ValueError):
    """Mensagem de encerramento fora do esquema (a mensagem de erro cita só o campo)."""


# ------------------------------------------------------------------------------- mensagem


@dataclass(frozen=True, slots=True)
class MensagemEncerramento:
    """Evento de encerramento que viaja pela fila. Sem PII por construção."""

    jornada_id: str
    camada: Camada
    em: datetime
    custo_brl: Decimal = Decimal("0")
    problema_id: int | None = None
    desfecho: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.jornada_id, str) or not _RE_JORNADA_ID.match(self.jornada_id):
            raise MensagemInvalida("jornada_id inválido")
        if self.camada not in CAMADAS_ENFILEIRAVEIS:
            raise MensagemInvalida("camada inválida")
        if not isinstance(self.em, datetime) or self.em.utcoffset() is None:
            raise MensagemInvalida("em deve ser um horário com fuso")
        if not isinstance(self.custo_brl, Decimal) or not self.custo_brl.is_finite():
            raise MensagemInvalida("custo_brl inválido")
        if self.custo_brl < 0:
            raise MensagemInvalida("custo_brl não pode ser negativo")
        if self.problema_id is not None and (
            isinstance(self.problema_id, bool)
            or not isinstance(self.problema_id, int)
            or self.problema_id < 1
        ):
            raise MensagemInvalida("problema_id inválido")
        if self.desfecho is not None and self.desfecho not in DESFECHOS:
            raise MensagemInvalida("desfecho inválido")

    def para_dict(self) -> dict[str, Any]:
        return {
            "v": VERSAO_ESQUEMA,
            "jornada_id": self.jornada_id,
            "camada": self.camada,
            "em": self.em.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "custo_brl": format(self.custo_brl, "f"),
            "problema_id": self.problema_id,
            "desfecho": self.desfecho,
        }

    def para_json(self) -> str:
        return json.dumps(self.para_dict(), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def de_dict(cls, dados: object) -> MensagemEncerramento:
        if not isinstance(dados, Mapping):
            raise MensagemInvalida("mensagem não é um objeto JSON")
        if dados.get("v") != VERSAO_ESQUEMA:
            raise MensagemInvalida("versão do esquema não suportada")
        bruto_em = dados.get("em")
        if not isinstance(bruto_em, str):
            raise MensagemInvalida("em inválido")
        try:
            em = datetime.fromisoformat(bruto_em)
        except ValueError:
            raise MensagemInvalida("em inválido") from None
        bruto_custo = dados.get("custo_brl", "0")
        if not isinstance(bruto_custo, str):
            raise MensagemInvalida("custo_brl inválido")
        try:
            custo = Decimal(bruto_custo)
        except InvalidOperation:
            raise MensagemInvalida("custo_brl inválido") from None
        return cls(
            jornada_id=dados.get("jornada_id"),  # type: ignore[arg-type]
            camada=dados.get("camada"),  # type: ignore[arg-type]
            em=em,
            custo_brl=custo,
            problema_id=dados.get("problema_id"),
            desfecho=dados.get("desfecho"),
        )

    @classmethod
    def de_json(cls, corpo: str) -> MensagemEncerramento:
        try:
            dados = json.loads(corpo)
        except (TypeError, ValueError):
            raise MensagemInvalida("corpo não é JSON") from None
        return cls.de_dict(dados)


# ------------------------------------------------------------------------------- produtor


@dataclass(frozen=True, slots=True)
class ResultadoEnfileiramento:
    """Indicador de falha da porta: `enfileirado=False` significa "não registrado".

    A porta não levanta exceção; quem chama decide se mostra algo (em geral, nada: o fluxo do
    Consumidor segue). `motivo` é um código curto (`MOTIVO_*`).
    """

    enfileirado: bool
    motivo: str | None = None
    message_id: str | None = None


class EncerradorDeJornada(Protocol):
    """Porta `encerrar_jornada`. Implementações: `EncerradorSqs` (produção) e fakes."""

    def encerrar_jornada(
        self,
        jornada_id: str,
        camada: Camada,
        *,
        custo_brl: Decimal = Decimal("0"),
        problema_id: int | None = None,
        desfecho: str | None = None,
        em: datetime | None = None,
    ) -> ResultadoEnfileiramento:
        """Pede o registro do encerramento. Nunca levanta exceção."""
        ...


class EncerradorSqs:
    """Porta `encerrar_jornada` sobre SQS. O cliente `sqs` (``boto3.client("sqs")``) é injetado."""

    def __init__(
        self,
        sqs: Any,
        fila_url: str | None,
        *,
        relogio: Callable[[], datetime] = agora_utc,
        agregados: AgregadosDiaRepo | None = None,
        log: Log | None = None,
    ) -> None:
        self._sqs = sqs
        self._fila_url = fila_url
        self._relogio = relogio
        self._agregados = agregados
        self._log = log or Log()

    def encerrar_jornada(
        self,
        jornada_id: str,
        camada: Camada,
        *,
        custo_brl: Decimal = Decimal("0"),
        problema_id: int | None = None,
        desfecho: str | None = None,
        em: datetime | None = None,
    ) -> ResultadoEnfileiramento:
        try:
            return self._enfileirar(jornada_id, camada, custo_brl, problema_id, desfecho, em)
        except Exception as exc:  # noqa: BLE001 - a porta nunca interrompe o fluxo do Consumidor
            return self._falhou(MOTIVO_FALHA_ENVIO, jornada_id, exc)

    def _enfileirar(
        self,
        jornada_id: str,
        camada: Camada,
        custo_brl: Decimal,
        problema_id: int | None,
        desfecho: str | None,
        em: datetime | None,
    ) -> ResultadoEnfileiramento:
        try:
            mensagem = MensagemEncerramento(
                jornada_id=jornada_id,
                camada=camada,
                em=em or self._relogio(),
                custo_brl=custo_brl,
                problema_id=problema_id,
                desfecho=desfecho,
            )
        except MensagemInvalida as exc:
            return self._falhou(MOTIVO_MENSAGEM_INVALIDA, jornada_id, exc)
        if not self._fila_url:
            return self._falhou(MOTIVO_FILA_NAO_CONFIGURADA, jornada_id, None)
        resposta = self._sqs.send_message(QueueUrl=self._fila_url, MessageBody=mensagem.para_json())
        self._log.info("encerramento_enfileirado", jornada_id=jornada_id, camada=camada)
        return ResultadoEnfileiramento(True, message_id=resposta.get("MessageId"))

    def _falhou(
        self, motivo: str, jornada_id: str, exc: BaseException | None
    ) -> ResultadoEnfileiramento:
        """Registra a falha em log e no contador `encerramento_falhou`; nunca levanta."""
        try:
            self._log.erro(
                "encerramento_nao_enfileirado", jornada_id=jornada_id, motivo=motivo, erro=exc
            )
        except Exception:  # noqa: BLE001
            pass
        if self._agregados is not None:
            try:
                self._agregados.incrementar(
                    self._relogio().astimezone(UTC).date(), METRICA_FALHA_ENCERRAMENTO
                )
            except Exception as erro_contador:  # noqa: BLE001
                try:
                    self._log.aviso("encerramento_contador_falha_indisponivel", erro=erro_contador)
                except Exception:  # noqa: BLE001
                    pass
        return ResultadoEnfileiramento(False, motivo=motivo)


def criar_cliente_sqs() -> Any:
    """`boto3.client("sqs")` com timeouts curtos (o envio está no caminho do Consumidor)."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        "sqs",
        config=Config(
            connect_timeout=SQS_TIMEOUT_CONEXAO_S,
            read_timeout=SQS_TIMEOUT_LEITURA_S,
            retries={"total_max_attempts": SQS_TENTATIVAS, "mode": "standard"},
        ),
    )


def criar_encerrador(
    ambiente: Mapping[str, str],
    *,
    sqs: Any | None = None,
    agregados: AgregadosDiaRepo | None = None,
    relogio: Callable[[], datetime] = agora_utc,
    log: Log | None = None,
) -> EncerradorSqs:
    """Monta a porta a partir de ``TRES_FILA_ENCERRAMENTOS_URL`` (definida pela stack da API).

    Sem a variável, a porta fica "não configurada": cada chamada devolve falha
    (`MOTIVO_FILA_NAO_CONFIGURADA`) e registra em log, sem derrubar a Lambda na partida.
    O cliente SQS só é criado se houver URL e nenhum cliente tiver sido injetado.
    """
    url = ambiente.get("TRES_FILA_ENCERRAMENTOS_URL") or None
    cliente = sqs if sqs is not None or not url else criar_cliente_sqs()
    return EncerradorSqs(cliente, url, relogio=relogio, agregados=agregados, log=log)


# ----------------------------------------------------------------------------- consumidor


def registrar_encerramento(jornadas: JornadasRepo, mensagem: MensagemEncerramento) -> bool:
    """Grava o `encerramento` na Jornada. Devolve True se esta mensagem foi quem encerrou.

    Idempotente: `JornadasRepo.encerrar` usa `aplicar_encerramento` e a condição
    `estado <> encerrada`. Repetir a mensagem (nova tentativa, entrega duplicada) ou perder a
    corrida para outra camada devolve False sem alterar a Jornada (Req 17.1).
    Jornada inexistente levanta `ErroNaoEncontrado` e falhas de infraestrutura levantam
    `ErroRepositorio`: em ambos os casos a mensagem deve voltar à fila.
    """
    resultado = jornadas.encerrar(
        mensagem.jornada_id,
        mensagem.camada,
        mensagem.em,
        mensagem.custo_brl,
        mensagem.problema_id,
        mensagem.desfecho,
    )
    return resultado.aplicado


def _tentativa(registro: Mapping[str, Any]) -> int:
    atributos = registro.get("attributes")
    bruto = atributos.get("ApproximateReceiveCount") if isinstance(atributos, Mapping) else None
    try:
        return max(1, int(bruto))
    except (TypeError, ValueError):
        return 1


def processar_lote(
    evento: Mapping[str, Any],
    jornadas: JornadasRepo,
    log: Log | None = None,
    *,
    max_tentativas: int = MAX_TENTATIVAS,
) -> dict[str, list[dict[str, str]]]:
    """Processa um evento do SQS e devolve a resposta de falha parcial do lote.

    Cada registro é isolado: a falha de um não afeta os outros. Os que falharem voltam em
    ``batchItemFailures`` (requer ``ReportBatchItemFailures``, já ligado na stack) e o SQS os
    reentrega após a visibilidade (cerca de 10 s) até `max_tentativas`; depois vão à DLQ.
    """
    log = log or Log()
    falhas: list[dict[str, str]] = []
    registros = evento.get("Records") if isinstance(evento, Mapping) else None
    for registro in registros if isinstance(registros, Sequence) else ():
        id_mensagem = registro.get("messageId") if isinstance(registro, Mapping) else None
        jornada_id: str | None = None
        try:
            mensagem = MensagemEncerramento.de_json(registro["body"])  # type: ignore[index]
            jornada_id = mensagem.jornada_id
            aplicado = registrar_encerramento(jornadas, mensagem)
            log.info(
                "encerramento_registrado" if aplicado else "encerramento_ja_existente",
                jornada_id=jornada_id,
                camada=mensagem.camada,
            )
        except Exception as exc:  # noqa: BLE001 - qualquer falha devolve a mensagem à fila
            tentativa = _tentativa(registro) if isinstance(registro, Mapping) else 1
            esgotou = tentativa >= max_tentativas
            log.erro(
                "encerramento_tentativas_esgotadas" if esgotou else "encerramento_falhou",
                jornada_id=jornada_id,
                tentativa=tentativa,
                erro=exc,
            )
            if isinstance(id_mensagem, str):
                falhas.append({"itemIdentifier": id_mensagem})
    return {"batchItemFailures": falhas}


# ---------------------------------------------------------------------- sinal para o Painel


@dataclass(frozen=True, slots=True)
class FalhasRegistroEncerramento:
    """O que o Painel_Metricas mostra como "falha de registro de encerramento" (Req 17.12).

    `na_dlq`: mensagens esgotadas aguardando análise (None = não foi possível consultar).
    `nao_enfileirados`: encerramentos que nem chegaram à fila no período.
    """

    na_dlq: int | None
    nao_enfileirados: int

    @property
    def houve_falha(self) -> bool:
        return bool(self.na_dlq) or self.nao_enfileirados > 0

    @property
    def total(self) -> int:
        return (self.na_dlq or 0) + self.nao_enfileirados


def contar_mensagens_dlq(sqs: Any, dlq_url: str) -> int:
    """Mensagens na DLQ (visíveis + em processamento + atrasadas). Aproximado, como no SQS."""
    resposta = sqs.get_queue_attributes(
        QueueUrl=dlq_url,
        AttributeNames=[
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible",
            "ApproximateNumberOfMessagesDelayed",
        ],
    )
    atributos = resposta.get("Attributes", {})
    return sum(int(atributos.get(nome, 0)) for nome in atributos)


def consultar_falhas_encerramento(
    *,
    sqs: Any,
    dlq_url: str | None,
    agregados: AgregadosDiaRepo,
    inicio: date,
    fim: date,
    log: Log | None = None,
) -> FalhasRegistroEncerramento:
    """Reúne os dois indicadores de falha para a tela de métricas (tarefa 20).

    A DLQ não é por período (mostra o que está pendente agora); o contador respeita
    `[inicio, fim]`. Se a DLQ não puder ser consultada, `na_dlq` vem None e a tela deve dizer
    "indisponível" em vez de "0".
    """
    log = log or Log()
    na_dlq: int | None = None
    if dlq_url:
        try:
            na_dlq = contar_mensagens_dlq(sqs, dlq_url)
        except Exception as exc:  # noqa: BLE001
            log.aviso("dlq_encerramentos_indisponivel", erro=exc)
    nao_enfileirados = sum(
        item.valor
        for item in agregados.listar(inicio, fim)
        if item.metrica == METRICA_FALHA_ENCERRAMENTO
    )
    return FalhasRegistroEncerramento(na_dlq=na_dlq, nao_enfileirados=nao_enfileirados)
