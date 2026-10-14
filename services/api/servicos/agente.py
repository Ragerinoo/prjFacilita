"""Porta do Assistente_IA (AgentCore) usada pela API (tarefa 12.2; Req 10.3, 10.4, 20.2, 20.4).

A API nunca fala com o modelo: ela fala com o agente (design 3.5), em três modos e com um
contrato JSON único de entrada (`PedidoAgente.para_payload`). Aqui ficam:

  * `AgenteClient` (Protocol): um método por modo, com tipos de entrada e de saída próprios;
  * `AgenteClientFake`: saídas, erros e atrasos programáveis, sem rede e sem dormir;
  * `AgenteClientAgentCore`: `bedrock-agentcore.invoke_agent_runtime` (cliente boto3 injetado).

Falhas tipadas
--------------
Qualquer problema (erro do serviço, rede, tempo esgotado, JSON ruim, saída fora do formato do
modo) vira `ErroAgente` (ou `AgenteTempoEsgotado`, `AgenteSaidaInvalida`). Quem chama trata
três casos e nunca recebe `ClientError`, `ReadTimeoutError` ou `JSONDecodeError`. As mensagens
das exceções não carregam texto do Consumidor nem texto do modelo (podem ir para logs).

Prazos (iguais a `services/agente/premissas.py`, que não vai no pacote da Lambda; o teste
`test_servico_agente.py` confere cada valor):

  responder 20 s | resumo_repasse 10 s | sugestao_atendente 10 s | conexão 3 s | sem retentativa

O prazo é duro: além do `read_timeout` do cliente boto3 (que vale por leitura de socket, não
para a resposta inteira), a chamada roda numa thread e é abandonada quando o prazo vence.

Sem PII: `PedidoAgente.mascarado()` aplica `mascarar_pii` a todo texto livre. O cliente
AgentCore o chama antes de serializar (segunda barreira, idempotente). Se o mascaramento falhar,
nada é enviado e a chamada falha com `ErroAgente`.

Contrato de saída por modo (o design só detalha `responder`; os outros dois seguem o mesmo
estilo e são a referência para a tarefa 17.3):

  responder          -> ver `SaidaResponder`
  resumo_repasse     -> {"resumo": str, "sentimento": str, "proxima_acao": str}
  sugestao_atendente -> {"sugestao": str, "fontes": [{"manual", "secao", "score"}]}

O cliente só confere FORMATO (chaves e tipos). Os limites de conteúdo (resumo de 1 a 300,
sentimento do Pacote, próxima ação de 1 a 200) são do domínio: `dominio.saida_assistente_valida`.
"""

from __future__ import annotations

import json
import math
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final, Literal, Protocol

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectTimeoutError,
    ReadTimeoutError,
)

from dominio import ErroMascaramento, mascarar_pii

# --------------------------------------------------------------------------- constantes

Modo = Literal["responder", "resumo_repasse", "sugestao_atendente"]
MODO_RESPONDER: Final[Modo] = "responder"
MODO_RESUMO_REPASSE: Final[Modo] = "resumo_repasse"
MODO_SUGESTAO_ATENDENTE: Final[Modo] = "sugestao_atendente"
MODOS: Final[tuple[Modo, ...]] = (MODO_RESPONDER, MODO_RESUMO_REPASSE, MODO_SUGESTAO_ATENDENTE)

