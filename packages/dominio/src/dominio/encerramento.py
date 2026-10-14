"""Regras de encerramento e abandono da Jornada (Req 17.1, 17.2).

Funções puras (sem I/O, relógio global ou aleatoriedade): o horário atual entra sempre
por parâmetro (`agora` / `em`). Todos os horários devem ter fuso (timezone-aware).

Máquina de estados (design, "Máquina de estados da Jornada"):

    ativa     -> encerrada (camada guia | ia)   resolvida no guia ou na IA
    escalada  -> encerrada (camada humano)      Atendente encerra o Chamado
    ativa     -> encerrada (camada abandonada)  30 min sem interação e sem Chamado

Garantias:
  * Uma Jornada tem no máximo uma camada de resolução, e ela é permanente: depois de
    encerrada, `aplicar_encerramento` e `marcar_abandono` devolvem a Jornada inalterada
    (equivalente à condição ``estado <> encerrada`` do ``UpdateItem`` no DynamoDB).
  * Abandono é terminal: interações posteriores (`registrar_interacao`) não alteram a
    camada nem o horário de encerramento (Req 17.2).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, Literal

from dominio.erros import ErroDominio
from dominio.tipos import Camada, JornadaEncerrada

LIMITE_ABANDONO: Final = timedelta(minutes=30)  # Req 17.2

EstadoJornada = Literal["ativa", "escalada", "encerrada"]

# Valores constantes dos atributos de índice esparso (design, `jornadas`).
ATIVA_PK: Final = "ATIVA"
ENCERRADA_PK: Final = "ENC"

_CENTAVOS: Final = Decimal("0.01")


class ErroEncerramento(ErroDominio):
    """Pedido de encerramento inválido (camada incompatível ou dados incoerentes)."""


@dataclass(frozen=True, slots=True)
class EstadoDaJornada:
    """Visão mínima da Jornada necessária para as regras de encerramento.

    `ultima_interacao` é a última interação do Consumidor. `chamado_numero` só existe
    depois da escalada. `encerramento` só existe em estado ``encerrada``.
    """

    jornada_id: str
    criada_em: datetime
    ultima_interacao: datetime
    estado: EstadoJornada = "ativa"
    chamado_numero: str | None = None
    encerramento: JornadaEncerrada | None = None

    @property
    def encerrada(self) -> bool:
        return self.estado == "encerrada"

    @property
    def tem_chamado(self) -> bool:
        return self.chamado_numero is not None or self.estado == "escalada"

    @property
    def ativa_pk(self) -> str | None:
        """Atributo do `gsi_ativas`: só existe enquanto ativa e sem Chamado."""
        return ATIVA_PK if self.estado == "ativa" and not self.tem_chamado else None

    @property
    def encerrada_pk(self) -> str | None:
        """Atributo do `gsi_encerradas`: só existe depois do encerramento."""
        return ENCERRADA_PK if self.encerrada else None

    @property
    def encerrada_em(self) -> datetime | None:
        """Espelho de `encerramento.em`, chave de ordenação do `gsi_encerradas`."""
        return self.encerramento.encerrada_em if self.encerramento else None


@dataclass(frozen=True, slots=True)
class ResultadoEncerramento:
    """Resultado de uma tentativa de encerrar a Jornada.

    `aplicado` é falso quando a Jornada já estava encerrada (ou, no abandono, quando
    ainda não venceu o prazo ou há Chamado); nesse caso `jornada` é a original.
    """

    jornada: EstadoDaJornada
    aplicado: bool


def _segundos(inicio: datetime, fim: datetime) -> int:
    return max(0, int((fim - inicio).total_seconds()))


def _custo_2_casas(custo: Decimal) -> Decimal:
    if custo < 0:
        raise ErroEncerramento("custo_brl não pode ser negativo")
    return custo.quantize(_CENTAVOS, rounding=ROUND_HALF_UP)


def _encerrar(
    j: EstadoDaJornada,
    camada: Camada,
    em: datetime,
    fim_do_tempo: datetime,
    custo_brl: Decimal,
    problema_id: int | None,
    desfecho: str | None,
) -> EstadoDaJornada:
    registro = JornadaEncerrada(
        jornada_id=j.jornada_id,
        camada=camada,
        encerrada_em=em,
        tempo_s=_segundos(j.criada_em, fim_do_tempo),
        custo_brl=_custo_2_casas(custo_brl),
        problema_id=problema_id,
        desfecho=desfecho,
    )
    return replace(j, estado="encerrada", encerramento=registro)


def aplicar_encerramento(
    jornada: EstadoDaJornada,
    camada: Camada,
    em: datetime,
    custo_brl: Decimal = Decimal("0"),
    problema_id: int | None = None,
    desfecho: str | None = None,
) -> ResultadoEncerramento:
    """Registra a única camada de resolução da Jornada (Req 17.1).

    * Jornada já encerrada: devolve-a inalterada com `aplicado=False`; a camada e o
      horário originais são permanentes (inclusive se já era ``abandonada``).
    * `tempo_s` = segundos do início da Jornada até `em`.
    * `custo_brl` é arredondado a 2 casas (meio para cima); negativo é erro.
    * ``abandonada`` não é aceita aqui: só `marcar_abandono` a produz.
    """
    if camada == "abandonada":
        raise ErroEncerramento("a camada 'abandonada' só pode ser aplicada por marcar_abandono")
    if jornada.encerrada:
        return ResultadoEncerramento(jornada, False)
    novo = _encerrar(jornada, camada, em, em, custo_brl, problema_id, desfecho)
    return ResultadoEncerramento(novo, True)


def marcar_abandono(
    jornada: EstadoDaJornada,
    agora: datetime,
    custo_brl: Decimal = Decimal("0"),
    problema_id: int | None = None,
) -> ResultadoEncerramento:
    """Marca a Jornada como ``abandonada`` (Req 17.2).

    Só se aplica quando a Jornada está ``ativa`` (não encerrada), sem Chamado e com
    pelo menos 30 minutos desde `ultima_interacao`. O `tempo_s` vai do início da
    Jornada até a última interação do Consumidor (Req 17.1). Caso contrário devolve a
    Jornada inalterada com `aplicado=False`. Abandono é terminal.
    """
    if jornada.estado != "ativa" or jornada.tem_chamado:
        return ResultadoEncerramento(jornada, False)
    if agora - jornada.ultima_interacao < LIMITE_ABANDONO:
        return ResultadoEncerramento(jornada, False)
    novo = _encerrar(
        jornada, "abandonada", agora, jornada.ultima_interacao, custo_brl, problema_id, None
    )
    return ResultadoEncerramento(novo, True)


def registrar_interacao(jornada: EstadoDaJornada, em: datetime) -> EstadoDaJornada:
    """Atualiza `ultima_interacao` sem nunca mudar um encerramento (Req 17.2).

    Numa Jornada encerrada (inclusive abandonada) a interação não altera nada.
    Em Jornada aberta, `ultima_interacao` nunca retrocede.
    """
    if jornada.encerrada or em <= jornada.ultima_interacao:
        return jornada
    return replace(jornada, ultima_interacao=em)
