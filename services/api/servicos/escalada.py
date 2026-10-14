"""Serviço de escalada e marcação de risco (tarefa 12.1).

Requisitos: 8.1, 8.2, 8.4, 8.5, 8.7, 9.1, 9.7, 9.8, 9.9, 9.10, 10.2, 11.1 a 11.4, 11.6 a 11.8.

Duas operações, usadas pelas rotas da tarefa 12.3 (`/mensagens`, `/vazamento`, `/resolucao`,
`/escalar`) e pelo pipeline do assistente:

  `marcar_risco(jornada_id, origem)`
      Grava a marcação de risco (`lista`, `ia` ou `guia`), monotônica: a primeira origem e o
      primeiro horário ficam (Req 8.4). Em seguida pede a escalada P1 com o gatilho
      `risco_seguranca`. A escalada acontece uma vez por Jornada (Req 8.5): marcações repetidas,
      de qualquer origem, não criam outro Chamado. Se já existe um Chamado P3 ou P2, ele é
      reavaliado para P1 no mesmo registro, sem Chamado novo (Req 9.9, 11.6).

  `escalar(jornada_id, gatilho)`
      1. Lê a Jornada e consolida os fatos (`risco_seguranca`, `guia_respondeu_nao`).
      2. Registra o gatilho como evento. Se falhar, a escalada segue e o gatilho é marcado
         "não registrado" no Chamado (Req 9.10; o marcador fica fora do Pacote, que não muda).
      3. `decidir_escalada` (Motor_Escalada, puro) sobre os fatos consolidados, uma única vez.
      4. Número `TRES-` + 10 caracteres Crockford aleatórios (não sequencial). Colisão
         (`numero_em_uso`) gera outro número.
      5. Pacote determinístico com os três campos de IA em valores provisórios (Req 10.2, 10.4)
         e `pacote_ia_status = pendente`; `criar_com_escalada` grava Chamado e Jornada numa
         transação só (Req 9.9, 11.7).
      6. P2: cria a Ordem_Servico em rascunho (chave `OS#<numero>`). Falha NÃO desfaz o
         Chamado: `os_status = falha` (Req 11.8).
      7. Dispara o enriquecimento assíncrono (resumo, sentimento e próxima ação). Falha não
         afeta o Chamado: o Pacote provisório já é válido (Req 10.4, 10.8).
      Jornada já escalada: devolve o Chamado existente, registra o gatilho adicional (Req 9.9)
      e reavalia a prioridade, que nunca diminui (Req 8.5, 11.6).

Contrato do histórico "já tentado" (Req 10.2): eventos da Jornada com `tipo == "passo_concluido"`
e `dados = {"passo": str, "camada": "guia"|"ia", "resultado": "sim"|"não"|"sem resposta"}`.
Eventos fora desse formato são ignorados; `camada` e `resultado` ausentes viram "guia" e
"sem resposta".

Sem PII: o serviço não lê nem grava telefone ou CEP; os logs levam só identificadores opacos.
"""

from __future__ import annotations

import dataclasses
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Protocol

from core.contexto import agora_utc
from core.logs import Log
from dominio import (
    CamposDeterministicos,
    DecisaoEscalada,
    FatosJornada,
    ItemJaTentado,
    Prioridade,
    dados_pessoais_solicitados,
    decidir_escalada,
    pacote_fallback,
    reavaliar_prioridade,
)
from dominio.pacote import NAO_INFORMADO, esquema_pacote
from dominio.tipos import Gatilho
from repositorios.erros import ErroNaoEncontrado, ErroRepositorio
from repositorios.ids import novo_ulid
from repositorios.interfaces import Repositorios
from repositorios.modelos import (
    Chamado,
    DecisaoRegistrada,
    Evento,
    GatilhoRegistrado,
    Jornada,
    OrdemServico,
    OrigemRisco,
)

# --------------------------------------------------------------------------- constantes

PREFIXO_NUMERO: Final = "TRES-"
TAMANHO_SUFIXO_NUMERO: Final = 10
#: Crockford base32 (sem I, L, O, U): o mesmo conjunto do padrão do esquema do Pacote.
ALFABETO_CROCKFORD: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
MAX_TENTATIVAS_NUMERO: Final = 5

