"""Semente de demonstração: dados FICTÍCIOS distribuídos nos últimos 30 dias (Req 16).

SOMENTE PARA DEMO/DESENVOLVIMENTO. Este é o único lugar do repositório com código que cria
dados de demonstração (Req 16.13): nada em `services/`, `packages/`, `apps/` ou `infra/` importa
este módulo. Quem liga a semente é o ponto de entrada de linha de comando do `dev_local.py`.

O que a semente cria (57 Jornadas, 23 Chamados, 27 avaliações):
- 26 Jornadas resolvidas no guia (`guia`), 8 abandonadas (`abandonada`);
- 16 Chamados encerrados com atendimento (Jornada `humano`): P1 x3, P2 x8, P3 x5, com os dois
  Desfechos (7 `falso_defeito`, 9 `defeito_real`);
- 4 Chamados abertos (1 P1 de risco criado hoje; 1 com resposta não lida) e 3 em atendimento
  (1 parado há 100 minutos ou mais, para o motivo "Parado" do Dashboard);
- 6 problemas do catálogo com contadores diários `problema_sel#<id>` coerentes com as Jornadas.

Como os registros nascem (Req 16.16): só pelos métodos dos repositórios em memória
(`jornadas.criar/encerrar/marcar_abandono`, `ServicoEscalada.escalar`, `chamados.assumir/
encerrar`, `avaliacoes.registrar`, `agregados.incrementar`), então os invariantes dos
repositórios continuam valendo. Os Chamados usam a decisão real do Motor_Escalada.

Tempo (Req 16.10): `agora` entra por parâmetro, com fuso, e a função não lê o relógio. Todo
instante é `agora - deslocamento` com deslocamento >= 0, então nada fica no futuro. Os
deslocamentos vêm de `random.Random(SEMENTE_ALEATORIA)`; o gerador é consumido na mesma ordem
a cada execução, e o único ajuste que depende de `agora` é o limite das horas desde 00:00 UTC
dos registros "de hoje". Por isso `criar_semente(agora + k dias inteiros)` produz o mesmo
conjunto deslocado em `k` dias. O dia dos contadores usa `servicos.insights.FUSO_REFERENCIA`.

Sem PII (Req 16.11): ids opacos, textos fixos em português, sem dígitos, telefone, CEP, e-mail
ou CPF.
"""
from __future__ import annotations

import logging
import math
import random
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Final

_RAIZ = Path(__file__).resolve().parent.parent
for _caminho in (_RAIZ / "services" / "api", _RAIZ / "packages" / "dominio" / "src"):
    if str(_caminho) not in sys.path:
        sys.path.insert(0, str(_caminho))

import core  # noqa: E402,F401  (importar `core` antes de `servicos.*`: import circular conhecido)
from core.logs import Log  # noqa: E402
from repositorios.interfaces import Repositorios  # noqa: E402
from repositorios.modelos import (  # noqa: E402
    Avaliacao,
    EncerramentoChamado,
    Jornada,
    OrigemJornada,
    RiscoMarcado,
)
from servicos.escalada import ServicoEscalada  # noqa: E402
from servicos.insights import FUSO_REFERENCIA  # noqa: E402

SEMENTE_ALEATORIA: Final = 20250607
PREFIXO_JORNADA: Final = "01JSEMENTE"  # os exemplos usam "01JDEMO..."; ids distintos (Req 16.15)
PREFIXO_CHAMADO: Final = "TRES-SEM"  # + 7 dígitos = 10 caracteres Crockford válidos

#: Pesos dos 6 primeiros problemas do catálogo (soma de Jornadas com problema selecionado).
PESOS_PROBLEMAS: Final = (14, 10, 8, 6, 4, 3)

_DIA_S: Final = 86400
_ATENDENTE: Final = "atendente"
_NOME_ATENDENTE: Final = "Atendente"

