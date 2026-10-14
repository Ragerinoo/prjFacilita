"""Agregação dos indicadores do Painel_Metricas (Req 17.3 a 17.11, 18.4).

Função pura: não faz I/O, não lê o relógio e só devolve **agregados** (contagens, taxas,
médias e ranking), nunca registros individuais de Jornada nem Dados_Pessoais (Req 18.4).

Convenções:
  * Período semiaberto ``[inicio, fim)`` com datetimes cientes de fuso e no máximo
    90 dias (Req 17.10). Jornadas e Chamados entram pela data de encerramento (Req 17.10);
    avaliações pela data da avaliação; contadores diários (`AgregadoDia`) pelos dias
    do calendário (no fuso de `inicio`) que o período toca.
  * Jornadas não encerradas, ou encerradas fora do período, nunca são contadas (Req 17.9).
  * Denominador zero devolve `SEM_DADOS` (Req 17.11), nunca 0 nem erro.
  * Percentuais com 1 casa (`Decimal`, meio para cima), custos com 2 casas, notas com
    1 casa e tempos como texto ``"min:seg"``.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, Literal

from dominio.encerramento import EstadoDaJornada
from dominio.erros import ErroDominio
from dominio.tipos import Camada, JornadaEncerrada

SEM_DADOS: Final = "sem dados"
SemDados = Literal["sem dados"]

PERIODO_MAXIMO: Final = timedelta(days=90)  # Req 17.10
CUSTO_MINUTO_MIN: Final = Decimal("0.00")  # Req 17.6
CUSTO_MINUTO_MAX: Final = Decimal("999.99")
TAMANHO_RANKING: Final = 10  # Req 17.8
DESFECHO_DEFEITO_REAL: Final = "defeito_real"

# Nomes das métricas em `agregados_dia` (design, tabela `agregados_dia`).
METRICA_IA_CACHE: Final = "ia_cache"
METRICA_IA_MODELO: Final = "ia_modelo"
PREFIXO_PROBLEMA_SEL: Final = "problema_sel#"

CAMADAS: Final[tuple[Camada, ...]] = ("guia", "ia", "humano", "abandonada")
_CAMADAS_RESOLVIDAS: Final[frozenset[Camada]] = frozenset({"guia", "ia", "humano"})

_DECIMO: Final = Decimal("0.1")
_CENTAVO: Final = Decimal("0.01")
_CEM: Final = Decimal(100)
_SEGUNDOS_POR_MINUTO: Final = Decimal(60)
_PROBLEMA_SEL = re.compile(re.escape(PREFIXO_PROBLEMA_SEL) + r"(\d+)")


class ErroMetricas(ErroDominio):
    """Entrada inválida para `agregar_metricas` (período, configuração ou nota)."""


@dataclass(frozen=True, slots=True)
class PeriodoMetricas:
    """Período ``[inicio, fim)`` de no máximo 90 dias (Req 17.10)."""

    inicio: datetime
    fim: datetime

    def __post_init__(self) -> None:
        for nome, valor in (("inicio", self.inicio), ("fim", self.fim)):
            if valor.tzinfo is None or valor.utcoffset() is None:
                raise ErroMetricas(f"{nome} deve ter fuso horário")
        if self.fim < self.inicio:
            raise ErroMetricas("o fim do período não pode ser anterior ao início")
        if self.fim - self.inicio > PERIODO_MAXIMO:
            raise ErroMetricas("o período máximo é de 90 dias")

    def contem(self, instante: datetime) -> bool:
        return self.inicio <= instante < self.fim

    def contem_dia(self, dia: date) -> bool:
        """O dia do calendário (fuso de `inicio`) é tocado pelo período."""
        if self.fim == self.inicio:
            return False
        ultimo = (self.fim - timedelta(microseconds=1)).astimezone(self.inicio.tzinfo).date()
        return self.inicio.date() <= dia <= ultimo


@dataclass(frozen=True, slots=True)
class ConfigMetricas:
    """Parâmetros da tabela `config` usados no cálculo.

    `custo_minuto_brl` aceita de 0,00 a 999,99 (Req 17.6). `titulos_problemas` mapeia
    `problema_id` para o título usado no ranking e no desempate alfabético.
    """

    custo_minuto_brl: Decimal
    titulos_problemas: Mapping[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not CUSTO_MINUTO_MIN <= self.custo_minuto_brl <= CUSTO_MINUTO_MAX:
            raise ErroMetricas("custo por minuto deve estar entre 0,00 e 999,99")


@dataclass(frozen=True, slots=True)
class ChamadoEncerrado:
    """Chamado encerrado (visão mínima). `desfecho`: ``defeito_real`` ou ``falso_defeito``.

    `inicio_atendimento` é o horário em que o Atendente assumiu (Req 14.5).
    """

    numero: str
    jornada_id: str
    encerrado_em: datetime
    desfecho: str
    inicio_atendimento: datetime | None = None


@dataclass(frozen=True, slots=True)
class Avaliacao:
    """Avaliação de uma Jornada (uma por Jornada), nota de 1 a 5."""

    jornada_id: str
    nota: int
    camada: Camada
    em: datetime


@dataclass(frozen=True, slots=True)
class AgregadoDia:
    """Contador diário (`agregados_dia`): ``ia_cache``, ``ia_modelo``, ``problema_sel#<id>``."""

    dia: date
    metrica: str
    valor: int