TIPO_EVENTO_GATILHO: Final = "escalada_gatilho"
TIPOS_EVENTO_PASSO: Final = frozenset({"passo_concluido"})
#: Resposta "Sim/Não" do Consumidor à instrução do guia (`POST /jornadas/{id}/resolucao`, tarefa
#: 12.3). `dados = {"problema_id": int, "resolvido": bool}`. Um "Não" marca como "não" o
#: resultado dos passos ainda "sem resposta" daquele problema, no histórico "já tentado".
TIPO_EVENTO_RESOLUCAO_GUIA: Final = "resolucao_guia"
MAX_PASSO: Final = 200  # Pacote_Repasse: `ja_tentado[].passo`
MAX_MODELO: Final = 80  # Pacote_Repasse: `modelo`

#: Categorias do Pacote por `problema_id` (1 a 13, ordem do Req 3.1); fora da lista: "outro".
_CATEGORIAS: Final[tuple[str, ...]] = tuple(esquema_pacote()["properties"]["categoria"]["enum"])
CATEGORIA_OUTRO: Final = "outro"

_CAMADAS_PASSO: Final = frozenset({"guia", "ia"})
_RESULTADOS_PASSO: Final = frozenset({"sim", "não", "sem resposta"})

#: Resposta do serviço sem Chamado nem rótulo técnico quando o repasse não pôde ser feito.
CONTATO_CONFIRMADO: Final = "confirmado"
CONTATO_PENDENTE: Final = "pendente"
CONTATO_NAO_REGISTRADO: Final = "nao_registrado"


# ------------------------------------------------------------------ rótulos e prazos (Req 12.1)


@dataclass(frozen=True, slots=True)
class ApresentacaoPrioridade:
    """Texto que o Consumidor vê no lugar de P1, P2 e P3 (Req 12.1). Sem siglas nem jargão."""

    rotulo: str
    prazo: str
    proximo_passo: str


_APRESENTACAO: Final[dict[Prioridade, ApresentacaoPrioridade]] = {
    "P1": ApresentacaoPrioridade(
        rotulo="Atendimento urgente",
        prazo="ligação em até 15 minutos",
        proximo_passo="Uma pessoa da nossa equipe vai ligar para você em até 15 minutos.",
    ),
    "P2": ApresentacaoPrioridade(
        rotulo="Atendimento prioritário",
        prazo="contato em até 4 horas úteis",
        proximo_passo="Uma pessoa da nossa equipe vai entrar em contato em até 4 horas úteis.",
    ),
    "P3": ApresentacaoPrioridade(
        rotulo="Atendimento por mensagem",
        prazo="resposta em até 1 dia útil",
        proximo_passo="Uma pessoa da nossa equipe vai responder em até 1 dia útil.",
    ),
}


def apresentar_prioridade(prioridade: Prioridade) -> ApresentacaoPrioridade:
    """Rótulo, prazo e próximo passo em linguagem simples (P1: 15 min; P2: 4 h úteis; P3: 1 dia)."""
    try:
        return _APRESENTACAO[prioridade]
    except KeyError:
        raise ValueError(f"Prioridade desconhecida: {prioridade!r}") from None


# ------------------------------------------------------------------------- número do Chamado


def gerar_numero_chamado(sortear_bits: Callable[[int], int] = secrets.randbits) -> str:
    """`TRES-` + 10 caracteres Crockford aleatórios (50 bits), nada sequencial (design 3.2)."""
    valor = sortear_bits(5 * TAMANHO_SUFIXO_NUMERO)
    letras = []
    for _ in range(TAMANHO_SUFIXO_NUMERO):
        letras.append(ALFABETO_CROCKFORD[valor & 0x1F])
        valor >>= 5
    return PREFIXO_NUMERO + "".join(reversed(letras))


# ------------------------------------------------------------------------ envelope da Jornada


def estado_publico(jornada: Jornada) -> str:
    """Estado da Jornada no vocabulário do front-end (`armazemRisco.ts`)."""
    if jornada.estado != "encerrada":
        return jornada.estado
    camada = jornada.encerramento.camada if jornada.encerramento else None
    return "abandonada" if camada == "abandonada" else f"encerrada_{camada or 'guia'}"