# Comentários fictícios (sem dígitos, sem e-mail), por faixa de nota.
_COMENTARIOS_POSITIVOS: Final = (
    "Resolveu rápido, obrigado.",
    "Instruções claras e fáceis de seguir.",
    "Foi simples, funcionou de primeira.",
    "Atendimento muito atencioso.",
)
_COMENTARIOS_NEUTROS: Final = (
    "Funcionou, mas poderia ser mais direto.",
    "Demorou um pouco para entender o passo.",
)
_COMENTARIOS_NEGATIVOS: Final = (
    "Demorou mais do que eu esperava.",
    "O problema voltou depois do atendimento.",
    "Não consegui resolver sozinho.",
)

# Textos de solução (6 frases fixas, sem dígitos).
_SOLUCOES_MANUAL: Final = (
    "Orientada a limpeza do reservatório conforme o manual.",
    "Orientada a posição correta da tampa conforme o manual.",
    "Seguido o passo a passo do manual até o equipamento voltar a funcionar.",
)
_SOLUCOES_OUTRA: Final = (
    "Encaminhado para a assistência técnica autorizada.",
    "Peça substituída pela assistência técnica.",
    "Orientação da equipe resolveu a dúvida de uso.",
)

# Notas das 27 avaliações: cobre de 1 a 5 (o sorteio só embaralha).
_NOTAS: Final = (5,) * 10 + (4,) * 8 + (3,) * 4 + (2,) * 3 + (1,) * 2

# Jornadas `guia` (índice 0 a 25) com avaliação: 15 delas, incluindo as de "hoje" (0 e 1).
_GUIA_COM_AVALIACAO: Final = frozenset({0, 1, 3, 5, 6, 8, 10, 11, 13, 15, 17, 18, 20, 22, 24})

# Chamados encerrados (16): P1 x3, P2 x8, P3 x5. O índice 2 é o do dia corrente.
_PRIORIDADES_HUMANO: Final = (
    "P3", "P2", "P2", "P1", "P3", "P2", "P2", "P1",
    "P3", "P2", "P3", "P2", "P1", "P3", "P2", "P2",
)  # fmt: skip
_P2_FALSO_DEFEITO: Final = frozenset({1, 4})  # ocorrências (0-based) de P2 com falso_defeito
_GATILHO_POR_PRIORIDADE: Final = {
    "P1": "risco_seguranca",
    "P2": "instrucao_sem_solucao",
    "P3": "pedido_humano",
}
_FAIXA_ASSUMIR_S: Final = {"P1": (120, 1200), "P2": (600, 14400), "P3": (1800, 21600)}
_FAIXA_ATENDER_S: Final = (300, 144000)  # do assumir ao encerrar: 5 min a 40 h
_TOTAL_MAXIMO_S: Final = 47 * 3600  # da criação ao encerramento: abaixo de 48 h

_LOGGER_SILENCIOSO = logging.getLogger("semente_demo")
_LOGGER_SILENCIOSO.addHandler(logging.NullHandler())
_LOGGER_SILENCIOSO.propagate = False


@dataclass(frozen=True, slots=True)
class ResumoSemente:
    """Quantidades criadas. `contadores` = incrementos `problema_sel#<id>` aplicados."""

    jornadas: int
    chamados: int
    avaliacoes: int
    contadores: int


def id_jornada(indice: int) -> str:
    """`01JSEMENTE` + 16 dígitos: 26 caracteres Crockford (formato de ULID)."""
    return f"{PREFIXO_JORNADA}{indice:016d}"