# Valores de services/agente/premissas.py (Q13 e Q18).
TIMEOUT_POR_MODO_S: Final[Mapping[Modo, float]] = {
    MODO_RESPONDER: 20.0,  # AGENTE_RESPONDER_TIMEOUT_S
    MODO_RESUMO_REPASSE: 10.0,  # ENRIQUECIMENTO_TIMEOUT_S (Req 10.4)
    MODO_SUGESTAO_ATENDENTE: 10.0,  # SUGESTAO_ATENDENTE_TIMEOUT_S (Req 15.7)
}
CONNECT_TIMEOUT_S: Final = 3.0  # AGENTE_CONNECT_TIMEOUT_S
SERVICO_BOTO3: Final = "bedrock-agentcore"  # SERVICO_BOTO3_RUNTIME
PREFIXO_SESSAO: Final = "tres-jornada-"  # RUNTIME_SESSION_PREFIXO
SESSAO_MIN: Final = 33  # RUNTIME_SESSION_ID_MIN
SESSAO_MAX: Final = 256  # RUNTIME_SESSION_ID_MAX
LIMIAR_RELEVANCIA_PADRAO: Final = 0.5  # LIMIAR_RELEVANCIA_PADRAO

RESULTADOS_RESPONDER: Final = frozenset(
    {"solucao", "sem_embasamento", "problema_catalogado", "risco"}
)
SENTIMENTOS_RESPONDER: Final = frozenset({"baixa", "média", "alta"})

CausaFalha = Literal["erro", "tempo_esgotado", "saida_invalida"]


# ------------------------------------------------------------------------------- falhas


class ErroAgente(Exception):
    """Falha ao usar o Assistente_IA. `causa` diz o que houve; `modo` onde.

    A mensagem é só a causa e o modo: nunca texto do Consumidor ou do modelo.
    """

    causa: CausaFalha = "erro"

    def __init__(self, modo: Modo, detalhe: str = "") -> None:
        self.modo: Modo = modo
        self.detalhe = detalhe
        super().__init__(f"agente[{modo}] {self.causa}" + (f": {detalhe}" if detalhe else ""))


class AgenteTempoEsgotado(ErroAgente):
    """O agente não respondeu dentro do prazo do modo (Req 10.4, 20.4)."""

    causa: CausaFalha = "tempo_esgotado"


class AgenteSaidaInvalida(ErroAgente):
    """A resposta chegou, mas não é JSON ou não tem o formato do modo."""

    causa: CausaFalha = "saida_invalida"


# --------------------------------------------------------------------------- entrada


@dataclass(frozen=True, slots=True)
class PassoRegistrado:
    camada: Literal["guia", "ia"]
    passo: str
    resultado: Literal["sim", "não", "sem resposta"]


@dataclass(frozen=True, slots=True)
class TurnoHistorico:
    papel: Literal["consumidor", "assistente"]
    texto: str


@dataclass(frozen=True, slots=True)
class SolucaoAnterior:
    id: str
    resumo: str


@dataclass(frozen=True, slots=True)
class ProblemaCatalogado:
    id: int
    titulo: str


def _mascarar(texto: str) -> str:
    return mascarar_pii(texto)  # levanta ErroMascaramento; nunca devolve o original


def _mascarar_estrutura(valor: Any) -> Any:
    """Mascara toda string de uma estrutura JSON (usado no `pacote` da sugestão)."""
    if isinstance(valor, str):
        return _mascarar(valor)
    if isinstance(valor, Mapping):
        return {k: _mascarar_estrutura(v) for k, v in valor.items()}
    if isinstance(valor, Sequence) and not isinstance(valor, bytes | bytearray):
        return [_mascarar_estrutura(v) for v in valor]
    return valor