def _iso(momento: datetime) -> str:
    return momento.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def situacao_contato(
    jornada: Jornada, chamado: Chamado | None, repasse_falhou: bool = False
) -> str:
    """Estado do repasse ao CS para o alerta de risco (Req 8.5, 8.6).

    `confirmado`: há Chamado e, se a Jornada tem risco, ele já é P1. `nao_registrado`: o repasse
    falhou agora (`repasse_falhou`) e ainda não há Chamado P1. `pendente`: o resto.
    """
    risco = jornada.risco is not None
    registrado = chamado is not None and (not risco or chamado.prioridade == "P1")
    if registrado:
        return CONTATO_CONFIRMADO
    return CONTATO_NAO_REGISTRADO if repasse_falhou else CONTATO_PENDENTE


def envelope_jornada(
    jornada: Jornada, chamado: Chamado | None = None, *, repasse_falhou: bool = False
) -> dict[str, Any]:
    """Envelope `jornada` das respostas públicas (contrato em `apps/web/src/risco/armazemRisco.ts`).

    `{jornada_id, estado, risco: {marcado, origem?, em?}, contato_cs}`. Só informa o que o
    servidor gravou; o cliente não consegue remover a marcação (Req 8.4).
    """
    risco: dict[str, Any] = {"marcado": jornada.risco is not None}
    if jornada.risco is not None:
        risco["origem"] = jornada.risco.origem
        risco["em"] = _iso(jornada.risco.em)
    return {
        "jornada_id": jornada.jornada_id,
        "estado": estado_publico(jornada),
        "risco": risco,
        "contato_cs": situacao_contato(jornada, chamado, repasse_falhou),
    }


# ----------------------------------------------------------------------------- portas


class DisparadorEnriquecimento(Protocol):
    """Porta que dispara, sem esperar, o enriquecimento do Pacote (tarefa 12.2).

    Produção: `lambda:InvokeFunction` com `InvocationType="Event"` na Lambda `enriquecimento`.
    A chamada precisa ser rápida e pode levantar exceção: o serviço a ignora (só registra).
    """

    def disparar(self, numero: str) -> None: ...


class DisparadorEnriquecimentoFake:
    """Fake de testes: guarda os números disparados e pode simular falha."""

    def __init__(self, erro: Exception | None = None) -> None:
        self.disparados: list[str] = []
        self.erro = erro

    def disparar(self, numero: str) -> None:
        if self.erro is not None:
            raise self.erro
        self.disparados.append(numero)


class DisparadorEnriquecimentoNulo:
    """Padrão quando nada foi configurado: não faz nada (o Pacote provisório já é válido)."""

    def disparar(self, numero: str) -> None:
        return None


# -------------------------------------------------------------------------------- resultados


@dataclass(frozen=True, slots=True)
class ResultadoEscalada:
    """Desfecho de `escalar`, com o que as rotas precisam devolver ao Consumidor (Req 12.1).

    `criado`: este chamado criou o Chamado. Falso = a Jornada já tinha um (idempotência) e
    `chamado` é o existente. `prioridade_elevada`: a reavaliação subiu a prioridade.
    `gatilho_registrado`: o gatilho desta chamada ficou gravado na Jornada.
    """

    chamado: Chamado
    jornada: Jornada
    criado: bool
    prioridade_elevada: bool
    gatilho_registrado: bool

    @property
    def numero(self) -> str:
        return self.chamado.numero

    @property
    def apresentacao(self) -> ApresentacaoPrioridade:
        return apresentar_prioridade(self.chamado.prioridade)

    @property
    def envelope(self) -> dict[str, Any]:
        return envelope_jornada(self.jornada, self.chamado)

    def para_dict(self) -> dict[str, Any]:
        """Corpo da resposta ao Consumidor. Não expõe P1, P2 ou P3 nem Dados_Pessoais."""
        a = self.apresentacao
        c = self.chamado
        return {
            "chamado": {
                "numero": c.numero,
                "prioridade_rotulo": a.rotulo,
                "prazo": a.prazo,
                "proximo_passo": a.proximo_passo,
                "classificacao": c.classificacao,
                "dados_solicitados": list(dados_pessoais_solicitados(c.prioridade)),
                "criado_em": _iso(c.criado_em),
            },
            "novo": self.criado,
            "jornada": self.envelope,
        }