class _Semeador:
    """Estado de uma execução: repositórios, relógio, gerador e contagens."""

    def __init__(self, repos: Repositorios, agora: datetime) -> None:
        self.repos = repos
        self.agora = agora
        self.rng = random.Random(SEMENTE_ALEATORIA)
        meia_noite = datetime.combine(
            agora.astimezone(FUSO_REFERENCIA).date(), time(0, 0), tzinfo=FUSO_REFERENCIA
        )
        self.segundos_hoje = max(0, int((agora - meia_noite).total_seconds()))
        self.cursor = agora
        self.proximo_numero = 0
        self.escalada = ServicoEscalada(
            repos,
            relogio=lambda: self.cursor,
            gerar_numero=self._gerar_numero,
            nome_modelo=self._nome_modelo,
            log=Log(_LOGGER_SILENCIOSO),
        )
        self.indice_jornada = 0
        self.jornadas = 0
        self.chamados = 0
        self.avaliacoes = 0
        self.contadores = 0
        self.notas = list(_NOTAS)
        self.rng.shuffle(self.notas)

        problemas = sorted(repos.catalogo.listar_problemas(), key=lambda p: p.problema_id)
        self.ids_problemas: list[int] = [p.problema_id for p in problemas[:6]]
        self.ids_modelos: list[str] = [m.modelo_id for m in repos.catalogo.listar_modelos()[:3]]

    # ------------------------------------------------------------------ auxiliares
    def _gerar_numero(self) -> str:
        self.proximo_numero += 1
        return f"{PREFIXO_CHAMADO}{self.proximo_numero:07d}"

    def _nome_modelo(self, modelo_id: str | None) -> str | None:
        modelo = None if modelo_id is None else self.repos.catalogo.obter_modelo(modelo_id)
        return modelo_id if modelo is None else modelo.nome

    def t(self, deslocamento_s: int | float) -> datetime:
        """Instante `agora - deslocamento` (deslocamento sempre >= 0)."""
        return self.agora - timedelta(seconds=max(0, int(deslocamento_s)))

    def problema(self, posicao: int) -> int | None:
        """Id do problema na posição `posicao` (0 a 5) do catálogo; `None` sem catálogo."""
        if not self.ids_problemas:
            return None
        return self.ids_problemas[posicao % len(self.ids_problemas)]

    def modelo(self, indice: int) -> str | None:
        return self.ids_modelos[indice % len(self.ids_modelos)] if self.ids_modelos else None

    def deslocamento_historico(self) -> int:
        """Segundos atrás, de 1 a cerca de 30 dias, mais denso nos últimos 7 dias."""
        faixa = self.rng.random()
        dias_recentes = self.rng.randint(1, 6)
        dias_antigos = self.rng.randint(7, 29)
        fracao = self.rng.randint(0, _DIA_S - 1)
        return (dias_recentes if faixa < 0.6 else dias_antigos) * _DIA_S + fracao

    def limitar_hoje(self, planejado_s: int) -> int:
        """Registro "de hoje": nunca antes das 00:00 do Fuso_Referencia."""
        return min(planejado_s, self.segundos_hoje)

    def logaritmico(self, minimo: int, maximo: int) -> int:
        return int(math.exp(self.rng.uniform(math.log(minimo), math.log(maximo))))

    # ------------------------------------------------------------------ registros
    def criar_jornada(
        self,
        *,
        criada_em: datetime,
        ultima_interacao: datetime,
        origem: OrigemJornada,
        modelo_id: str | None,
        problema_id: int | None,
        limite_selecao: datetime,
        risco_em: datetime | None = None,
        guia_respondeu_nao: bool = False,
    ) -> str:
        self.indice_jornada += 1
        jid = id_jornada(self.indice_jornada)
        resultado = self.repos.jornadas.criar(
            Jornada(
                jornada_id=jid,
                criada_em=criada_em,
                ultima_interacao=ultima_interacao,
                origem=origem,
                origem_inicial=origem,
                modelo_id=modelo_id,
                problema_id=problema_id,
                problemas_selecionados=() if problema_id is None else (problema_id,),
                risco=None if risco_em is None else RiscoMarcado("lista", risco_em),
                guia_respondeu_nao=guia_respondeu_nao,
            )
        )
        if not resultado.aplicado:
            raise RuntimeError(f"Jornada {jid} já existe")
        self.jornadas += 1
        if problema_id is not None:
            selecao = min(criada_em + timedelta(seconds=self.rng.randint(20, 60)), limite_selecao)
            dia: date = selecao.astimezone(FUSO_REFERENCIA).date()
            self.repos.agregados.incrementar(dia, f"problema_sel#{problema_id}")
            self.contadores += 1
        else:
            self.rng.randint(20, 60)  # mantém o consumo do gerador igual com e sem problema
        return jid

    def escalar(self, jid: str, instante: datetime, gatilho: str, prioridade: str) -> str:
        """Escala pelo ServicoEscalada com o relógio no `instante`; confere a prioridade."""
        self.cursor = instante
        resultado = self.escalada.escalar(jid, gatilho)  # type: ignore[arg-type]
        if not resultado.criado or resultado.chamado.prioridade != prioridade:
            raise RuntimeError(
                f"escalada inesperada para {jid}: {resultado.chamado.prioridade} != {prioridade}"
            )
        self.chamados += 1
        return resultado.numero

    def avaliar(
        self, jid: str, camada: str, instante: datetime, *, comentar_a_cada: int = 3
    ) -> None:
        indice = self.avaliacoes
        nota = self.proxima_nota()
        comentario = ""
        if indice % comentar_a_cada == 0:
            pool = (
                _COMENTARIOS_POSITIVOS
                if nota >= 4
                else _COMENTARIOS_NEUTROS
                if nota == 3
                else _COMENTARIOS_NEGATIVOS
            )
            comentario = pool[self.rng.randrange(len(pool))]
        resultado = self.repos.avaliacoes.registrar(
            Avaliacao(jid, nota, camada, instante, comentario)  # type: ignore[arg-type]
        )
        if not resultado.aplicado:
            raise RuntimeError(f"Avaliação de {jid} já existe")
        self.avaliacoes += 1

    def proxima_nota(self) -> int:
        return self.notas.pop(0)

    # ------------------------------------------------------------------ coortes
    def semear_guia(self) -> None:
        origens: list[OrigemJornada] = ["qr"] * 15 + ["busca"] * 11
        self.rng.shuffle(origens)
        posicoes = [0] * 6 + [1] * 5 + [2] * 5 + [3] * 3 + [4] * 4 + [5] * 3
        self.rng.shuffle(posicoes)
        for i in range(26):
            planejado = self.rng.randint(900, 40000)
            historico = self.deslocamento_historico()
            tempo_s = self.rng.randint(90, 900)
            atraso_avaliacao = self.rng.randint(20, 300)
            d_enc = self.limitar_hoje(planejado) if i < 3 else historico
            t_enc = self.t(d_enc)
            criada = t_enc - timedelta(seconds=tempo_s)
            pid = self.problema(posicoes[i])
            jid = self.criar_jornada(
                criada_em=criada,
                ultima_interacao=t_enc,
                origem=origens[i],
                modelo_id=self.modelo(i),
                problema_id=pid,
                limite_selecao=t_enc,
            )
            self.repos.jornadas.encerrar(jid, "guia", t_enc, problema_id=pid)
            if i in _GUIA_COM_AVALIACAO:
                t_aval = t_enc + timedelta(seconds=min(atraso_avaliacao, d_enc))
                self.avaliar(jid, "guia", t_aval)

    def semear_abandonadas(self) -> None:
        origens: list[OrigemJornada] = ["qr"] * 3 + ["busca"] * 5
        self.rng.shuffle(origens)
        for i in range(8):
            t_ab = self.t(self.deslocamento_historico())
            ultima = t_ab - timedelta(minutes=31, seconds=self.rng.randint(0, 1200))
            criada = ultima - timedelta(seconds=self.rng.randint(60, 600))
            jid = self.criar_jornada(
                criada_em=criada,
                ultima_interacao=ultima,
                origem=origens[i],
                modelo_id=self.modelo(i + 1),
                problema_id=None,
                limite_selecao=ultima,
            )
            self.repos.jornadas.marcar_abandono(jid, t_ab)

    def semear_humano(self) -> None:
        posicoes = [0] * 6 + [1] * 4 + [2] * 3 + [3] * 3
        self.rng.shuffle(posicoes)
        origens: list[OrigemJornada] = ["qr"] * 10 + ["busca"] * 6
        self.rng.shuffle(origens)
        ocorrencias_p2 = 0
        for i, prioridade in enumerate(_PRIORIDADES_HUMANO):
            minimo, maximo = _FAIXA_ASSUMIR_S[prioridade]
            assumir_s = self.logaritmico(minimo, maximo)
            atender_s = self.logaritmico(*_FAIXA_ATENDER_S)
            historico = self.deslocamento_historico()
            planejado_hoje = self.rng.randint(1800, 14000)
            preparo_s = self.rng.randint(30, 600)
            atraso_avaliacao = self.rng.randint(60, 900)
            if i == 0:
                assumir_s, atender_s = 21600, 144000  # extremos: 6 h até assumir, 40 h de atendimento
            elif i == 1:
                assumir_s, atender_s = 120, 300  # extremos: 2 min até assumir
            elif i == 2:
                assumir_s, atender_s = 900, 1800  # o encerrado do dia corrente
            atender_s = min(atender_s, _TOTAL_MAXIMO_S - assumir_s)

            if prioridade == "P1":
                desfecho = "defeito_real"
            elif prioridade == "P3":
                desfecho = "falso_defeito"
            else:
                desfecho = "falso_defeito" if ocorrencias_p2 in _P2_FALSO_DEFEITO else "defeito_real"
                ocorrencias_p2 += 1

            d_enc = self.limitar_hoje(planejado_hoje) if i == 2 else historico
            t_enc = self.t(d_enc)
            t_ass = t_enc - timedelta(seconds=atender_s)
            t_cri = t_ass - timedelta(seconds=assumir_s)
            t_jor = t_cri - timedelta(seconds=preparo_s)
            pid = self.problema(posicoes[i])
            numero = self._abrir_chamado(
                prioridade, t_jor, t_cri, origens[i], i, pid
            )
            self.repos.chamados.assumir(numero, _ATENDENTE, _NOME_ATENDENTE, t_ass)
            solucao_tipo, solucao = self.escolher_solucao(desfecho)
            self.repos.chamados.encerrar(
                numero, EncerramentoChamado(desfecho, solucao_tipo, solucao, t_enc, _ATENDENTE)
            )
            jid = self._jornada_do(numero)
            self.repos.jornadas.encerrar(
                jid, "humano", t_enc, Decimal("0"), pid, desfecho
            )
            if i % 4 != 3:  # 12 das 16 com avaliação
                t_aval = t_enc + timedelta(seconds=min(atraso_avaliacao, d_enc))
                self.avaliar(jid, "humano", t_aval)

    def semear_abertos_e_em_atendimento(self) -> None:
        # A1: P1 de risco criado hoje. A2: P2 com resposta não lida. A3 e A4: P3 sem responsável.
        a1 = self.limitar_hoje(self.rng.randint(900, 2400))
        a2 = self.rng.randint(3 * 3600, 8 * 3600)
        a3 = _DIA_S + self.rng.randint(0, 6 * 3600)
        a4 = self.rng.randint(2 * 3600, 5 * 3600)
        abertos = (
            ("P1", a1, self.problema(0), True),
            ("P2", a2, self.problema(1), False),
            ("P3", a3, None, False),
            ("P3", a4, None, False),
        )
        numeros: list[str] = []
        for k, (prioridade, d_cri, pid, _) in enumerate(abertos):
            t_cri = self.t(d_cri)
            t_jor = t_cri - timedelta(seconds=self.rng.randint(30, 300))
            numeros.append(
                self._abrir_chamado(prioridade, t_jor, t_cri, "qr" if k % 2 == 0 else "busca", k, pid)
            )
        # A2 tem resposta do Consumidor ainda não lida (motivo "Resposta não lida").
        self.repos.chamados.definir_resposta_nao_lida(numeros[1], True)

        # T1: P3 parado (responsável há 100 minutos ou mais, motivo "Parado").
        # T2: P2 criado e assumido hoje. T3: P3 assumido há 30 a 50 minutos (ainda não parado).
        d_ass_parado = self.rng.randint(6000, 14400)
        gap_parado = self.rng.randint(600, 3600)
        d_cri_t2 = self.limitar_hoje(self.rng.randint(2400, 3600))
        d_ass_t3 = self.rng.randint(1800, 3000)
        gap_t3 = self.rng.randint(300, 1200)
        em_atendimento = (
            ("P3", d_ass_parado, gap_parado, None),
            ("P2", d_cri_t2 // 2, d_cri_t2 - d_cri_t2 // 2, self.problema(0)),
            ("P3", d_ass_t3, gap_t3, None),
        )
        for k, (prioridade, d_ass, gap_s, pid) in enumerate(em_atendimento):
            t_ass = self.t(d_ass)
            t_cri = t_ass - timedelta(seconds=gap_s)
            t_jor = t_cri - timedelta(seconds=self.rng.randint(30, 300))
            numero = self._abrir_chamado(
                prioridade, t_jor, t_cri, "busca" if k % 2 == 0 else "qr", k + 4, pid
            )
            self.repos.chamados.assumir(numero, _ATENDENTE, _NOME_ATENDENTE, t_ass)

    # ------------------------------------------------------------------ pecas comuns
    def _abrir_chamado(
        self,
        prioridade: str,
        t_jor: datetime,
        t_cri: datetime,
        origem: OrigemJornada,
        indice_modelo: int,
        pid: int | None,
    ) -> str:
        """Cria a Jornada (com risco no P1 e "Não" no P2) e a escala; devolve o número."""
        risco_em = t_jor + timedelta(seconds=self.rng.randint(5, 25)) if prioridade == "P1" else None
        jid = self.criar_jornada(
            criada_em=t_jor,
            ultima_interacao=t_cri,
            origem=origem,
            modelo_id=self.modelo(indice_modelo),
            problema_id=pid,
            limite_selecao=t_cri,
            risco_em=risco_em,
            guia_respondeu_nao=prioridade == "P2",
        )
        return self.escalar(jid, t_cri, _GATILHO_POR_PRIORIDADE[prioridade], prioridade)

    def _jornada_do(self, numero: str) -> str:
        chamado = self.repos.chamados.obter(numero)
        assert chamado is not None
        return chamado.jornada_id

    def escolher_solucao(self, desfecho: str) -> tuple[str, str]:
        if desfecho == "falso_defeito":
            opcoes = [*_SOLUCOES_MANUAL, _SOLUCOES_OUTRA[2]]
        else:
            opcoes = list(_SOLUCOES_OUTRA[:2])
        texto = opcoes[self.rng.randrange(len(opcoes))]
        return ("instrução do manual" if texto in _SOLUCOES_MANUAL else "outra"), texto


def criar_semente(
    repos: Repositorios,
    *,
    agora: datetime,
    log: Callable[[str], None] = print,
) -> ResumoSemente:
    """Cria a semente fictícia em `repos` e devolve as quantidades criadas.

    `agora` precisa ter fuso (`ValueError` se for ingênuo). Se a primeira Jornada da semente já
    existe, não cria nada e devolve `ResumoSemente(0, 0, 0, 0)`.
    """
    if agora.tzinfo is None or agora.utcoffset() is None:
        raise ValueError("`agora` precisa ter fuso horário")
    if repos.jornadas.obter(id_jornada(1)) is not None:
        return ResumoSemente(0, 0, 0, 0)
    semeador = _Semeador(repos, agora)
    semeador.semear_guia()
    semeador.semear_abandonadas()
    semeador.semear_humano()
    semeador.semear_abertos_e_em_atendimento()
    resumo = ResumoSemente(
        jornadas=semeador.jornadas,
        chamados=semeador.chamados,
        avaliacoes=semeador.avaliacoes,
        contadores=semeador.contadores,
    )
    log(
        f"[demo] Semente de dados FICTÍCIOS criada: {resumo.jornadas} jornadas, "
        f"{resumo.chamados} chamados, {resumo.avaliacoes} avaliações."
    )
    return resumo
