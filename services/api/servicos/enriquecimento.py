"""Enriquecimento assíncrono do Pacote_Repasse (tarefa 12.2; Req 10.3, 10.4, 10.8, 20.4).

O Chamado nasce na escalada com o Pacote determinístico e os três campos de IA em valores
provisórios (`pacote_ia_status = pendente`, ver `servicos.escalada`). A Lambda `enriquecimento`
chama `enriquecer_pacote`, que:

  1. lê o Chamado. Já `ok` ou `fallback`: não faz nada (idempotente);
  2. monta o pedido ao agente SÓ com o histórico da Jornada e campos não pessoais, tudo
     mascarado com `mascarar_pii`. Se o mascaramento falhar, o agente NÃO é chamado e o
     fallback é aplicado (Req 18.8);
  3. pede `resumo_repasse` com prazo de até 10 s (Req 10.4);
  4. valida a saída com `dominio.saida_assistente_valida` (resumo de 1 a 300, sentimento do
     Pacote, próxima ação de 1 a 200);
  5. grava com `ChamadosRepo.atualizar_campos_ia`: valores da IA e status `ok`, ou o fallback
     do Req 10.4 e status `fallback`. Só os três campos de IA mudam; prioridade, canal,
     anexos etc. nunca são tocados (uma reavaliação de prioridade feita enquanto isso fica).

Como o prazo de 15 s do Req 10.8 é cumprido
-------------------------------------------
  * O Pacote já está disponível ao Painel quando o Chamado é criado (menos de 3 s, Req 12.1),
    com o fallback do Req 10.4 em vigor. O enriquecimento só substitui os três campos. Mesmo
    que a Lambda falhe, estoure o tempo ou nem seja disparada, o Painel tem um Pacote válido.
  * A Lambda tem timeout de 15 s (`LAMBDA_ENRIQUECIMENTO_TIMEOUT_S`) e o agente, 10 s de prazo
    duro (`ENRIQUECIMENTO_TIMEOUT_S`): chamada abandonada ao fim de 10 s, sem retentativa.
  * Sobram 5 s para ler e gravar. O prazo do agente é `min(10, restante - RESERVA_GRAVACAO_S)`,
    onde `restante` vem do contexto da Lambda depois das leituras. A gravação usa um cliente
    DynamoDB com pior caso de 4 s (conexão 0,5 s + leitura 1 s, 2 tentativas, ver
    `handlers.enriquecimento`), igual à reserva. Assim a soma nunca passa de 15 s.
  * A invocação é `InvocationType="Event"` sem retentativa e com idade máxima de 60 s.

Sem PII: nada de telefone, CEP ou texto livre sem máscara chega ao agente, aos logs ou aos
retornos. Os logs levam só `numero`, `jornada_id`, contagens, causa e duração.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal, Protocol

from botocore.exceptions import BotoCoreError, ClientError

from core.logs import Log
from dominio import ErroMascaramento, mascarar_pii
from dominio.pacote import (
    PROXIMA_ACAO_FALLBACK,
    RESUMO_FALLBACK,
    SENTIMENTO_FALLBACK,
    SaidaAssistente,
    saida_assistente_valida,
)
from repositorios.interfaces import Repositorios
from servicos.agente import (
    AgenteClient,
    ErroAgente,
    PassoRegistrado,
    PedidoAgente,
    TurnoHistorico,
)
from servicos.escalada import DisparadorEnriquecimentoNulo, ja_tentado_de_eventos

# --------------------------------------------------------------------------- constantes

#: Prazo duro do agente no `resumo_repasse` (Req 10.4; `premissas.ENRIQUECIMENTO_TIMEOUT_S`).
ENRIQUECIMENTO_TIMEOUT_S: Final = 10.0
#: Timeout da Lambda (`premissas.LAMBDA_ENRIQUECIMENTO_TIMEOUT_S`; Req 10.8).
LAMBDA_ENRIQUECIMENTO_TIMEOUT_S: Final = 15.0
#: Tempo reservado depois do agente para gravar (pior caso do cliente DynamoDB da Lambda).
RESERVA_GRAVACAO_S: Final = 4.0
#: Abaixo disso não vale chamar o agente: vai direto ao fallback.
ORCAMENTO_MINIMO_AGENTE_S: Final = 1.0

#: Eventos da Jornada que carregam o texto da conversa (`dados = {"texto": <já mascarado>}`).
TIPOS_MENSAGEM: Final[Mapping[str, Literal["consumidor", "assistente"]]] = {
    "mensagem_consumidor": "consumidor",
    "mensagem_assistente": "assistente",
}
MAX_TURNOS: Final = 20  # últimos turnos enviados (custo e latência do modelo)
MAX_TEXTO: Final = 1000  # caracteres por turno, depois de mascarar
MAX_PASSOS: Final = 30

PADRAO_NUMERO: Final = re.compile(r"^TRES-[0-9A-HJKMNP-TV-Z]{10}$")

StatusEnriquecimento = Literal["ok", "fallback", "ja_processado", "chamado_inexistente"]
MotivoFallback = Literal[
    "erro", "tempo_esgotado", "saida_invalida", "resumo_invalido", "mascaramento", "sem_tempo"
]


@dataclass(frozen=True, slots=True)
class ResultadoEnriquecimento:
    """Desfecho de `enriquecer_pacote`. `motivo` só existe quando o status é `fallback`."""

    numero: str
    status: StatusEnriquecimento
    motivo: MotivoFallback | None = None
    duracao_agente_s: float | None = None

    def para_dict(self) -> dict[str, Any]:
        """Resposta da Lambda (sem texto livre)."""
        corpo: dict[str, Any] = {"status": self.status}
        if self.motivo is not None:
            corpo["motivo"] = self.motivo
        return corpo


# ------------------------------------------------------------------------- montagem


def _limitar(texto: str) -> str:
    return texto if len(texto) <= MAX_TEXTO else texto[:MAX_TEXTO]


def _historico(eventos: list[Any]) -> tuple[TurnoHistorico, ...]:
    """Turnos da conversa em ordem cronológica, já mascarados e limitados.

    Mascara ANTES de truncar: cortar primeiro poderia deixar um pedaço de telefone sem máscara.
    Levanta `ErroMascaramento` se algum texto não puder ser mascarado.
    """
    turnos: list[TurnoHistorico] = []
    for evento in eventos:
        papel = TIPOS_MENSAGEM.get(evento.tipo)
        texto = evento.dados.get("texto") if isinstance(evento.dados, Mapping) else None
        if papel is None or not isinstance(texto, str) or not texto.strip():
            continue
        turnos.append(TurnoHistorico(papel=papel, texto=_limitar(mascarar_pii(texto))))
    return tuple(turnos[-MAX_TURNOS:])


def _passos(eventos: list[Any]) -> tuple[PassoRegistrado, ...]:
    itens = ja_tentado_de_eventos(eventos)
    return tuple(
        PassoRegistrado(camada=i.camada, passo=_limitar(mascarar_pii(i.passo)), resultado=i.resultado)
        for i in itens[-MAX_PASSOS:]
    )


def montar_pedido(repos: Repositorios, jornada_id: str) -> PedidoAgente:
    """Pedido `resumo_repasse` da Jornada: histórico e passos mascarados, sem Dados_Pessoais.

    Fonte: tabelas `jornadas` e `eventos` (a conversa é evento da Jornada, design item 4).
    `numero_serie` e `modelo_id` são identificadores do produto e vão como estão. Telefone e
    CEP moram só em `dados_pessoais`, tabela que este módulo nunca lê.
    Levanta `ErroMascaramento` (nada deve ser enviado) ou `ErroRepositorio` (leitura falhou).
    """
    jornada = repos.jornadas.obter(jornada_id)
    eventos = repos.eventos.listar(jornada_id)
    return PedidoAgente(
        jornada_id=jornada_id,
        modelo_id=jornada.modelo_id if jornada else None,
        numero_serie=jornada.numero_serie if jornada else None,
        passos_registrados=_passos(eventos),
        historico=_historico(eventos),
    )


# --------------------------------------------------------------------------- serviço


def enriquecer_pacote(
    numero: str,
    repos: Repositorios,
    agente: AgenteClient,
    *,
    orcamento_agente_s: float = ENRIQUECIMENTO_TIMEOUT_S,
    relogio: Callable[[], float] = time.monotonic,
    log: Log | None = None,
) -> ResultadoEnriquecimento:
    """Preenche resumo, sentimento e próxima ação do Pacote do Chamado `numero`.

    `orcamento_agente_s`: tempo disponível para o agente (a Lambda reduz conforme o que resta do
    seu timeout). Nunca passa de 10 s. Nunca levanta por causa do agente: qualquer falha dele,
    do mascaramento ou da validação vira fallback (Req 10.4). Falhas do repositório
    (`ErroRepositorio`) sobem: o Chamado continua com o Pacote provisório, que já é válido.
    """
    log = log or Log()
    chamado = repos.chamados.obter(numero)
    if chamado is None:
        log.aviso("enriquecimento_chamado_inexistente", numero=numero)
        return ResultadoEnriquecimento(numero, "chamado_inexistente")
    if chamado.pacote_ia_status != "pendente":
        log.info("enriquecimento_ignorado", numero=numero, pacote_ia_status=chamado.pacote_ia_status)
        return ResultadoEnriquecimento(numero, "ja_processado")

    saida, motivo, duracao = _consultar_agente(
        chamado.jornada_id, repos, agente, min(orcamento_agente_s, ENRIQUECIMENTO_TIMEOUT_S), relogio, log
    )
    if motivo is None and saida_assistente_valida(saida):
        assert saida is not None
        repos.chamados.atualizar_campos_ia(
            numero,
            str(saida.resumo),
            str(saida.sentimento),
            str(saida.proxima_acao),
            "ok",
        )
        log.info("enriquecimento_ok", numero=numero, jornada_id=chamado.jornada_id)
        return ResultadoEnriquecimento(numero, "ok", duracao_agente_s=duracao)

    motivo = motivo or "resumo_invalido"
    repos.chamados.atualizar_campos_ia(
        numero, RESUMO_FALLBACK, SENTIMENTO_FALLBACK, PROXIMA_ACAO_FALLBACK, "fallback"
    )
    log.aviso("enriquecimento_fallback", numero=numero, jornada_id=chamado.jornada_id, causa=motivo)
    return ResultadoEnriquecimento(numero, "fallback", motivo, duracao)


def _consultar_agente(
    jornada_id: str,
    repos: Repositorios,
    agente: AgenteClient,
    orcamento_s: float,
    relogio: Callable[[], float],
    log: Log,
) -> tuple[SaidaAssistente | None, MotivoFallback | None, float | None]:
    """Chama `resumo_repasse`. Devolve `(saída, motivo_da_falha, duração)`; nunca levanta."""
    if orcamento_s < ORCAMENTO_MINIMO_AGENTE_S:
        return None, "sem_tempo", None
    try:
        pedido = montar_pedido(repos, jornada_id)
    except ErroMascaramento:
        # Nada de texto sem máscara sai daqui (Req 18.8): usa o fallback.
        return None, "mascaramento", None
    # ErroRepositorio na leitura do histórico sobe: sem histórico não há o que resumir e o
    # Pacote provisório (igual ao fallback) segue valendo.
    inicio = relogio()
    try:
        bruto = agente.resumo_repasse(pedido, timeout_s=orcamento_s)
    except ErroAgente as exc:
        duracao = relogio() - inicio
        log.aviso("agente_resumo_falhou", jornada_id=jornada_id, causa=exc.causa, duracao_s=duracao)
        return None, exc.causa, duracao
    except Exception as exc:  # noqa: BLE001 - qualquer coisa do agente vira fallback (Req 10.4)
        log.erro("agente_resumo_erro_inesperado", jornada_id=jornada_id, erro=exc)
        return None, "erro", relogio() - inicio
    duracao = relogio() - inicio
    if duracao > orcamento_s:  # resposta tardia de um agente que ignorou o prazo
        return None, "tempo_esgotado", duracao
    return (
        SaidaAssistente(
            resumo=bruto.resumo, sentimento=bruto.sentimento, proxima_acao=bruto.proxima_acao
        ),
        None,
        duracao,
    )


# -------------------------------------------------------------------------- disparador


class ErroDisparo(Exception):
    """A Lambda de enriquecimento não aceitou o evento (`ServicoEscalada` só registra)."""


class ClienteLambda(Protocol):
    def invoke(self, **kwargs: Any) -> Mapping[str, Any]: ...


class DisparadorLambda:
    """Implementa `DisparadorEnriquecimento`: `lambda:InvokeFunction` assíncrono (`Event`).

    Não engole nada: qualquer falha do cliente ou resposta diferente de 202 levanta
    `ErroDisparo`. O `ServicoEscalada` já ignora (e registra) falhas de disparo, porque o Pacote
    provisório é válido (Req 10.4, 10.8).
    """

    def __init__(self, cliente: ClienteLambda, nome_funcao: str) -> None:
        if not nome_funcao:
            raise ValueError("nome_funcao é obrigatório")
        self._cliente = cliente
        self._nome = nome_funcao

    def disparar(self, numero: str) -> None:
        if not PADRAO_NUMERO.match(numero):
            raise ErroDisparo("número de Chamado inválido")
        try:
            resposta = self._cliente.invoke(
                FunctionName=self._nome,
                InvocationType="Event",
                Payload=json.dumps({"numero": numero}).encode("utf-8"),
            )
        except (ClientError, BotoCoreError) as exc:
            raise ErroDisparo(f"invocação falhou ({type(exc).__name__})") from exc
        status = resposta.get("StatusCode")
        if status != 202:
            raise ErroDisparo(f"invocação assíncrona não aceita (status {status})")


def criar_disparador(ambiente: Mapping[str, str], cliente: ClienteLambda | None = None) -> Any:
    """Disparador do ambiente: `DisparadorLambda` se `TRES_FUNCAO_ENRIQUECIMENTO` existe.

    Sem a variável (modo local, testes), devolve o disparador nulo. O cliente boto3 tem
    timeouts curtos e nenhuma retentativa: a escalada não pode esperar a invocação (Req 12.1).
    """
    funcao = ambiente.get("TRES_FUNCAO_ENRIQUECIMENTO")
    if not funcao:
        return DisparadorEnriquecimentoNulo()
    if cliente is None:
        import boto3
        from botocore.config import Config

        cliente = boto3.client(
            "lambda",
            config=Config(
                connect_timeout=1,
                read_timeout=2,
                retries={"total_max_attempts": 1, "mode": "standard"},
            ),
        )
    return DisparadorLambda(cliente, funcao)
