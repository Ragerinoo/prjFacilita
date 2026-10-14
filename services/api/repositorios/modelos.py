"""Registros persistidos (tipos imutáveis) que as interfaces de repositório trocam.

Espelham o design ("Data Models") e os nomes de atributos de `infra/stacks/dados_stack.py`.
Horários são sempre `datetime` com fuso. Dinheiro é `Decimal`. Os adaptadores DynamoDB
(tarefa 9.2) convertem de e para itens; os fakes em memória guardam estes objetos direto.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Final, Literal

from dominio import (
    FILA_PK,
    DecisaoEscalada,
    EstadoDaJornada,
    FatosJornada,
    Gatilho,
    ItemJaTentado,
    JornadaEncerrada,
    PacoteRepasse,
    montar_fila_sk,
)
from dominio.encerramento import ATIVA_PK, ENCERRADA_PK
from dominio.tipos import Classificacao, Prioridade
from repositorios.ids import eh_ulid

# ----------------------------------------------------------------------------- comuns

# P1 > P2 > P3: quanto menor o número, maior a prioridade.
RANKING_PRIORIDADE: Final[dict[Prioridade, int]] = {"P1": 0, "P2": 1, "P3": 2}


@dataclass(frozen=True, slots=True)
class ResultadoCondicional[T]:
    """Desfecho de uma escrita condicional.

    `aplicado` é falso quando a condição de escrita não foi satisfeita (por exemplo,
    "já existe" ou "já tem responsável"). `registro` é o estado do registro depois da
    operação: o novo, se aplicado; o que já estava gravado, caso contrário.
    """

    aplicado: bool
    registro: T


# ----------------------------------------------------------------------------- Jornada

OrigemJornada = Literal["qr", "busca"]
EstadoJornadaRegistro = Literal["ativa", "escalada", "encerrada"]
OrigemRisco = Literal["lista", "ia", "guia"]


@dataclass(frozen=True, slots=True)
class RiscoMarcado:
    """Marcação de risco de segurança; monotônica, nunca removida (Req 8.4)."""

    origem: OrigemRisco
    em: datetime


@dataclass(frozen=True, slots=True)
class GatilhoRegistrado:
    """Gatilho de escalada. `registrado=False` quando o registro falhou (Req 9.10)."""

    tipo: Gatilho
    em: datetime
    registrado: bool = True


@dataclass(frozen=True, slots=True)
class DecisaoRegistrada:
    """Decisão do Motor_Escalada gravada com o critério e o horário (Req 11.7)."""

    prioridade: Prioridade
    classificacao: Classificacao
    canal: str
    criterio: Literal[1, 2, 3]
    em: datetime

    @classmethod
    def de(cls, decisao: DecisaoEscalada, em: datetime) -> DecisaoRegistrada:
        return cls(decisao.prioridade, decisao.classificacao, decisao.canal, decisao.criterio, em)


@dataclass(frozen=True, slots=True)
class EscaladaJornada:
    """Bloco `escalada` da Jornada: o único Chamado dela (Req 9.9)."""

    chamado_numero: str
    em: datetime
    gatilhos: tuple[GatilhoRegistrado, ...]
    decisao: DecisaoRegistrada


@dataclass(frozen=True, slots=True)
class Jornada:
    """Item da tabela `jornadas`."""

    jornada_id: str
    criada_em: datetime
    ultima_interacao: datetime
    origem: OrigemJornada
    origem_inicial: OrigemJornada
    estado: EstadoJornadaRegistro = "ativa"
    modelo_id: str | None = None
    numero_serie: str | None = None
    problema_id: int | None = None
    problemas_selecionados: tuple[int, ...] = ()
    seletor_area: str | None = None
    seletor_estado: str | None = None
    risco: RiscoMarcado | None = None
    guia_respondeu_nao: bool = False
    msgs_modelo: int = 0
    ia_nao: int = 0
    frustracao_alta_seq: int = 0
    custo_ia_brl: Decimal = Decimal("0")
    escalada: EscaladaJornada | None = None
    encerramento: JornadaEncerrada | None = None

    @property
    def chamado_numero(self) -> str | None:
        return self.escalada.chamado_numero if self.escalada else None

    def estado_dominio(self) -> EstadoDaJornada:
        """Visão usada pelas regras puras de encerramento (`dominio.encerramento`)."""
        return EstadoDaJornada(
            jornada_id=self.jornada_id,
            criada_em=self.criada_em,
            ultima_interacao=self.ultima_interacao,
            estado=self.estado,
            chamado_numero=self.chamado_numero,
            encerramento=self.encerramento,
        )

    def com_estado_dominio(self, est: EstadoDaJornada) -> Jornada:
        return replace(
            self,
            estado=est.estado,
            ultima_interacao=est.ultima_interacao,
            encerramento=est.encerramento,
        )

    def fatos(self) -> FatosJornada:
        """Fatos consolidados para o Motor_Escalada."""
        gatilhos = (
            frozenset(g.tipo for g in self.escalada.gatilhos) if self.escalada else frozenset()
        )
        return FatosJornada(
            risco_seguranca=self.risco is not None,
            guia_respondeu_nao=self.guia_respondeu_nao,
            gatilhos=gatilhos,
            problema_id=None if self.problema_id is None else str(self.problema_id),
        )

    # Atributos de índice esparso (existem só enquanto valem as condições).
    @property
    def ativa_pk(self) -> str | None:
        """`gsi_ativas`: Jornada ativa e sem Chamado."""
        return ATIVA_PK if self.estado == "ativa" and self.escalada is None else None

    @property
    def encerrada_pk(self) -> str | None:
        """`gsi_encerradas`: Jornada encerrada."""
        return ENCERRADA_PK if self.estado == "encerrada" else None

    @property
    def encerrada_em(self) -> datetime | None:
        """Espelho de `encerramento.em`, chave de ordenação do `gsi_encerradas`."""
        return self.encerramento.encerrada_em if self.encerramento else None


# ----------------------------------------------------------------------------- Evento


@dataclass(frozen=True, slots=True)
class Evento:
    """Item de `eventos`. A chave de ordenação `ts_ulid` é o próprio `evento_id`.

    O `evento_id` é um ULID gerado pelo cliente (ou pelo servidor); como ele embute o
    horário, a ordem das chaves é cronológica e o `Put` condicional na chave dá a
    idempotência do reenvio (Req 3.12). Textos de mensagens chegam sempre mascarados.
    """

    jornada_id: str
    evento_id: str
    tipo: str
    em: datetime
    dados: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not eh_ulid(self.evento_id):
            raise ValueError(f"evento_id deve ser um ULID: {self.evento_id!r}")

    @property
    def ts_ulid(self) -> str:
        return self.evento_id


# ----------------------------------------------------------------------------- Chamado

StatusChamado = Literal["aberto", "em_atendimento", "encerrado"]
StatusPacoteIA = Literal["pendente", "ok", "fallback"]
StatusOS = Literal["ok", "falha", "nao_aplicavel"]
DesfechoChamado = Literal["falso_defeito", "defeito_real"]
TipoSolucao = Literal["instrução do manual", "outra"]


@dataclass(frozen=True, slots=True)
class Responsavel:
    usuario: str
    nome: str
    inicio: datetime


@dataclass(frozen=True, slots=True)
class AnexoChamado:
    chave: str
    mime: Literal["image/jpeg", "image/png"]
    bytes: int


@dataclass(frozen=True, slots=True)
class EncerramentoChamado:
    desfecho: DesfechoChamado
    solucao_tipo: TipoSolucao
    solucao: str
    em: datetime
    por: str


@dataclass(frozen=True, slots=True)
class Chamado:
    """Item da tabela `chamados` (PK `numero`)."""

    numero: str
    jornada_id: str
    criado_em: datetime
    prioridade: Prioridade
    classificacao: Classificacao
    canal: str
    decisao_criterio: Literal[1, 2, 3]
    pacote: PacoteRepasse
    status: StatusChamado = "aberto"
    pacote_ia_status: StatusPacoteIA = "pendente"
    gatilho_nao_registrado: bool = False
    responsavel: Responsavel | None = None
    alerta_p1_visto: bool = False
    resposta_nao_lida: bool = False
    os_status: StatusOS = "nao_aplicavel"
    agendamento: datetime | None = None
    anexos: tuple[AnexoChamado, ...] = ()
    encerramento: EncerramentoChamado | None = None

    # Atributos do `gsi_fila` (índice esparso): somem quando o Chamado é encerrado.
    @property
    def fila_pk(self) -> str | None:
        return FILA_PK if self.status != "encerrado" else None

    @property
    def fila_sk(self) -> str | None:
        if self.status == "encerrado":
            return None
        return montar_fila_sk(self.prioridade, self.criado_em, self.numero)


MotivoEscalada = Literal["criado", "jornada_inexistente", "jornada_ja_escalada", "numero_em_uso"]


@dataclass(frozen=True, slots=True)
class ResultadoEscalada:
    """Desfecho da transação "criar Chamado + marcar Jornada escalada" (Req 9.9).

    `numero_existente` traz o Chamado que a Jornada já tinha, quando o motivo é
    `jornada_ja_escalada`. Com `numero_em_uso`, quem chama gera outro número e tenta de novo.
    """

    criado: bool
    motivo: MotivoEscalada
    numero_existente: str | None = None


AutorMensagem = Literal["atendente", "consumidor"]


@dataclass(frozen=True, slots=True)
class MensagemChamado:
    """Item de `mensagens_chamado` (PK `numero`, SK `ts_ulid`)."""

    numero: str
    ts_ulid: str
    autor: AutorMensagem
    texto: str
    em: datetime
    lida: bool = False


# ----------------------------------------------------------------------------- PII


@dataclass(frozen=True, slots=True)
class Consentimento:
    em: datetime
    versao_finalidade: str


@dataclass(frozen=True, slots=True)
class DadosPessoaisRegistro:
    """Item de `dados_pessoais` (PK `numero`). Só aqui existem telefone, CEP, nome e e-mail (PII)."""

    numero: str
    consentimento: Consentimento
    telefone: str | None = None
    cep: str | None = None


@dataclass(frozen=True, slots=True)
class AcessoPII:
    """Item de `acessos_pii`: quem viu os dados pessoais e quando (resolução de segundos)."""

    numero: str
    ts_ulid: str
    atendente_id: str
    em: datetime


# ----------------------------------------------------------------------------- OS

StatusOrdemServico = Literal["rascunho", "aberta"]


def os_id_de(numero: str) -> str:
    """Chave determinística da Ordem_Servico: `OS#<numero>` (Req 11.8)."""
    return f"OS#{numero}"


@dataclass(frozen=True, slots=True)
class OrdemServico:
    numero: str
    modelo: str
    numero_serie: str
    categoria: str
    ja_tentado: tuple[ItemJaTentado, ...] = ()
    status: StatusOrdemServico = "rascunho"

    @property
    def os_id(self) -> str:
        return os_id_de(self.numero)


# ----------------------------------------------------------------------------- Cache


@dataclass(frozen=True, slots=True)
class RegistroCache:
    """Item de `cache_respostas` (PK `chave` = `modelo_id#hash`)."""

    chave: str
    modelo_id: str
    pergunta_normalizada: str
    pergunta: str
    resposta: str
    aprovador_id: str
    aprovado_em: datetime | None
    fontes: tuple[dict[str, Any], ...] = ()
    hits: int = 0


# ----------------------------------------------------------------------------- Avaliação


@dataclass(frozen=True, slots=True)
class Avaliacao:
    """Item de `avaliacoes` (PK `jornada_id`): uma por Jornada (Req 5.5)."""

    jornada_id: str
    nota: int
    camada: Literal["guia", "ia", "humano"]
    em: datetime
    comentario: str = ""

    def __post_init__(self) -> None:
        if not 1 <= self.nota <= 5:
            raise ValueError(f"nota deve estar entre 1 e 5: {self.nota}")
        if len(self.comentario) > 500:
            raise ValueError("comentário excede 500 caracteres")


# ----------------------------------------------------------------------------- Agregados


@dataclass(frozen=True, slots=True)
class AgregadoDia:
    """Item de `agregados_dia` (PK `dia` ISO, SK `metrica`)."""

    dia: str
    metrica: str
    valor: int


# ----------------------------------------------------------------------------- Painel_CS

PerfilCS = Literal["atendente", "gestor"]


@dataclass(frozen=True, slots=True)
class UsuarioCS:
    """Item de `usuarios_cs` (PK `usuario`). Nunca contém senha em texto puro."""

    usuario: str
    hash_senha: str
    perfil: PerfilCS
    falhas: tuple[datetime, ...] = ()
    bloqueado_ate: datetime | None = None
    deve_trocar_senha: bool = True


@dataclass(frozen=True, slots=True)
class SessaoCS:
    """Item de `sessoes_cs` (PK `token_hash`, SHA-256 do token opaco). `ttl` em epoch."""

    token_hash: str
    usuario: str
    perfil: PerfilCS
    ultima_atividade: datetime
    ttl: int
