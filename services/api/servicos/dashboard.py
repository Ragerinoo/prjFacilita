"""Dashboard do Painel_CS: visão geral e Chamados em foco (função pura, sem I/O).

Não lê relógio nem repositório: recebe o instante `agora`, a projeção mínima de cada
Chamado (`ChamadoDashboard`) e os títulos do catálogo. A projeção só carrega o que o
Dashboard precisa; nunca telefone, CEP, mensagens, resumo do Pacote, `jornada_id`,
nome ou usuário do responsável, anexos, encerramento nem canal (Req 23.1 a 23.3).

Conjunto fechado de chaves da resposta:
- primeiro nível: `modo_local`, `gerado_em`, `visao_geral`, `em_foco`;
- `visao_geral`: `abertos`, `em_atendimento`, `encerrados`, `p1_risco_abertos`,
  `sem_responsavel`, `respostas_nao_lidas` (inteiros, sem restrição de data);
- `em_foco`: `total`, `limite`, `itens` (no máximo `LIMITE_EM_FOCO`);
- cada item: `numero`, `prioridade`, `status`, `modelo`, `problema`, `idade_min`,
  `risco`, `sem_responsavel`, `resposta_nao_lida`, `parado`, `motivos`.

A ordem de `em_foco.itens` é total e determinística: motivo mais urgente, prioridade
(P1 antes de P2 antes de P3), idade em minutos decrescente e número crescente.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from dominio.tipos import Prioridade
from repositorios.modelos import RANKING_PRIORIDADE, Chamado, Jornada, StatusChamado
from servicos.metricas_chamados import ROTULO_NAO_INFORMADO

LIMITE_PARADO: Final = timedelta(minutes=60)
LIMITE_EM_FOCO: Final = 10
# Do mais ao menos urgente.
MOTIVOS: Final = ("p1_ou_risco", "resposta_nao_lida", "sem_responsavel", "parado")

CHAVES_PRIMEIRO_NIVEL: Final = ("modo_local", "gerado_em", "visao_geral", "em_foco")
CHAVES_VISAO_GERAL: Final = (
    "abertos",
    "em_atendimento",
    "encerrados",
    "p1_risco_abertos",
    "sem_responsavel",
    "respostas_nao_lidas",
)
CHAVES_EM_FOCO: Final = ("total", "limite", "itens")
CHAVES_ITEM: Final = (
    "numero",
    "prioridade",
    "status",
    "modelo",
    "problema",
    "idade_min",
    "risco",
    "sem_responsavel",
    "resposta_nao_lida",
    "parado",
    "motivos",
)


@dataclass(frozen=True, slots=True)
class ChamadoDashboard:
    """Projeção mínima de um Chamado (privacidade por construção)."""

    numero: str
    prioridade: Prioridade
    status: StatusChamado
    criado_em: datetime
    responsavel_desde: datetime | None  # só o instante; nunca nome nem usuário
    resposta_nao_lida: bool
    risco: bool  # Jornada.risco is not None
    modelo_id: str | None
    problema_id: int | None

    @classmethod
    def de(cls, chamado: Chamado, jornada: Jornada | None) -> ChamadoDashboard:
        """Jornada ausente vira `risco=False`, `modelo_id=None` e `problema_id=None`."""
        return cls(
            numero=chamado.numero,
            prioridade=chamado.prioridade,
            status=chamado.status,
            criado_em=chamado.criado_em,
            responsavel_desde=(
                chamado.responsavel.inicio if chamado.responsavel is not None else None
            ),
            resposta_nao_lida=chamado.resposta_nao_lida,
            risco=jornada is not None and jornada.risco is not None,
            modelo_id=None if jornada is None else jornada.modelo_id,
            problema_id=None if jornada is None else jornada.problema_id,
        )


def _ativo(chamado: ChamadoDashboard) -> bool:
    return chamado.status != "encerrado"


def _parado(chamado: ChamadoDashboard, agora: datetime) -> bool:
    return (
        chamado.status == "em_atendimento"
        and chamado.responsavel_desde is not None
        and agora - chamado.responsavel_desde >= LIMITE_PARADO
    )


def motivos_de(chamado: ChamadoDashboard, agora: datetime) -> tuple[str, ...]:
    """Motivos de foco na ordem de `MOTIVOS`; vazia para Chamado encerrado."""
    if not _ativo(chamado):
        return ()
    vale = {
        "p1_ou_risco": chamado.prioridade == "P1" or chamado.risco,
        "resposta_nao_lida": chamado.resposta_nao_lida,
        "sem_responsavel": chamado.responsavel_desde is None,
        "parado": _parado(chamado, agora),
    }
    return tuple(motivo for motivo in MOTIVOS if vale[motivo])


def idade_em_minutos(chamado: ChamadoDashboard, agora: datetime) -> int:
    """Minutos completos desde a abertura, nunca negativos."""
    return max(0, int((agora - chamado.criado_em).total_seconds() // 60))


def chave_de_ordem(chamado: ChamadoDashboard, agora: datetime) -> tuple[int, int, int, str]:
    """Chave total: motivo mais urgente, prioridade, mais antigo primeiro, número."""
    motivos = motivos_de(chamado, agora)
    return (
        MOTIVOS.index(motivos[0]),
        RANKING_PRIORIDADE[chamado.prioridade],
        -idade_em_minutos(chamado, agora),
        chamado.numero,
    )


def _rotulo_problema(problema_id: int | None, titulos: Mapping[int, str]) -> str:
    if problema_id is None:
        return ROTULO_NAO_INFORMADO
    titulo = titulos.get(problema_id)
    return titulo if titulo else f"Problema {problema_id}"


def _item(
    chamado: ChamadoDashboard, agora: datetime, titulos: Mapping[int, str]
) -> dict[str, Any]:
    return {
        "numero": chamado.numero,
        "prioridade": chamado.prioridade,
        "status": chamado.status,
        "modelo": chamado.modelo_id if chamado.modelo_id else ROTULO_NAO_INFORMADO,
        "problema": _rotulo_problema(chamado.problema_id, titulos),
        "idade_min": idade_em_minutos(chamado, agora),
        "risco": chamado.risco,
        "sem_responsavel": chamado.responsavel_desde is None,
        "resposta_nao_lida": chamado.resposta_nao_lida,
        "parado": _parado(chamado, agora),
        "motivos": list(motivos_de(chamado, agora)),
    }


def montar_dashboard(
    agora: datetime,
    *,
    modo_local: bool,
    chamados: Sequence[ChamadoDashboard],
    titulos: Mapping[int, str],
) -> dict[str, Any]:
    ativos = [c for c in chamados if _ativo(c)]
    visao_geral = {
        "abertos": sum(1 for c in chamados if c.status == "aberto"),
        "em_atendimento": sum(1 for c in chamados if c.status == "em_atendimento"),
        "encerrados": sum(1 for c in chamados if c.status == "encerrado"),
        "p1_risco_abertos": sum(1 for c in ativos if c.prioridade == "P1" and c.risco),
        "sem_responsavel": sum(1 for c in ativos if c.responsavel_desde is None),
        "respostas_nao_lidas": sum(1 for c in ativos if c.resposta_nao_lida),
    }
    em_foco = sorted(
        (c for c in ativos if motivos_de(c, agora)),
        key=lambda c: chave_de_ordem(c, agora),
    )
    return {
        "modo_local": modo_local,
        "gerado_em": agora.isoformat(),
        "visao_geral": visao_geral,
        "em_foco": {
            "total": len(em_foco),
            "limite": LIMITE_EM_FOCO,
            "itens": [_item(c, agora, titulos) for c in em_foco[:LIMITE_EM_FOCO]],
        },
    }
