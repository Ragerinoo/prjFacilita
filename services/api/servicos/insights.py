"""Insights do Gestor (serviço puro, sem I/O).

Esta primeira parte define as constantes do contrato, o erro de período e a resolução do
período de análise. A função `resolver_periodo` não lê o relógio: recebe `agora`.
O intervalo é semiaberto `[inicio, fim)`, o mesmo que `PeriodoMetricas` usa.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final

from dominio.metricas import (
    SEM_DADOS,
    ChamadoEncerrado,
    ConfigMetricas,
    Metricas,
    PeriodoMetricas,
    agregar_metricas,
    formatar_min_seg,
)
from dominio.metricas import AgregadoDia as AgregadoDiaDominio
from dominio.metricas import Avaliacao as AvaliacaoDominio
from dominio.pii import mascarar_pii
from dominio.tipos import JornadaEncerrada, Prioridade
from repositorios.modelos import (
    AgregadoDia,
    Avaliacao,
    Chamado,
    Jornada,
    OrigemJornada,
    StatusChamado,
)

# Os contadores diários `problema_sel#<id>` são gravados pelo dia UTC, então o dia do
# contador e o dia do período coincidem.
FUSO_REFERENCIA: Final = UTC
PERIODOS: Final = ("hoje", "7d", "30d", "personalizado")
PERIODO_PADRAO: Final = "7d"
MAX_DIAS_PERSONALIZADO: Final = 90
MAX_COMENTARIOS: Final = 10
MAX_CARACTERES_SOLUCAO: Final = 120
CHAVES_PRIMEIRO_NIVEL: Final = (
    "periodo",
    "modo_local",
    "satisfacao",
    "comentarios",
    "atendimento",
    "desfecho",
    "p1_risco",
    "ranking_problemas",
    "funil",
)

_DIAS_JANELA: Final = {"7d": 7, "30d": 30}
_FORMATO_DATA: Final = re.compile(r"\d{4}-\d{2}-\d{2}")


class ErroPeriodoInsights(ValueError):
    """Período inválido. `campo` é `periodo`, `inicio` ou `fim`."""

    def __init__(self, campo: str, motivo: str) -> None:
        super().__init__(f"{campo}: {motivo}")
        self.campo = campo
        self.motivo = motivo


@dataclass(frozen=True, slots=True)
class PeriodoInsights:
    """Período resolvido, no intervalo semiaberto `[inicio, fim)`."""

    id: str
    inicio: datetime
    fim: datetime


def _meia_noite(dia: date) -> datetime:
    return datetime.combine(dia, time(0, 0), tzinfo=FUSO_REFERENCIA)


def _ler_data(campo: str, valor: str | None) -> date:
    if valor is None or valor == "":
        raise ErroPeriodoInsights(campo, "obrigatório no período personalizado")
    if not isinstance(valor, str) or not _FORMATO_DATA.fullmatch(valor):
        raise ErroPeriodoInsights(campo, "use o formato AAAA-MM-DD")
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise ErroPeriodoInsights(campo, "data inexistente") from None


def resolver_periodo(
    agora: datetime,
    periodo: str | None,
    inicio: str | None,
    fim: str | None,
) -> PeriodoInsights:
    """Resolve o período de análise. Levanta `ErroPeriodoInsights` se for inválido."""
    identificador = PERIODO_PADRAO if periodo is None or periodo == "" else periodo
    if identificador not in PERIODOS:
        raise ErroPeriodoInsights("periodo", "valor não reconhecido")

    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=FUSO_REFERENCIA)
    agora = agora.astimezone(FUSO_REFERENCIA)

    if identificador in _DIAS_JANELA:
        # Próximo segundo inteiro depois de `agora`: um registro gravado no mesmo
        # instante da requisição entra no período.
        limite = agora.replace(microsecond=0) + timedelta(seconds=1)
        return PeriodoInsights(
            identificador, limite - timedelta(days=_DIAS_JANELA[identificador]), limite
        )

    if identificador == "hoje":
        dia = agora.date()
        return PeriodoInsights(
            identificador, _meia_noite(dia), _meia_noite(dia + timedelta(days=1))
        )

    dia_inicio = _ler_data("inicio", inicio)
    dia_fim = _ler_data("fim", fim)
    if dia_fim < dia_inicio:
        raise ErroPeriodoInsights("fim", "anterior a inicio")
    if (dia_fim - dia_inicio).days + 1 > MAX_DIAS_PERSONALIZADO:
        raise ErroPeriodoInsights(
            "fim", f"intervalo maior que {MAX_DIAS_PERSONALIZADO} dias"
        )
    return PeriodoInsights(
        identificador, _meia_noite(dia_inicio), _meia_noite(dia_fim + timedelta(days=1))
    )


@dataclass(frozen=True, slots=True)
class ChamadoInsights:
    """Projeção mínima de um Chamado (privacidade por construção).

    Fica de fora o pacote de repasse (resumo, modelo, série), o número do Chamado e o
    `jornada_id`. `desfecho`, `solucao_tipo` e `solucao` são `None` sem encerramento;
    o desfecho não é normalizado aqui.
    """

    prioridade: Prioridade
    status: StatusChamado
    criado_em: datetime
    assumido_em: datetime | None
    encerrado_em: datetime | None
    desfecho: str | None
    solucao_tipo: str | None
    solucao: str | None
    problema_id: int | None
    jornada_risco: bool

    @classmethod
    def de(cls, chamado: Chamado, jornada: Jornada | None) -> ChamadoInsights:
        """Jornada ausente vira `problema_id=None` e `jornada_risco=False`."""
        encerramento = chamado.encerramento
        return cls(
            prioridade=chamado.prioridade,
            status=chamado.status,
            criado_em=chamado.criado_em,
            assumido_em=(
                chamado.responsavel.inicio if chamado.responsavel is not None else None
            ),
            encerrado_em=None if encerramento is None else encerramento.em,
            desfecho=None if encerramento is None else encerramento.desfecho,
            solucao_tipo=None if encerramento is None else encerramento.solucao_tipo,
            solucao=None if encerramento is None else encerramento.solucao,
            problema_id=None if jornada is None else jornada.problema_id,
            jornada_risco=jornada is not None and jornada.risco is not None,
        )


@dataclass(frozen=True, slots=True)
class JornadaInsights:
    """Projeção mínima de uma Jornada encerrada: origem inicial e o encerramento."""

    origem_inicial: OrigemJornada
    encerramento: JornadaEncerrada

    @classmethod
    def de(cls, jornada: Jornada) -> JornadaInsights | None:
        """`None` se a Jornada não está encerrada."""
        if jornada.encerramento is None:
            return None
        return cls(
            origem_inicial=jornada.origem_inicial, encerramento=jornada.encerramento
        )

# --------------------------------------------------------------------------- auxiliares
# Arredondamento local (D8): o domínio só expõe a média por camada e seus auxiliares são
# privados. Mesma semântica: `Decimal`, `ROUND_HALF_UP`, 1 casa.
_DECIMO: Final = Decimal("0.1")
_CEM: Final = Decimal(100)
_NOTAS: Final = (1, 2, 3, 4, 5)
_CAMADAS_AVALIADAS: Final = ("guia", "humano")
DESFECHO_FALSO_DEFEITO: Final = "falso_defeito"
DESFECHO_DEFEITO_REAL: Final = "defeito_real"
DESFECHO_NAO_INFORMADO: Final = "nao_informado"
_DESFECHOS_RECONHECIDOS: Final = frozenset({DESFECHO_FALSO_DEFEITO, DESFECHO_DEFEITO_REAL})
def _arredondar(valor: Decimal) -> Decimal:
    return valor.quantize(_DECIMO, rounding=ROUND_HALF_UP)
def _pct(parte: int, total: int) -> Decimal | str:
    """Percentual com 1 casa (meio para cima); `SEM_DADOS` se `total` é 0."""
    if total == 0:
        return SEM_DADOS
    return _arredondar(Decimal(parte) * _CEM / Decimal(total))
def _media_nota(soma: int, quantidade: int) -> Decimal | str:
    """Média com 1 casa (meio para cima); `SEM_DADOS` se `quantidade` é 0."""
    if quantidade == 0:
        return SEM_DADOS
    return _arredondar(Decimal(soma) / Decimal(quantidade))
def _no_periodo(periodo: PeriodoInsights, instante: datetime) -> bool:
    """Intervalo semiaberto `[inicio, fim)`: a fronteira final nunca conta duas vezes."""
    return periodo.inicio <= instante < periodo.fim
def _avaliacoes_do_periodo(
    periodo: PeriodoInsights, avaliacoes: Iterable[Avaliacao]
) -> list[Avaliacao]:
    return [a for a in avaliacoes if _no_periodo(periodo, a.em)]
def _normalizar_desfecho(desfecho: str | None) -> str:
    if desfecho is not None and desfecho in _DESFECHOS_RECONHECIDOS:
        return desfecho
    return DESFECHO_NAO_INFORMADO
def _agregar(
    periodo: PeriodoInsights,
    *,
    chamados: Iterable[ChamadoInsights],
    avaliacoes: Iterable[Avaliacao],
    agregados: Iterable[AgregadoDia],
    titulos: Mapping[int, str],
    jornadas_encerradas: Iterable[JornadaInsights] | None,
) -> Metricas:
    """Prepara e executa a chamada única de `agregar_metricas`.
    Custo por minuto `0.00` (sem custo na resposta) e Jornadas sem a camada `ia`.
    `jornadas_encerradas=None` (leitura falhou) segue como lista vazia: o chamador decide
    omitir o funil. Todo filtro de período é refeito aqui, em `[inicio, fim)`.
    """
    jornadas = [
        j.encerramento
        for j in (jornadas_encerradas or ())
        if j.encerramento.camada != "ia" and _no_periodo(periodo, j.encerramento.encerrada_em)
    ]
    encerrados = [
        ChamadoEncerrado(
            numero="",
            jornada_id="",
            encerrado_em=c.encerrado_em,
            desfecho=_normalizar_desfecho(c.desfecho),
            inicio_atendimento=c.assumido_em,
        )
        for c in chamados
        if c.encerrado_em is not None and _no_periodo(periodo, c.encerrado_em)
    ]
    do_dominio = [
        AvaliacaoDominio(a.jornada_id, a.nota, a.camada, a.em)
        for a in _avaliacoes_do_periodo(periodo, avaliacoes)
    ]
    dias = [AgregadoDiaDominio(date.fromisoformat(a.dia), a.metrica, a.valor) for a in agregados]
    return agregar_metricas(
        jornadas,
        encerrados,
        do_dominio,
        dias,
        PeriodoMetricas(periodo.inicio, periodo.fim),
        ConfigMetricas(Decimal("0.00"), titulos),
    )
def _montar_satisfacao(
    periodo: PeriodoInsights, avaliacoes: Sequence[Avaliacao], metricas: Metricas
) -> dict[str, Any]:
    """`satisfacao`: média geral, total, 5 linhas de distribuição e `guia`/`humano`."""
    do_periodo = _avaliacoes_do_periodo(periodo, avaliacoes)
    total = len(do_periodo)
    quantidades = {nota: 0 for nota in _NOTAS}
    for a in do_periodo:
        quantidades[a.nota] += 1
    return {
        "nota_media": _media_nota(sum(a.nota for a in do_periodo), total),
        "total": total,
        "distribuicao": [
            {"nota": n, "quantidade": quantidades[n], "percentual": _pct(quantidades[n], total)}
            for n in _NOTAS
        ],
        "por_camada": [
            {
                "camada": c,
                "nota_media": metricas.camada(c).nota_media,
                "avaliacoes": metricas.camada(c).avaliacoes,
            }
            for c in _CAMADAS_AVALIADAS
        ],
    }
def _montar_comentarios(
    periodo: PeriodoInsights, avaliacoes: Sequence[Avaliacao]
) -> list[dict[str, Any]]:
    """`comentarios`: até 10, mais recentes primeiro, texto mascarado, só nota/em/texto."""
    candidatas = [
        a for a in _avaliacoes_do_periodo(periodo, avaliacoes) if a.comentario.strip()
    ]
    candidatas.sort(key=lambda a: (a.em, a.jornada_id), reverse=True)
    itens: list[dict[str, Any]] = []
    for a in candidatas:
        if len(itens) >= MAX_COMENTARIOS:
            break
        try:
            texto = mascarar_pii(a.comentario)
        except Exception:  # noqa: BLE001 - falha no mascaramento omite o comentário
            continue
        itens.append({"nota": a.nota, "em": a.em.isoformat(), "texto": texto})
    return itens

# -------------------------------------------------------------- atendimento e desfecho
_DESFECHOS_ORDEM: Final = (
    DESFECHO_FALSO_DEFEITO,
    DESFECHO_DEFEITO_REAL,
    DESFECHO_NAO_INFORMADO,
)


def _encerrados_do_periodo(
    periodo: PeriodoInsights, chamados: Iterable[ChamadoInsights]
) -> list[ChamadoInsights]:
    """Chamados_Encerrados cujo `encerrado_em` cai em `[inicio, fim)`."""
    return [
        c
        for c in chamados
        if c.encerrado_em is not None and _no_periodo(periodo, c.encerrado_em)
    ]


def _segundos(inicio: datetime, fim: datetime) -> int:
    """Duração inteira em segundos; negativa vale 0 (Req 5.6)."""
    return max(0, int((fim - inicio).total_seconds()))


def _resumir_tempos(duracoes: Sequence[int]) -> dict[str, Any]:
    """Média e mediana em `min:seg` e `quantidade`; `SEM_DADOS` sem durações."""
    n = len(duracoes)
    if n == 0:
        return {"media": SEM_DADOS, "mediana": SEM_DADOS, "quantidade": 0}
    ordenadas = sorted(max(0, d) for d in duracoes)
    media = (2 * sum(ordenadas) + n) // (2 * n)  # meio para cima, só inteiros
    meio = n // 2
    if n % 2 == 1:
        mediana = ordenadas[meio]
    else:
        mediana = (ordenadas[meio - 1] + ordenadas[meio] + 1) // 2
    return {
        "media": formatar_min_seg(media),
        "mediana": formatar_min_seg(mediana),
        "quantidade": n,
    }


def _montar_atendimento(
    periodo: PeriodoInsights, chamados: Sequence[ChamadoInsights]
) -> dict[str, Any]:
    """`atendimento`: tempos até assumir e até encerrar dos Chamados_Encerrados."""
    encerrados = _encerrados_do_periodo(periodo, chamados)
    ate_assumir = [
        _segundos(c.criado_em, c.assumido_em) for c in encerrados if c.assumido_em is not None
    ]
    ate_encerrar = [_segundos(c.criado_em, c.encerrado_em) for c in encerrados]  # type: ignore[arg-type]
    return {
        "ate_assumir": _resumir_tempos(ate_assumir),
        "ate_encerrar": _resumir_tempos(ate_encerrar),
    }


def _montar_desfecho(
    periodo: PeriodoInsights, chamados: Sequence[ChamadoInsights], metricas: Metricas
) -> dict[str, Any]:
    """`desfecho`: 3 linhas fixas somando `total`; precisão vinda de `agregar_metricas`."""
    encerrados = _encerrados_do_periodo(periodo, chamados)
    total = len(encerrados)
    quantidades = {d: 0 for d in _DESFECHOS_ORDEM}
    for c in encerrados:
        quantidades[_normalizar_desfecho(c.desfecho)] += 1
    return {
        "total": total,
        "itens": [
            {
                "desfecho": d,
                "quantidade": quantidades[d],
                "percentual": _pct(quantidades[d], total),
            }
            for d in _DESFECHOS_ORDEM
        ],
        "precisao_escalada_pct": metricas.precisao_escalada_pct,
    }


def _montar_p1_risco(
    periodo: PeriodoInsights, chamados: Sequence[ChamadoInsights]
) -> dict[str, int]:
    """`p1_risco`: P1 com risco criados no período e, entre eles, os não encerrados."""
    p1 = [
        c
        for c in chamados
        if c.prioridade == "P1" and c.jornada_risco and _no_periodo(periodo, c.criado_em)
    ]
    return {
        "total": len(p1),
        "nao_encerrados": sum(1 for c in p1 if c.status != "encerrado"),
    }


# ------------------------------------------------------------------- ranking e funil
_ORIGENS_ORDEM: Final = ("qr", "busca")
_CAMADAS_FUNIL: Final = ("guia", "humano", "abandonada")  # a camada `ia` fica de fora
MAX_ITENS_RANKING: Final = 10
_RETICENCIAS: Final = "…"


def _cortar_solucao(texto: str) -> str:
    """Corta em `MAX_CARACTERES_SOLUCAO` (reticências incluídas), só depois de mascarar."""
    if len(texto) <= MAX_CARACTERES_SOLUCAO:
        return texto
    return texto[: MAX_CARACTERES_SOLUCAO - 1] + _RETICENCIAS


def _solucao_mais_registrada(encerrados: Sequence[ChamadoInsights]) -> dict[str, Any] | str:
    """Grupo `(solucao_tipo, texto mascarado)` mais frequente; `SEM_DADOS` se não há nenhum.

    Empate: menor texto mascarado e depois menor `solucao_tipo`. Chamado cuja solução falha
    no mascaramento fica fora só desta contagem.
    """
    grupos: dict[tuple[str, str], int] = {}
    for c in encerrados:
        if c.solucao is None or not c.solucao.strip():
            continue
        try:
            texto = mascarar_pii(c.solucao)
        except Exception:  # noqa: BLE001 - falha no mascaramento tira o Chamado da contagem
            continue
        chave = (c.solucao_tipo or "", texto)
        grupos[chave] = grupos.get(chave, 0) + 1
    if not grupos:
        return SEM_DADOS
    (tipo, texto), quantidade = min(
        grupos.items(), key=lambda g: (-g[1], g[0][1], g[0][0])
    )
    return {
        "solucao_tipo": tipo,
        "solucao": _cortar_solucao(texto),
        "quantidade": quantidade,
    }


def _montar_ranking(
    periodo: PeriodoInsights,
    chamados: Sequence[ChamadoInsights],
    metricas: Metricas,
) -> list[dict[str, Any]]:
    """`ranking_problemas`: ordem, título e `selecoes` vêm do domínio, sem reordenar."""
    criados = [c for c in chamados if _no_periodo(periodo, c.criado_em)]
    encerrados = _encerrados_do_periodo(periodo, chamados)
    itens: list[dict[str, Any]] = []
    for item in metricas.ranking[:MAX_ITENS_RANKING]:
        do_problema = [c for c in encerrados if c.problema_id == item.problema_id]
        falsos = sum(
            1 for c in do_problema if _normalizar_desfecho(c.desfecho) == DESFECHO_FALSO_DEFEITO
        )
        itens.append(
            {
                "problema_id": item.problema_id,
                "titulo": item.titulo if item.titulo.strip() else f"Problema {item.problema_id}",
                "selecoes": item.jornadas,
                "chamados": sum(1 for c in criados if c.problema_id == item.problema_id),
                "falso_defeito_pct": _pct(falsos, len(do_problema)),
                "solucao_mais_registrada": _solucao_mais_registrada(do_problema),
            }
        )
    return itens


def _montar_funil(
    periodo: PeriodoInsights,
    jornadas_encerradas: Sequence[JornadaInsights] | None,
    metricas: Metricas,
) -> dict[str, Any] | None:
    """`funil`: `None` quando a leitura das Jornadas encerradas falhou."""
    if jornadas_encerradas is None:
        return None
    # Mesmo recorte de `_agregar`: sem a camada `ia` e dentro de `[inicio, fim)`.
    do_periodo = [
        j
        for j in jornadas_encerradas
        if j.encerramento.camada != "ia" and _no_periodo(periodo, j.encerramento.encerrada_em)
    ]
    total = len(do_periodo)
    return {
        "total_encerradas": metricas.total_encerradas,
        "por_origem": [
            {
                "origem": o,
                "quantidade": (n := sum(1 for j in do_periodo if j.origem_inicial == o)),
                "percentual": _pct(n, total),
            }
            for o in _ORIGENS_ORDEM
        ],
        "abandono_pct": metricas.camada("abandonada").deflexao_pct,
        "deflexao": [
            {
                "camada": c,
                "quantidade": metricas.camada(c).jornadas,
                "percentual": metricas.camada(c).deflexao_pct,
            }
            for c in _CAMADAS_FUNIL
        ],
    }


def montar_insights(
    periodo: PeriodoInsights,
    *,
    modo_local: bool,
    chamados: Sequence[ChamadoInsights],
    avaliacoes: Sequence[Avaliacao],
    agregados: Sequence[AgregadoDia],
    titulos: Mapping[int, str],
    jornadas_encerradas: Sequence[JornadaInsights] | None,
) -> dict[str, Any]:
    """Monta a resposta fechada de 9 chaves. Pura: sem I/O e sem relógio."""
    metricas = _agregar(
        periodo,
        chamados=chamados,
        avaliacoes=avaliacoes,
        agregados=agregados,
        titulos=titulos,
        jornadas_encerradas=jornadas_encerradas,
    )
    return {
        "periodo": {
            "id": periodo.id,
            "inicio": periodo.inicio.isoformat(),
            "fim": periodo.fim.isoformat(),
        },
        "modo_local": modo_local,
        "satisfacao": _montar_satisfacao(periodo, avaliacoes, metricas),
        "comentarios": _montar_comentarios(periodo, avaliacoes),
        "atendimento": _montar_atendimento(periodo, chamados),
        "desfecho": _montar_desfecho(periodo, chamados, metricas),
        "p1_risco": _montar_p1_risco(periodo, chamados),
        "ranking_problemas": _montar_ranking(periodo, chamados, metricas),
        "funil": _montar_funil(periodo, jornadas_encerradas, metricas),
    }