@dataclass(frozen=True, slots=True)
class IndicadorCamada:
    """Indicadores de uma camada. `None` = não se aplica (abandonada não tem tempo/custo)."""

    camada: Camada
    jornadas: int
    deflexao_pct: Decimal | SemDados
    tempo_medio: str | SemDados | None
    custo_medio_brl: Decimal | SemDados | None
    nota_media: Decimal | SemDados
    avaliacoes: int


@dataclass(frozen=True, slots=True)
class ItemRanking:
    problema_id: int
    titulo: str
    jornadas: int


@dataclass(frozen=True, slots=True)
class Metricas:
    """Resultado agregado do período. Só agregados (Req 18.4)."""

    periodo: PeriodoMetricas
    total_encerradas: int
    camadas: tuple[IndicadorCamada, ...]  # guia, ia, humano, abandonada
    chamados_encerrados: int
    precisao_escalada_pct: Decimal | SemDados
    respostas_ia: int
    acerto_cache_pct: Decimal | SemDados
    ranking: tuple[ItemRanking, ...]

    def camada(self, nome: Camada) -> IndicadorCamada:
        return next(c for c in self.camadas if c.camada == nome)


# --------------------------------------------------------------------------- auxiliares


def formatar_min_seg(segundos: int) -> str:
    """``312`` -> ``"5:12"``. Minutos não são limitados a 59 (``"75:03"``)."""
    minutos, resto = divmod(max(0, segundos), 60)
    return f"{minutos}:{resto:02d}"


def _pct(parte: int, total: int) -> Decimal | SemDados:
    if total == 0:
        return SEM_DADOS
    return (Decimal(parte) * _CEM / Decimal(total)).quantize(_DECIMO, rounding=ROUND_HALF_UP)


def _media(soma: Decimal, quantidade: int, casas: Decimal) -> Decimal | SemDados:
    if quantidade == 0:
        return SEM_DADOS
    return (soma / Decimal(quantidade)).quantize(casas, rounding=ROUND_HALF_UP)


def _encerramentos(
    jornadas: Iterable[EstadoDaJornada | JornadaEncerrada], periodo: PeriodoMetricas
) -> list[JornadaEncerrada]:
    """Só Jornadas encerradas dentro do período (Req 17.9)."""
    achadas: list[JornadaEncerrada] = []
    for j in jornadas:
        enc = j.encerramento if isinstance(j, EstadoDaJornada) else j
        if enc is not None and periodo.contem(enc.encerrada_em):
            achadas.append(enc)
    return achadas


def _minutos_humano(chamado: ChamadoEncerrado | None) -> Decimal:
    if chamado is None or chamado.inicio_atendimento is None:
        return Decimal(0)
    segundos = max(0, int((chamado.encerrado_em - chamado.inicio_atendimento).total_seconds()))
    return Decimal(segundos) / _SEGUNDOS_POR_MINUTO


def _chave_alfabetica(titulo: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", titulo)
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).casefold()


def _ranking(
    agregados: Iterable[AgregadoDia], periodo: PeriodoMetricas, titulos: Mapping[int, str]
) -> tuple[ItemRanking, ...]:
    contagem: dict[int, int] = {}
    for a in agregados:
        casou = _PROBLEMA_SEL.fullmatch(a.metrica)
        if casou and a.valor > 0 and periodo.contem_dia(a.dia):
            pid = int(casou.group(1))
            contagem[pid] = contagem.get(pid, 0) + a.valor
    itens = [ItemRanking(p, titulos.get(p, f"Problema {p}"), n) for p, n in contagem.items()]
    itens.sort(key=lambda i: (-i.jornadas, _chave_alfabetica(i.titulo), i.titulo, i.problema_id))
    return tuple(itens[:TAMANHO_RANKING])


