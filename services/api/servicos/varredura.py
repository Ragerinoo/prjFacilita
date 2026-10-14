"""Varredura de abandono de Jornadas (tarefa 20.1; Req 17.2, com custo do Req 17.1).
Rodada pela Lambda `varredura` (EventBridge Scheduler, a cada 5 min). Procura no `gsi_ativas`
as Jornadas ``ativa`` e sem Chamado cuja última interação foi há 30 minutos ou mais e as marca
``abandonada`` com `JornadasRepo.marcar_abandono`.
Garantias (a regra é do domínio, a condição de escrita é do repositório):
  * Terminal e "exatamente uma camada": `marcar_abandono` só grava com ``estado = ativa``, sem
    escalada e com `ultima_interacao` igual à lida. Jornada com Chamado, já encerrada ou que
    recebeu uma interação no meio do caminho volta ``aplicado=False`` e não é alterada.
  * Idempotente: depois de marcada, a Jornada sai do `gsi_ativas`; rodar de novo (ou duas
    execuções sobrepostas) não muda nada. O `gsi_ativas` é eventualmente consistente, então um
    item já encerrado pode ainda aparecer na lista; o `marcar_abandono` relê a Jornada com
    leitura forte e devolve ``aplicado=False``.
  * O limite é inclusivo: 30:00 de inatividade abandona; 29:59 não (`dominio.LIMITE_ABANDONO`).
  * O custo de IA acumulado da Jornada (`custo_ia_brl`) vai para o registro de encerramento
    (Req 17.1). O `problema_id` vem do próprio repositório, que o relê junto da Jornada.
  * Falha em um item (``ErroRepositorio``, ``ErroNaoEncontrado`` ou qualquer outra) é contada e
    registrada, e a varredura segue com os demais. Só a falha da listagem sobe, para o
    Scheduler tentar de novo e o erro aparecer nas métricas da Lambda.
Orçamento de tempo: a Lambda tem 60 s. O repositório lista TODOS os candidatos de uma vez
(a paginação do `Query` é interna), então a proteção está no processamento: no máximo
`limite_por_execucao` Jornadas por rodada, das mais antigas para as mais novas, e a varredura
para sozinha quando `restante_s()` cai abaixo de `margem_s`. O que sobrar fica no `gsi_ativas`
e a rodada seguinte continua (5 min depois). Não há perda: só atraso de abandono.
Limitação conhecida: o custo vem da listagem (`gsi_ativas` projeta o item inteiro), então um
custo somado entre a listagem e a gravação sem nova interação não entra no registro. É uma
janela de segundos numa Jornada parada há 30 min; qualquer chamada ao modelo vem de uma
interação e, portanto, cancela o abandono.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any, Final

from core.logs import Log
from dominio.encerramento import LIMITE_ABANDONO
from repositorios.erros import ErroNaoEncontrado
from repositorios.interfaces import JornadasRepo
from repositorios.modelos import Jornada

#: Teto de Jornadas processadas por rodada (o excedente fica para a rodada seguinte).
LIMITE_POR_EXECUCAO: Final = 500
#: Folga reservada no fim da Lambda (timeout de 60 s): cobre o pior caso de uma chamada ao
#: DynamoDB (~9 s com a config curta) mais a gravação do log e o retorno.
MARGEM_S: Final = 20.0
INTERROMPIDA_LIMITE: Final = "limite"
INTERROMPIDA_TEMPO: Final = "tempo"
def custo_acumulado(jornada: Jornada) -> Decimal:
    """Custo padrão levado ao registro de abandono: o `custo_ia_brl` da Jornada."""
    return jornada.custo_ia_brl
def varrer_abandonadas(
    jornadas: JornadasRepo,
    agora: datetime,
    *,
    limite_por_execucao: int = LIMITE_POR_EXECUCAO,
    custo_por_jornada: Callable[[Jornada], Decimal] = custo_acumulado,
    restante_s: Callable[[], float] | None = None,
    margem_s: float = MARGEM_S,
    log: Log | None = None,
) -> dict[str, Any]:
    """Marca como abandonadas as Jornadas sem interação há `LIMITE_ABANDONO` ou mais.
    `agora` (com fuso) entra por parâmetro, sem relógio global. `restante_s` devolve os
    segundos que restam à execução (na Lambda, ``contexto.get_remaining_time_in_millis()/1000``);
    sem ele não há corte por tempo, só por `limite_por_execucao`.
    Devolve o resumo da rodada::
        {"limite_ate": ISO, "candidatas": n, "processadas": n, "abandonadas": n,
         "ignoradas": n, "falhas": n, "nao_processadas": n, "interrompida_por": None|str}
    `ignoradas` são as que não precisavam ou não podiam ser marcadas (interação nova, Chamado,
    já encerrada, removida); `nao_processadas` ficaram para a próxima rodada.
    """
    if agora.tzinfo is None or agora.utcoffset() is None:
        raise ValueError("agora deve ter fuso horário")
    if limite_por_execucao < 0:
        raise ValueError("limite_por_execucao não pode ser negativo")
    log = log or Log()
    limite = agora - LIMITE_ABANDONO
    candidatas = jornadas.listar_ativas_sem_interacao_ate(limite)
    abandonadas = ignoradas = falhas = processadas = 0
    interrompida: str | None = None
    for jornada in candidatas:
        if processadas >= limite_por_execucao:
            interrompida = INTERROMPIDA_LIMITE
            break
        if restante_s is not None and restante_s() < margem_s:
            interrompida = INTERROMPIDA_TEMPO
            break
        processadas += 1
        try:
            resultado = jornadas.marcar_abandono(
                jornada.jornada_id, agora, custo_por_jornada(jornada)
            )
        except ErroNaoEncontrado:
            ignoradas += 1  # removida entre a listagem e a gravação
            log.aviso("varredura_jornada_inexistente", jornada_id=jornada.jornada_id)
        except Exception as exc:  # noqa: BLE001 - uma Jornada com falha não derruba a rodada
            falhas += 1
            log.erro("varredura_falha_no_item", jornada_id=jornada.jornada_id, erro=exc)
        else:
            if resultado.aplicado:
                abandonadas += 1
            else:
                ignoradas += 1
    resumo: dict[str, Any] = {
        "limite_ate": limite.isoformat(),
        "candidatas": len(candidatas),
        "processadas": processadas,
        "abandonadas": abandonadas,
        "ignoradas": ignoradas,
        "falhas": falhas,
        "nao_processadas": len(candidatas) - processadas,
        "interrompida_por": interrompida,
    }
    nivel = log.aviso if falhas or interrompida else log.info
    nivel("varredura_concluida", **resumo)
    return resumo