@dataclass(frozen=True, slots=True)
class ResultadoMarcacaoRisco:
    """Desfecho de `marcar_risco`.

    `nova_marcacao`: esta chamada gravou a marcação (a primeira origem vence). `escalada` é None
    quando o repasse falhou (`repasse_falhou`): a marcação fica e o front-end oferece "Tentar
    novamente" (Req 8.6), que chama `escalar` de novo.
    """

    jornada: Jornada
    nova_marcacao: bool
    escalada: ResultadoEscalada | None
    repasse_falhou: bool = False

    @property
    def envelope(self) -> dict[str, Any]:
        chamado = self.escalada.chamado if self.escalada else None
        return envelope_jornada(self.jornada, chamado, repasse_falhou=self.repasse_falhou)

    def para_dict(self) -> dict[str, Any]:
        corpo: dict[str, Any] = self.escalada.para_dict() if self.escalada else {}
        corpo["jornada"] = self.envelope
        return corpo


# ------------------------------------------------------------------------- funções auxiliares


def categoria_do_problema(problema_id: int | None) -> str:
    """Categoria do Pacote (um dos 13 Problemas_Catalogados ou "outro", Req 10.1)."""
    if problema_id is None or isinstance(problema_id, bool) or not 1 <= problema_id <= 13:
        return CATEGORIA_OUTRO
    return _CATEGORIAS[problema_id - 1]


def ja_tentado_de_eventos(eventos: list[Evento]) -> tuple[ItemJaTentado, ...]:
    """Itens "já tentado" em ordem cronológica, a partir dos eventos da Jornada (ver docstring)."""
    itens: list[ItemJaTentado] = []
    problemas: list[object] = []  # `problema_id` de cada item, em paralelo a `itens`
    for evento in eventos:
        if evento.tipo == TIPO_EVENTO_RESOLUCAO_GUIA and evento.dados.get("resolvido") is False:
            for i, item in enumerate(itens):
                if (
                    item.camada == "guia"
                    and item.resultado == "sem resposta"
                    and problemas[i] == evento.dados.get("problema_id")
                ):
                    itens[i] = dataclasses.replace(item, resultado="não")
            continue
        if evento.tipo not in TIPOS_EVENTO_PASSO:
            continue
        dados = evento.dados
        passo = dados.get("passo")
        if not isinstance(passo, str) or not passo.strip():
            continue
        camada = dados.get("camada")
        resultado = dados.get("resultado")
        itens.append(
            ItemJaTentado(
                passo=passo.strip()[:MAX_PASSO],
                camada=camada if camada in _CAMADAS_PASSO else "guia",  # type: ignore[arg-type]
                resultado=resultado if resultado in _RESULTADOS_PASSO else "sem resposta",  # type: ignore[arg-type]
            )
        )
        problemas.append(dados.get("problema_id"))
    return tuple(itens)


def _nome_modelo_padrao(modelo_id: str | None) -> str | None:
    return modelo_id


# ------------------------------------------------------------------------------- o serviço