@dataclass(frozen=True, slots=True)
class PedidoAgente:
    """Entrada comum aos três modos (contrato do design 3.5).

    `mensagem`, `historico`, `passos_registrados` etc. DEVEM chegar mascarados; o cliente
    AgentCore ainda reaplica `mascarado()` como segunda barreira. `modelo_id` e
    `numero_serie` são identificadores de produto, não Dados_Pessoais, e seguem como estão.
    `pacote` só é usado em `sugestao_atendente` (Pacote_Repasse como dict JSON).
    """

    jornada_id: str
    modelo_id: str | None = None
    numero_serie: str | None = None
    passos_registrados: tuple[PassoRegistrado, ...] = ()
    historico: tuple[TurnoHistorico, ...] = ()
    mensagem: str = ""
    solucoes_anteriores: tuple[SolucaoAnterior, ...] = ()
    limiar_relevancia: float = LIMIAR_RELEVANCIA_PADRAO
    problemas_catalogados: tuple[ProblemaCatalogado, ...] = ()
    pacote: Mapping[str, Any] | None = None

    def mascarado(self) -> PedidoAgente:
        """Cópia com todo texto livre mascarado. Levanta `ErroMascaramento` se falhar."""
        return replace(
            self,
            passos_registrados=tuple(
                replace(p, passo=_mascarar(p.passo)) for p in self.passos_registrados
            ),
            historico=tuple(replace(t, texto=_mascarar(t.texto)) for t in self.historico),
            mensagem=_mascarar(self.mensagem),
            solucoes_anteriores=tuple(
                replace(s, resumo=_mascarar(s.resumo)) for s in self.solucoes_anteriores
            ),
            problemas_catalogados=tuple(
                replace(p, titulo=_mascarar(p.titulo)) for p in self.problemas_catalogados
            ),
            pacote=None if self.pacote is None else _mascarar_estrutura(self.pacote),
        )

    def para_payload(self, modo: Modo) -> dict[str, Any]:
        """JSON do contrato de invocação (design 3.5). `pacote` só aparece quando informado."""
        payload: dict[str, Any] = {
            "modo": modo,
            "jornada_id": self.jornada_id,
            "modelo_id": self.modelo_id,
            "numero_serie": self.numero_serie,
            "passos_registrados": [
                {"camada": p.camada, "passo": p.passo, "resultado": p.resultado}
                for p in self.passos_registrados
            ],
            "historico": [{"papel": t.papel, "texto": t.texto} for t in self.historico],
            "mensagem": self.mensagem,
            "solucoes_anteriores": [
                {"id": s.id, "resumo": s.resumo} for s in self.solucoes_anteriores
            ],
            "limiar_relevancia": self.limiar_relevancia,
            "problemas_catalogados": [
                {"id": p.id, "titulo": p.titulo} for p in self.problemas_catalogados
            ],
        }
        if self.pacote is not None:
            payload["pacote"] = dict(self.pacote)
        return payload


# ---------------------------------------------------------------------------- saídas


@dataclass(frozen=True, slots=True)
class FonteResposta:
    manual: str
    secao: str
    score: float | None = None


@dataclass(frozen=True, slots=True)
class UsoModelo:
    tokens_entrada: int
    tokens_saida: int
    modelo: str


@dataclass(frozen=True, slots=True)
class SaidaResponder:
    resultado: Literal["solucao", "sem_embasamento", "problema_catalogado", "risco"]
    texto: str
    fontes: tuple[FonteResposta, ...]
    problema_id: int | None
    risco_seguranca: bool
    sentimento: Literal["baixa", "média", "alta"] | None
    uso: UsoModelo
    score_maximo: float | None = None


@dataclass(frozen=True, slots=True)
class SaidaResumoRepasse:
    """Resumo, sentimento e próxima ação propostos pelo agente (ainda NÃO validados)."""

    resumo: str
    sentimento: str
    proxima_acao: str


@dataclass(frozen=True, slots=True)
class SaidaSugestaoAtendente:
    sugestao: str
    fontes: tuple[FonteResposta, ...] = field(default_factory=tuple)


Saida = SaidaResponder | SaidaResumoRepasse | SaidaSugestaoAtendente


# ------------------------------------------------------------------------------- porta


class AgenteClient(Protocol):
    """Porta do Assistente_IA. Cada método devolve a saída tipada ou levanta `ErroAgente`.

    `timeout_s` reduz o prazo do modo (nunca o aumenta); `None` usa `TIMEOUT_POR_MODO_S`.
    """

    def responder(
        self, pedido: PedidoAgente, *, timeout_s: float | None = None
    ) -> SaidaResponder: ...

    def resumo_repasse(
        self, pedido: PedidoAgente, *, timeout_s: float | None = None
    ) -> SaidaResumoRepasse: ...

    def sugestao_atendente(
        self, pedido: PedidoAgente, *, timeout_s: float | None = None
    ) -> SaidaSugestaoAtendente: ...


