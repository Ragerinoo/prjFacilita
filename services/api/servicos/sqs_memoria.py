"""Fila SQS falsa em memória, para testes do encerramento (sem rede, sem `moto`).

Imita o que o serviço usa do SQS:
  * `send_message` e `get_queue_attributes` (a interface do cliente boto3 que o produtor e a
    consulta da DLQ recebem por injeção);
  * a entrega a uma Lambda com ``batch_size=1`` e ``ReportBatchItemFailures``, com
    ``ApproximateReceiveCount`` e o redrive para a DLQ depois de `max_tentativas` recebimentos.

Simplificações: o tempo de visibilidade não é simulado (a mensagem devolvida fica logo
disponível) e há uma só fila de origem mais a DLQ. Como no SQS real, a mensagem só vai para a
DLQ no recebimento seguinte ao último que falhou, não no momento da falha.
"""

from __future__ import annotations

import itertools
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class _Mensagem:
    id: str
    corpo: str
    recebimentos: int = 0


class SqsMemoria:
    def __init__(
        self,
        fila_url: str = "mem://tres-encerramentos",
        dlq_url: str = "mem://tres-encerramentos-dlq",
        max_tentativas: int = 3,
    ) -> None:
        self.fila_url = fila_url
        self.dlq_url = dlq_url
        self.max_tentativas = max_tentativas
        self._fila: deque[_Mensagem] = deque()
        self._dlq: list[_Mensagem] = []
        self._ids = itertools.count(1)
        self._falhas_envio: list[BaseException] = []
        self.envios = 0  # tentativas de envio (inclusive as que falharam)

    # -- interface do cliente boto3 -------------------------------------------------------
    def send_message(self, *, QueueUrl: str, MessageBody: str, **_: Any) -> dict[str, str]:  # noqa: N803
        self.envios += 1
        if self._falhas_envio:
            raise self._falhas_envio.pop(0)
        if QueueUrl != self.fila_url:
            raise KeyError("fila desconhecida")
        mensagem = _Mensagem(id=f"msg-{next(self._ids)}", corpo=MessageBody)
        self._fila.append(mensagem)
        return {"MessageId": mensagem.id}

    def get_queue_attributes(self, *, QueueUrl: str, **_: Any) -> dict[str, dict[str, str]]:  # noqa: N803
        if QueueUrl == self.dlq_url:
            visiveis = len(self._dlq)
        elif QueueUrl == self.fila_url:
            visiveis = len(self._fila)
        else:
            raise KeyError("fila desconhecida")
        return {
            "Attributes": {
                "ApproximateNumberOfMessages": str(visiveis),
                "ApproximateNumberOfMessagesNotVisible": "0",
                "ApproximateNumberOfMessagesDelayed": "0",
            }
        }

    # -- controle dos testes --------------------------------------------------------------
    def falhar_proximos_envios(self, quantidade: int, erro: BaseException | None = None) -> None:
        """Os próximos `quantidade` envios levantam `erro` (padrão: ConnectionError)."""
        for _ in range(quantidade):
            self._falhas_envio.append(erro or ConnectionError("SQS indisponível"))

    @property
    def corpos_na_fila(self) -> list[str]:
        return [m.corpo for m in self._fila]

    @property
    def corpos_na_dlq(self) -> list[str]:
        return [m.corpo for m in self._dlq]

    @property
    def tamanho(self) -> int:
        return len(self._fila)

    # -- entrega à Lambda ----------------------------------------------------------------
    def entregar(self, handler: Callable[[dict[str, Any], Any], dict[str, Any]]) -> bool:
        """Entrega a próxima mensagem a `handler`. False se a fila estava vazia.

        Mensagem que já foi recebida `max_tentativas` vezes vai para a DLQ sem ser entregue.
        Falha do handler (exceção ou ``batchItemFailures``) devolve a mensagem ao fim da fila.
        """
        if not self._fila:
            return False
        mensagem = self._fila.popleft()
        if mensagem.recebimentos >= self.max_tentativas:
            self._dlq.append(mensagem)
            return True
        mensagem.recebimentos += 1
        evento = {
            "Records": [
                {
                    "messageId": mensagem.id,
                    "body": mensagem.corpo,
                    "attributes": {"ApproximateReceiveCount": str(mensagem.recebimentos)},
                    "eventSource": "aws:sqs",
                }
            ]
        }
        try:
            resposta = handler(evento, None)
            falhou = bool(resposta and resposta.get("batchItemFailures"))
        except Exception:  # noqa: BLE001 - invocação com erro: o lote inteiro volta
            falhou = True
        if falhou:
            self._fila.append(mensagem)
        return True

    def drenar(
        self, handler: Callable[[dict[str, Any], Any], dict[str, Any]], limite: int = 100
    ) -> int:
        """Entrega até esvaziar a fila (ou `limite` entregas). Devolve quantas entregas houve."""
        entregas = 0
        while entregas < limite and self.entregar(handler):
            entregas += 1
        return entregas