def _contar_metrica(agregados: Iterable[AgregadoDia], periodo: PeriodoMetricas, nome: str) -> int:
    return sum(a.valor for a in agregados if a.metrica == nome and periodo.contem_dia(a.dia))


# --------------------------------------------------------------------------- principal


def agregar_metricas(
    jornadas: Iterable[EstadoDaJornada | JornadaEncerrada],
    chamados: Iterable[ChamadoEncerrado],
    avaliacoes: Iterable[Avaliacao],
    agregados_dia: Iterable[AgregadoDia],
    periodo: PeriodoMetricas,
    cfg: ConfigMetricas,
) -> Metricas:
    """Calcula todos os indicadores do período (Req 17.3 a 17.11).

    * Deflexão (17.3): Jornadas encerradas na camada / total encerrado no período.
    * Precisão da escalada (17.4): Chamados ``defeito_real`` / Chamados encerrados.
    * Tempo médio (17.5): média de `tempo_s` em guia, ia e humano, sem abandonadas.
    * Custo médio (17.6): guia = 0; ia = média do `custo_brl` das Jornadas (soma do
      custo de tokens); humano = minutos de atendimento × `custo_minuto_brl`, onde os
      minutos vão de `inicio_atendimento` ao encerramento do Chamado da Jornada (0 se
      o Chamado ou o início não existirem).
    * Acerto do cache (17.7): ``ia_cache`` / (``ia_cache`` + ``ia_modelo``).
    * Ranking (17.8): 10 mais selecionados, empate por título (sem acento e caixa).
    * Nota média (1 casa) e quantidade de avaliações por camada (17.8).
    """
    encerradas = _encerramentos(jornadas, periodo)
    lista_chamados = [c for c in chamados if periodo.contem(c.encerrado_em)]
    agregados = list(agregados_dia)
    chamado_por_jornada = {c.jornada_id: c for c in lista_chamados}

    notas: dict[Camada, list[int]] = {c: [] for c in CAMADAS}
    for av in avaliacoes:
        if not periodo.contem(av.em):
            continue
        if isinstance(av.nota, bool) or not 1 <= av.nota <= 5:
            raise ErroMetricas("a nota de avaliação deve estar entre 1 e 5")
        notas[av.camada].append(av.nota)

    total = len(encerradas)
    indicadores: list[IndicadorCamada] = []
    for camada in CAMADAS:
        da_camada = [j for j in encerradas if j.camada == camada]
        n = len(da_camada)
        tempo: str | SemDados | None = None
        custo: Decimal | SemDados | None = None
        if camada in _CAMADAS_RESOLVIDAS:
            media_s = _media(Decimal(sum(j.tempo_s for j in da_camada)), n, Decimal(1))
            tempo = media_s if media_s == SEM_DADOS else formatar_min_seg(int(media_s))
            if camada == "guia":
                custo = _media(Decimal(0), n, _CENTAVO)
            elif camada == "ia":
                custo = _media(sum((j.custo_brl for j in da_camada), Decimal(0)), n, _CENTAVO)
            else:
                minutos = sum(
                    (_minutos_humano(chamado_por_jornada.get(j.jornada_id)) for j in da_camada),
                    Decimal(0),
                )
                custo = _media(minutos * cfg.custo_minuto_brl, n, _CENTAVO)
        da_nota = notas[camada]
        indicadores.append(
            IndicadorCamada(
                camada=camada,
                jornadas=n,
                deflexao_pct=_pct(n, total),
                tempo_medio=tempo,
                custo_medio_brl=custo,
                nota_media=_media(Decimal(sum(da_nota)), len(da_nota), _DECIMO),
                avaliacoes=len(da_nota),
            )
        )

    reais = sum(1 for c in lista_chamados if c.desfecho == DESFECHO_DEFEITO_REAL)
    do_cache = _contar_metrica(agregados, periodo, METRICA_IA_CACHE)
    do_modelo = _contar_metrica(agregados, periodo, METRICA_IA_MODELO)

    return Metricas(
        periodo=periodo,
        total_encerradas=total,
        camadas=tuple(indicadores),
        chamados_encerrados=len(lista_chamados),
        precisao_escalada_pct=_pct(reais, len(lista_chamados)),
        respostas_ia=do_cache + do_modelo,
        acerto_cache_pct=_pct(do_cache, do_cache + do_modelo),
        ranking=_ranking(agregados, periodo, cfg.titulos_problemas),
    )