def prazo_do_modo(modo: Modo, timeout_s: float | None = None) -> float:
    """Prazo efetivo: o do modo, ou o menor entre ele e o pedido (nunca maior)."""
    teto = TIMEOUT_POR_MODO_S[modo]
    if timeout_s is None:
        return teto
    return max(0.0, min(teto, float(timeout_s)))


# ----------------------------------------------------------------- validação de formato


def _falha(modo: Modo, detalhe: str) -> AgenteSaidaInvalida:
    return AgenteSaidaInvalida(modo, detalhe)


def _texto(modo: Modo, obj: Mapping[str, Any], chave: str) -> str:
    valor = obj.get(chave)
    if not isinstance(valor, str):
        raise _falha(modo, f"campo '{chave}' ausente ou não é texto")
    return valor


def _numero(modo: Modo, valor: Any, nome: str) -> float:
    if isinstance(valor, bool) or not isinstance(valor, int | float) or not math.isfinite(valor):
        raise _falha(modo, f"campo '{nome}' não é número")
    return float(valor)


def _inteiro_nao_negativo(modo: Modo, valor: Any, nome: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
        raise _falha(modo, f"campo '{nome}' não é inteiro não negativo")
    return valor


def _fontes(modo: Modo, valor: Any) -> tuple[FonteResposta, ...]:
    if not isinstance(valor, list):
        raise _falha(modo, "campo 'fontes' não é lista")
    saida: list[FonteResposta] = []
    for item in valor:
        if not isinstance(item, Mapping):
            raise _falha(modo, "item de 'fontes' não é objeto")
        score = item.get("score")
        saida.append(
            FonteResposta(
                manual=_texto(modo, item, "manual"),
                secao=_texto(modo, item, "secao"),
                score=None if score is None else _numero(modo, score, "score"),
            )
        )
    return tuple(saida)


def interpretar_saida(modo: Modo, obj: Any) -> Saida:
    """Converte o JSON do agente na saída tipada do modo. Formato errado: `AgenteSaidaInvalida`."""
    if not isinstance(obj, Mapping):
        raise _falha(modo, "a resposta não é um objeto JSON")
    if modo == MODO_RESUMO_REPASSE:
        return SaidaResumoRepasse(
            resumo=_texto(modo, obj, "resumo"),
            sentimento=_texto(modo, obj, "sentimento"),
            proxima_acao=_texto(modo, obj, "proxima_acao"),
        )
    if modo == MODO_SUGESTAO_ATENDENTE:
        return SaidaSugestaoAtendente(
            sugestao=_texto(modo, obj, "sugestao"),
            fontes=_fontes(modo, obj["fontes"]) if "fontes" in obj else (),
        )
    resultado = obj.get("resultado")
    if resultado not in RESULTADOS_RESPONDER:
        raise _falha(modo, "campo 'resultado' fora do domínio")
    sentimento = obj.get("sentimento")
    if sentimento is not None and sentimento not in SENTIMENTOS_RESPONDER:
        raise _falha(modo, "campo 'sentimento' fora do domínio")
    problema_id = obj.get("problema_id")
    if problema_id is not None and (isinstance(problema_id, bool) or not isinstance(problema_id, int)):
        raise _falha(modo, "campo 'problema_id' não é inteiro")
    risco = obj.get("risco_seguranca")
    if not isinstance(risco, bool):
        raise _falha(modo, "campo 'risco_seguranca' não é booleano")
    uso = obj.get("uso")
    if not isinstance(uso, Mapping):
        raise _falha(modo, "campo 'uso' ausente")
    score_maximo = obj.get("score_maximo")
    return SaidaResponder(
        resultado=resultado,
        texto=_texto(modo, obj, "texto"),
        fontes=_fontes(modo, obj.get("fontes", [])),
        problema_id=problema_id,
        risco_seguranca=risco,
        sentimento=sentimento,
        uso=UsoModelo(
            tokens_entrada=_inteiro_nao_negativo(modo, uso.get("tokens_entrada"), "tokens_entrada"),
            tokens_saida=_inteiro_nao_negativo(modo, uso.get("tokens_saida"), "tokens_saida"),
            modelo=_texto(modo, uso, "modelo"),
        ),
        score_maximo=None if score_maximo is None else _numero(modo, score_maximo, "score_maximo"),
    )


# ------------------------------------------------------------------------------ o fake


def _saida_padrao(modo: Modo) -> Saida:
    if modo == MODO_RESUMO_REPASSE:
        return SaidaResumoRepasse(
            resumo="Consumidor relata o problema e já tentou os passos do guia sem sucesso.",
            sentimento="neutro",
            proxima_acao="Ligar para confirmar o sintoma e orientar a próxima verificação.",
        )
    if modo == MODO_SUGESTAO_ATENDENTE:
        return SaidaSugestaoAtendente(sugestao="Olá! Vamos verificar isso juntos.")
    return SaidaResponder(
        resultado="sem_embasamento",
        texto="",
        fontes=(),
        problema_id=None,
        risco_seguranca=False,
        sentimento=None,
        uso=UsoModelo(0, 0, "fake"),
        score_maximo=0.0,
    )


@dataclass(frozen=True, slots=True)
class ChamadaAgente:
    """Registro de uma chamada ao fake: o que foi pedido e com que prazo."""

    modo: Modo
    pedido: PedidoAgente
    timeout_s: float


class AgenteClientFake:
    """Fake de testes e do modo local. Nada de rede, nada de `sleep`.

    `programar(modo, resultado)`: `resultado` é uma saída (devolvida sempre), uma exceção
    (levantada sempre), uma lista (consumida uma a uma; a última se repete) ou um `callable`
    `(pedido) -> saída | exceção`. `atrasar(modo, segundos)` simula demora: se passar do prazo
    efetivo, a chamada levanta `AgenteTempoEsgotado` sem executar a saída. Sem programação, cada
    modo devolve uma saída válida padrão.
    """

    def __init__(self) -> None:
        self.chamadas: list[ChamadaAgente] = []
        self._programado: dict[Modo, Any] = {}
        self._atrasos: dict[Modo, float] = {}
        self._trava = threading.Lock()

    # -- programação ------------------------------------------------------------------
    def programar(self, modo: Modo, resultado: Any) -> AgenteClientFake:
        with self._trava:
            self._programado[modo] = list(resultado) if isinstance(resultado, list) else resultado
        return self

    def atrasar(self, modo: Modo, segundos: float) -> AgenteClientFake:
        self._atrasos[modo] = segundos
        return self

    def chamadas_do_modo(self, modo: Modo) -> list[ChamadaAgente]:
        return [c for c in self.chamadas if c.modo == modo]

    # -- porta --------------------------------------------------------------------------
    def responder(self, pedido: PedidoAgente, *, timeout_s: float | None = None) -> SaidaResponder:
        return self._executar(MODO_RESPONDER, pedido, timeout_s)  # type: ignore[return-value]

    def resumo_repasse(
        self, pedido: PedidoAgente, *, timeout_s: float | None = None
    ) -> SaidaResumoRepasse:
        return self._executar(MODO_RESUMO_REPASSE, pedido, timeout_s)  # type: ignore[return-value]

    def sugestao_atendente(
        self, pedido: PedidoAgente, *, timeout_s: float | None = None
    ) -> SaidaSugestaoAtendente:
        return self._executar(MODO_SUGESTAO_ATENDENTE, pedido, timeout_s)  # type: ignore[return-value]

    # -- interno ------------------------------------------------------------------------
    def _executar(self, modo: Modo, pedido: PedidoAgente, timeout_s: float | None) -> Saida:
        prazo = prazo_do_modo(modo, timeout_s)
        with self._trava:
            self.chamadas.append(ChamadaAgente(modo, pedido, prazo))
            programado = self._programado.get(modo)
            if isinstance(programado, list):
                resultado = programado.pop(0) if len(programado) > 1 else programado[0]
            else:
                resultado = programado
        if self._atrasos.get(modo, 0.0) > prazo:
            raise AgenteTempoEsgotado(modo, f"prazo de {prazo:g} s excedido")
        if callable(resultado) and not isinstance(resultado, BaseException):
            resultado = resultado(pedido)
        if resultado is None:
            return _saida_padrao(modo)
        if isinstance(resultado, BaseException):
            raise resultado
        return resultado  # type: ignore[no-any-return]


# ------------------------------------------------------------------- AgentCore (boto3)


def sessao_do_runtime(jornada_id: str) -> str:
    """`runtimeSessionId` da Jornada (33 a 256 caracteres; igual a `premissas.runtime_session_id`)."""
    if not jornada_id or not jornada_id.isalnum():
        raise ValueError("jornada_id deve ser alfanumérico e não vazio")
    sessao = f"{PREFIXO_SESSAO}{jornada_id}"
    if not SESSAO_MIN <= len(sessao) <= SESSAO_MAX:
        raise ValueError("runtimeSessionId fora de 33 a 256 caracteres")
    return sessao


def criar_cliente_agentcore(timeout_s: float, regiao: str | None = None) -> Any:
    """Cliente boto3 `bedrock-agentcore`: conexão 3 s, leitura `timeout_s`, SEM retentativa.

    `total_max_attempts=1` é a forma correta de "uma tentativa só" no botocore
    (`max_attempts=1` significaria 1 retentativa; ver `premissas.AGENTE_MAX_TENTATIVAS`).
    """
    import boto3
    from botocore.config import Config

    return boto3.client(
        SERVICO_BOTO3,
        region_name=regiao,
        config=Config(
            connect_timeout=CONNECT_TIMEOUT_S,
            read_timeout=timeout_s,
            retries={"total_max_attempts": 1, "mode": "standard"},
        ),
    )


def criar_clientes_agentcore(regiao: str | None = None) -> dict[Modo, Any]:
    """Um cliente por prazo distinto (o `read_timeout` é fixo por cliente)."""
    por_prazo: dict[float, Any] = {}
    clientes: dict[Modo, Any] = {}
    for modo, prazo in TIMEOUT_POR_MODO_S.items():
        if prazo not in por_prazo:
            por_prazo[prazo] = criar_cliente_agentcore(prazo, regiao)
        clientes[modo] = por_prazo[prazo]
    return clientes


class AgenteClientAgentCore:
    """Invoca o runtime do agente com `invoke_agent_runtime` (IAM/SigV4, sessão por Jornada).

    `cliente`: um cliente boto3 `bedrock-agentcore` (usado em todos os modos) ou um mapa
    `modo -> cliente` (`criar_clientes_agentcore`), para prazos de leitura diferentes.
    """

    def __init__(self, runtime_arn: str, cliente: Any | Mapping[Modo, Any]) -> None:
        if not runtime_arn:
            raise ValueError("runtime_arn é obrigatório")
        self._arn = runtime_arn
        self._cliente = cliente

    def responder(self, pedido: PedidoAgente, *, timeout_s: float | None = None) -> SaidaResponder:
        return self._invocar(MODO_RESPONDER, pedido, timeout_s)  # type: ignore[return-value]

    def resumo_repasse(
        self, pedido: PedidoAgente, *, timeout_s: float | None = None
    ) -> SaidaResumoRepasse:
        return self._invocar(MODO_RESUMO_REPASSE, pedido, timeout_s)  # type: ignore[return-value]

    def sugestao_atendente(
        self, pedido: PedidoAgente, *, timeout_s: float | None = None
    ) -> SaidaSugestaoAtendente:
        return self._invocar(MODO_SUGESTAO_ATENDENTE, pedido, timeout_s)  # type: ignore[return-value]

    # -- interno ------------------------------------------------------------------------
    def _cliente_do_modo(self, modo: Modo) -> Any:
        if isinstance(self._cliente, Mapping):
            return self._cliente[modo]
        return self._cliente

    def _invocar(self, modo: Modo, pedido: PedidoAgente, timeout_s: float | None) -> Saida:
        prazo = prazo_do_modo(modo, timeout_s)
        if prazo <= 0:
            raise AgenteTempoEsgotado(modo, "sem tempo disponível")
        try:
            sessao = sessao_do_runtime(pedido.jornada_id)
            payload = pedido.mascarado().para_payload(modo)  # segunda barreira de PII
            corpo = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except ErroMascaramento:
            raise ErroAgente(modo, "mascaramento falhou; nada foi enviado") from None
        except (ValueError, TypeError):
            raise ErroAgente(modo, "pedido inválido") from None

        cliente = self._cliente_do_modo(modo)
        bruto = self._chamar_com_prazo(
            modo,
            prazo,
            lambda: self._ler_resposta(
                cliente.invoke_agent_runtime(
                    agentRuntimeArn=self._arn,
                    runtimeSessionId=sessao,
                    contentType="application/json",
                    accept="application/json",
                    payload=corpo,
                )
            ),
        )
        return interpretar_saida(modo, self._decodificar(modo, bruto))

    @staticmethod
    def _ler_resposta(resposta: Mapping[str, Any]) -> bytes:
        """`response["response"]` é um StreamingBody: lê tudo (sem streaming no MVP)."""
        fluxo = resposta["response"]
        dados = fluxo.read()
        return dados if isinstance(dados, bytes) else str(dados).encode("utf-8")

    @staticmethod
    def _chamar_com_prazo(modo: Modo, prazo_s: float, trabalho: Callable[[], bytes]) -> bytes:
        """Executa `trabalho` numa thread e abandona-a quando o prazo duro vence."""
        resultado: dict[str, Any] = {}

        def alvo() -> None:
            try:
                resultado["valor"] = trabalho()
            except BaseException as exc:  # noqa: BLE001 - repassado à thread chamadora
                resultado["erro"] = exc

        thread = threading.Thread(target=alvo, name=f"agente-{modo}", daemon=True)
        thread.start()
        thread.join(prazo_s)
        if thread.is_alive():
            raise AgenteTempoEsgotado(modo, f"prazo de {prazo_s:g} s excedido")
        erro = resultado.get("erro")
        if erro is None:
            return resultado["valor"]  # type: ignore[no-any-return]
        if isinstance(erro, ConnectTimeoutError | ReadTimeoutError | TimeoutError):
            raise AgenteTempoEsgotado(modo, "tempo de rede esgotado") from None
        if isinstance(erro, ClientError):
            codigo = erro.response.get("Error", {}).get("Code", "desconhecido")
            raise ErroAgente(modo, f"serviço respondeu {codigo}") from None
        if isinstance(erro, BotoCoreError | OSError | KeyError):
            raise ErroAgente(modo, f"falha de chamada ({type(erro).__name__})") from None
        raise ErroAgente(modo, f"falha inesperada ({type(erro).__name__})") from None

    @staticmethod
    def _decodificar(modo: Modo, bruto: bytes) -> Any:
        try:
            valor = json.loads(bruto.decode("utf-8"))
            if isinstance(valor, str):  # alguns entrypoints devolvem o JSON como texto
                valor = json.loads(valor)
        except (ValueError, RecursionError):
            raise AgenteSaidaInvalida(modo, "a resposta não é JSON válido") from None
        return valor