class ServicoEscalada:
    """Escalada e marcação de risco. Tudo é injetado: repositórios, relógio e geradores."""

    def __init__(
        self,
        repos: Repositorios,
        *,
        relogio: Callable[[], datetime] = agora_utc,
        gerar_numero: Callable[[], str] = gerar_numero_chamado,
        disparador: DisparadorEnriquecimento | None = None,
        nome_modelo: Callable[[str | None], str | None] = _nome_modelo_padrao,
        log: Log | None = None,
    ) -> None:
        """`nome_modelo` converte `modelo_id` no nome do catálogo para o Pacote (até 80
        caracteres); sem nome, o Pacote usa o próprio `modelo_id` ou "não informado"."""
        self._repos = repos
        self._relogio = relogio
        self._gerar_numero = gerar_numero
        self._disparador: DisparadorEnriquecimento = disparador or DisparadorEnriquecimentoNulo()
        self._nome_modelo = nome_modelo
        self._log = log or Log()

    # ------------------------------------------------------------------- marcação de risco

    def marcar_risco(self, jornada_id: str, origem: OrigemRisco) -> ResultadoMarcacaoRisco:
        """Marca risco (monotônico) e garante a escalada P1, uma por Jornada.

        Jornada inexistente levanta `ErroNaoEncontrado`. Qualquer outra falha do repasse NÃO
        remove nem impede a marcação: o resultado traz `repasse_falhou=True` (Req 8.6).
        """
        agora = self._relogio()
        nova = False
        try:
            marcacao = self._repos.jornadas.marcar_risco(jornada_id, origem, agora)
            nova = marcacao.aplicado
        except ErroNaoEncontrado:
            raise
        except ErroRepositorio as exc:
            # Escalar mesmo assim: `escalar` tenta gravar a marcação de novo (segurança primeiro).
            self._log.erro("risco_marcacao_falhou", jornada_id=jornada_id, erro=exc)
        if nova:
            self._log.info("risco_marcado", jornada_id=jornada_id, origem=origem)
        try:
            escalada = self.escalar(jornada_id, "risco_seguranca", origem_risco=origem)
        except ErroNaoEncontrado:
            raise
        except Exception as exc:  # noqa: BLE001 - o repasse falhou; a marcação permanece
            self._log.erro("risco_repasse_falhou", jornada_id=jornada_id, erro=exc)
            return ResultadoMarcacaoRisco(
                jornada=self._obter(jornada_id),
                nova_marcacao=nova,
                escalada=None,
                repasse_falhou=True,
            )
        return ResultadoMarcacaoRisco(
            jornada=escalada.jornada, nova_marcacao=nova, escalada=escalada
        )

    # ------------------------------------------------------------------------------ escalar

    def escalar(
        self,
        jornada_id: str,
        gatilho: Gatilho,
        *,
        origem_risco: OrigemRisco = "lista",
    ) -> ResultadoEscalada:
        """Escala a Jornada (idempotente). Ver a docstring do módulo para os passos.

        `origem_risco` só vale para `gatilho == "risco_seguranca"` numa Jornada ainda sem
        marcação (nesse caso a marcação é gravada aqui, com essa origem).
        Levanta `ErroNaoEncontrado` (Jornada inexistente) ou `ErroRepositorio` (a transação
        do Chamado falhou; nada foi gravado e a chamada pode ser repetida).
        """
        jornada = self._obter(jornada_id)
        if gatilho == "risco_seguranca" and jornada.risco is None:
            jornada = self._garantir_marcacao(jornada, origem_risco)
        if jornada.escalada is not None:
            return self._ja_escalada(jornada, gatilho)

        fatos = self._consolidar_fatos(jornada, gatilho)
        agora = self._relogio()
        registrado = self._registrar_gatilho_evento(jornada, gatilho, agora)
        decisao = decidir_escalada(fatos)
        ja_tentado = self._ja_tentado(jornada_id)

        for _ in range(MAX_TENTATIVAS_NUMERO):
            numero = self._gerar_numero()
            chamado = self._montar_chamado(
                numero, jornada, decisao, ja_tentado, agora, gatilho_nao_registrado=not registrado
            )
            resultado = self._repos.chamados.criar_com_escalada(
                chamado,
                GatilhoRegistrado(gatilho, agora, registrado),
                DecisaoRegistrada.de(decisao, agora),
            )
            if resultado.criado:
                break
            if resultado.motivo == "jornada_inexistente":
                raise ErroNaoEncontrado("jornadas", jornada_id)
            if resultado.motivo == "jornada_ja_escalada":
                # Outra requisição escalou entre a leitura e a transação (Req 9.9).
                return self._ja_escalada(self._obter(jornada_id), gatilho)
            # numero_em_uso: sorteia outro número e tenta de novo.
        else:
            raise ErroRepositorio("não foi possível gerar um número de Chamado livre")

        self._log.info(
            "chamado_criado",
            jornada_id=jornada_id,
            numero=numero,
            prioridade=decisao.prioridade,
            criterio=decisao.criterio,
            gatilho=gatilho,
            gatilho_registrado=registrado,
        )
        chamado = self._ordem_servico_se_p2(chamado)
        self._disparar_enriquecimento(numero)
        return ResultadoEscalada(
            chamado=self._obter_chamado(numero),
            jornada=self._obter(jornada_id),
            criado=True,
            prioridade_elevada=False,
            gatilho_registrado=registrado,
        )

    # ------------------------------------------------------------------- Jornada já escalada

    def _ja_escalada(self, jornada: Jornada, gatilho: Gatilho) -> ResultadoEscalada:
        """Mantém o Chamado, registra o gatilho adicional e reavalia a prioridade (Req 9.9)."""
        assert jornada.escalada is not None
        numero = jornada.escalada.chamado_numero
        registrado = self._registrar_gatilho_adicional(jornada, gatilho)
        jornada = self._obter(jornada.jornada_id)
        chamado = self._obter_chamado(numero)

        fatos = self._consolidar_fatos(jornada, gatilho)
        atual = DecisaoEscalada(
            chamado.prioridade, chamado.classificacao, chamado.canal, chamado.decisao_criterio
        )
        nova = reavaliar_prioridade(atual, fatos)
        elevada = False
        if nova != atual:
            pacote = dataclasses.replace(
                chamado.pacote,
                prioridade=nova.prioridade,
                classificacao=nova.classificacao,
                canal_recomendado=nova.canal,
            )
            reav = self._repos.chamados.reavaliar(
                numero, DecisaoRegistrada.de(nova, self._relogio()), pacote
            )
            elevada = reav.aplicado
            chamado = reav.registro
            if elevada:
                self._log.info(
                    "chamado_prioridade_elevada",
                    jornada_id=jornada.jornada_id,
                    numero=numero,
                    de=atual.prioridade,
                    para=nova.prioridade,
                )
        if chamado.prioridade == "P2" and chamado.os_status != "ok":
            chamado = self._ordem_servico_se_p2(chamado)
        return ResultadoEscalada(
            chamado=self._obter_chamado(numero),
            jornada=self._obter(jornada.jornada_id),
            criado=False,
            prioridade_elevada=elevada,
            gatilho_registrado=registrado,
        )

    # ---------------------------------------------------------------------- passos internos

    def _obter(self, jornada_id: str) -> Jornada:
        jornada = self._repos.jornadas.obter(jornada_id)
        if jornada is None:
            raise ErroNaoEncontrado("jornadas", jornada_id)
        return jornada

    def _obter_chamado(self, numero: str) -> Chamado:
        chamado = self._repos.chamados.obter(numero)
        if chamado is None:
            raise ErroRepositorio(f"Chamado {numero} referenciado pela Jornada não existe")
        return chamado

    def _garantir_marcacao(self, jornada: Jornada, origem: OrigemRisco) -> Jornada:
        """Grava a marcação que o gatilho de risco implica. Falha não impede a escalada."""
        try:
            return self._repos.jornadas.marcar_risco(
                jornada.jornada_id, origem, self._relogio()
            ).registro
        except ErroNaoEncontrado:
            raise
        except ErroRepositorio as exc:
            self._log.erro("risco_marcacao_falhou", jornada_id=jornada.jornada_id, erro=exc)
            return jornada

    @staticmethod
    def _consolidar_fatos(jornada: Jornada, gatilho: Gatilho) -> FatosJornada:
        """Fatos da Jornada. O gatilho de risco vale como risco mesmo se a marcação falhou."""
        base = jornada.fatos()
        if gatilho == "risco_seguranca" and not base.risco_seguranca:
            base = dataclasses.replace(base, risco_seguranca=True)
        return dataclasses.replace(base, gatilhos=base.gatilhos | {gatilho})

    def _registrar_gatilho_evento(
        self, jornada: Jornada, gatilho: Gatilho, agora: datetime
    ) -> bool:
        """Registra o gatilho como evento. Devolve False se falhar (Req 9.10)."""
        try:
            self._repos.eventos.registrar(
                Evento(
                    jornada_id=jornada.jornada_id,
                    evento_id=novo_ulid(agora),
                    tipo=TIPO_EVENTO_GATILHO,
                    em=agora,
                    dados={"gatilho": gatilho},
                )
            )
            return True
        except Exception as exc:  # noqa: BLE001 - escalar mesmo assim (Req 9.10)
            self._log.erro(
                "gatilho_nao_registrado", jornada_id=jornada.jornada_id, gatilho=gatilho, erro=exc
            )
            return False

    def _registrar_gatilho_adicional(self, jornada: Jornada, gatilho: Gatilho) -> bool:
        """Acrescenta o gatilho à Jornada já escalada (uma vez por tipo). False se falhar."""
        assert jornada.escalada is not None
        if any(g.tipo == gatilho for g in jornada.escalada.gatilhos):
            return True
        try:
            r = self._repos.jornadas.registrar_gatilho_adicional(
                jornada.jornada_id, GatilhoRegistrado(gatilho, self._relogio(), True)
            )
            return r.aplicado
        except Exception as exc:  # noqa: BLE001 - o Chamado existente segue como está
            self._log.erro(
                "gatilho_adicional_nao_registrado",
                jornada_id=jornada.jornada_id,
                gatilho=gatilho,
                erro=exc,
            )
            return False

    def _ja_tentado(self, jornada_id: str) -> tuple[ItemJaTentado, ...]:
        try:
            return ja_tentado_de_eventos(self._repos.eventos.listar(jornada_id))
        except Exception as exc:  # noqa: BLE001 - lista vazia é válida; não bloqueia o Chamado
            self._log.aviso("ja_tentado_indisponivel", jornada_id=jornada_id, erro=exc)
            return ()

    def _montar_chamado(
        self,
        numero: str,
        jornada: Jornada,
        decisao: DecisaoEscalada,
        ja_tentado: tuple[ItemJaTentado, ...],
        agora: datetime,
        *,
        gatilho_nao_registrado: bool,
    ) -> Chamado:
        nome = (self._nome_modelo(jornada.modelo_id) or "").strip()[:MAX_MODELO]
        det = CamposDeterministicos(
            numero_chamado=numero,
            modelo=nome or NAO_INFORMADO,
            origem=jornada.origem,
            categoria=categoria_do_problema(jornada.problema_id),
            classificacao=decisao.classificacao,
            prioridade=decisao.prioridade,
            canal_recomendado=decisao.canal,
            numero_serie=jornada.numero_serie,
            ja_tentado=ja_tentado,
        )
        return Chamado(
            numero=numero,
            jornada_id=jornada.jornada_id,
            criado_em=agora,
            prioridade=decisao.prioridade,
            classificacao=decisao.classificacao,
            canal=decisao.canal,
            decisao_criterio=decisao.criterio,
            pacote=pacote_fallback(det),
            status="aberto",
            pacote_ia_status="pendente",
            gatilho_nao_registrado=gatilho_nao_registrado,
        )

    def _ordem_servico_se_p2(self, chamado: Chamado) -> Chamado:
        """P2: cria a Ordem_Servico em rascunho (idempotente). Falha mantém o Chamado (Req 11.8)."""
        if chamado.prioridade != "P2":
            return chamado
        pacote = chamado.pacote
        ordem = OrdemServico(
            numero=chamado.numero,
            modelo=pacote.modelo,
            numero_serie=pacote.numero_serie,
            categoria=pacote.categoria,
            ja_tentado=pacote.ja_tentado,
        )
        try:
            self._repos.ordens_servico.criar_rascunho(ordem)  # já existente: sem duplicar
            status = "ok"
        except Exception as exc:  # noqa: BLE001
            self._log.erro("ordem_servico_falhou", numero=chamado.numero, erro=exc)
            status = "falha"
        try:
            return self._repos.chamados.definir_os_status(chamado.numero, status)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 - o Chamado e a prioridade ficam como estão
            self._log.erro("os_status_nao_gravado", numero=chamado.numero, erro=exc)
            return chamado

    def _disparar_enriquecimento(self, numero: str) -> None:
        try:
            self._disparador.disparar(numero)
        except Exception as exc:  # noqa: BLE001 - o Pacote provisório já é válido (Req 10.4)
            self._log.erro("enriquecimento_nao_disparado", numero=numero, erro=exc)
