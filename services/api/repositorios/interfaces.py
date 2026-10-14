"""Interfaces (typing.Protocol) dos repositórios.

Cada método documenta a garantia condicional que TODA implementação deve dar (o fake em
memória e o adaptador DynamoDB da tarefa 9.2 passam nos mesmos testes de contrato, 9.3):

  Garantia                                   Mecanismo no DynamoDB
  -----------------------------------------  ------------------------------------------
  Um Chamado por Jornada (Req 9.9)           Transact: Put Chamado + Update Jornada
  Um responsável por Chamado (Req 14.6)      Update com attribute_not_exists(responsavel)
  Uma avaliação por Jornada (Req 5.5)        Put com attribute_not_exists(jornada_id)
  Uma camada de resolução (Req 17.1)         Update com estado <> encerrada
  Sem duplicar entrada no cache (Req 16.8)   Put com attribute_not_exists(chave)
  Uma Ordem_Servico por Chamado (Req 11.8)   Put com attribute_not_exists(os_id)
  Limite de chamadas ao modelo (Req 7.4)     Update com condição msgs_modelo < limite
  Evento do cliente sem duplicar (Req 3.12)  Put com attribute_not_exists(ts_ulid)

Convenções: condição não satisfeita volta como resultado (`aplicado=False`), nunca como
exceção. Mutação sobre registro inexistente levanta `ErroNaoEncontrado`. Falha de
infraestrutura levanta `ErroRepositorio`. Os horários entram por parâmetro.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

from dominio import (
    Camada,
    EntradaCache,
    Nivel,
    PacoteRepasse,
    ResultadoEncerramento,
    ResultadoInsercao,
)
from repositorios.catalogo import CatalogoRepo
from repositorios.modelos import (
    AcessoPII,
    AgregadoDia,
    AnexoChamado,
    AutorMensagem,
    Avaliacao,
    Chamado,
    Consentimento,
    DadosPessoaisRegistro,
    DecisaoRegistrada,
    EncerramentoChamado,
    Evento,
    GatilhoRegistrado,
    Jornada,
    MensagemChamado,
    OrdemServico,
    OrigemRisco,
    PerfilCS,
    RegistroCache,
    ResultadoCondicional,
    ResultadoEscalada,
    SessaoCS,
    StatusOS,
    StatusPacoteIA,
    UsuarioCS,
)


class JornadasRepo(Protocol):
    """Tabela `jornadas` (índices esparsos `gsi_ativas` e `gsi_encerradas`)."""

    def criar(self, jornada: Jornada) -> ResultadoCondicional[Jornada]:
        """Put com `attribute_not_exists(jornada_id)`. Existente: `aplicado=False`."""
        ...

    def obter(self, jornada_id: str) -> Jornada | None:
        """Leitura fortemente consistente."""
        ...

    def associar_modelo(
        self, jornada_id: str, modelo_id: str, numero_serie: str | None = None
    ) -> Jornada:
        """Associa o modelo escolhido na busca: `origem` vira "busca"; `origem_inicial` fica."""
        ...

    def registrar_seletor(self, jornada_id: str, area: str, estado: str) -> Jornada: ...

    def registrar_interacao(self, jornada_id: str, em: datetime) -> Jornada:
        """`ultima_interacao` nunca retrocede e Jornada encerrada nunca muda (Req 17.2)."""
        ...

    def registrar_problema_selecionado(self, jornada_id: str, problema_id: int) -> bool:
        """Define `problema_id`. Devolve True só na primeira seleção deste problema na
        Jornada (base do agregado `problema_sel#<id>`, Req 17.8)."""
        ...

    def marcar_guia_respondeu_nao(self, jornada_id: str) -> Jornada:
        """`fatos.guia_respondeu_nao = true` (monotônico)."""
        ...

    def marcar_risco(
        self, jornada_id: str, origem: OrigemRisco, em: datetime
    ) -> ResultadoCondicional[Jornada]:
        """Marca risco com `attribute_not_exists(risco)`: monotônico (Req 8.4). Já marcada:
        `aplicado=False`, a marcação original (origem e horário) é preservada."""
        ...

    def incrementar_msgs_modelo(
        self, jornada_id: str, limite: int
    ) -> ResultadoCondicional[Jornada]:
        """`ADD msgs_modelo 1` com condição `msgs_modelo < limite` (Req 7.4, 7.5).
        No limite: `aplicado=False`, contador intacto. A `limite`-ésima chamada é permitida."""
        ...

    def incrementar_ia_nao(self, jornada_id: str) -> Jornada:
        """Incremento atômico de `ia_nao` (Req 9.2)."""
        ...

    def atualizar_frustracao(self, jornada_id: str, nivel: Nivel) -> Jornada:
        """ "alta" soma 1 a `frustracao_alta_seq`; outro nível zera (Req 9.5)."""
        ...

    def somar_custo_ia(self, jornada_id: str, custo_brl: Decimal) -> Jornada:
        """Soma atômica (4 casas) ao `custo_ia_brl`. Custo negativo é erro."""
        ...

    def registrar_gatilho_adicional(
        self, jornada_id: str, gatilho: GatilhoRegistrado
    ) -> ResultadoCondicional[Jornada]:
        """Acrescenta gatilho a uma Jornada JÁ escalada (Req 9.9). Sem escalada:
        `aplicado=False`. A criação da escalada é de `ChamadosRepo.criar_com_escalada`."""
        ...

    def encerrar(
        self,
        jornada_id: str,
        camada: Camada,
        em: datetime,
        custo_brl: Decimal = Decimal("0"),
        problema_id: int | None = None,
        desfecho: str | None = None,
    ) -> ResultadoEncerramento:
        """Update condicional `estado <> encerrada` (Req 17.1): a primeira camada vence;
        depois disso `aplicado=False` e a Jornada fica como estava. Atualiza os atributos
        `encerrada_pk`/`encerrada_em` e remove `ativa_pk`. A camada "abandonada" só sai
        de `marcar_abandono`."""
        ...

    def marcar_abandono(
        self, jornada_id: str, agora: datetime, custo_brl: Decimal = Decimal("0")
    ) -> ResultadoEncerramento:
        """Abandono condicional: só Jornada `ativa`, sem Chamado e com 30 min sem interação
        (Req 17.2). Terminal."""
        ...

    def listar_ativas_sem_interacao_ate(self, limite: datetime) -> list[Jornada]:
        """`gsi_ativas`: ativas e sem Chamado com `ultima_interacao <= limite`, da mais
        antiga para a mais nova (varredura de abandono)."""
        ...

    def listar_encerradas(self, inicio: datetime, fim: datetime) -> list[Jornada]:
        """`gsi_encerradas`: encerradas com `encerramento.em` em `[inicio, fim]` (inclusivo),
        em ordem cronológica (métricas, Req 17)."""
        ...


class EventosRepo(Protocol):
    """Tabela `eventos` (PK `jornada_id`, SK `ts_ulid` = `evento_id`)."""

    def registrar(self, evento: Evento) -> bool:
        """Put condicional por `evento_id`: True se novo, False se já existia (o evento
        original permanece, Req 3.12)."""
        ...

    def listar(self, jornada_id: str) -> list[Evento]:
        """Eventos da Jornada em ordem cronológica (ordem da chave)."""
        ...


class ChamadosRepo(Protocol):
    """Tabela `chamados` (índice esparso `gsi_fila`)."""

    def criar_com_escalada(
        self,
        chamado: Chamado,
        gatilho: GatilhoRegistrado,
        decisao: DecisaoRegistrada,
    ) -> ResultadoEscalada:
        """Transação atômica (TransactWrite): Put do Chamado (`attribute_not_exists(numero)`)
        E Update da Jornada (`escalada` ausente), tudo ou nada (Req 9.9).

        Na Jornada grava `escalada {chamado_numero, em=chamado.criado_em, gatilhos=[gatilho],
        decisao}` e, se estava "ativa", passa a "escalada" (sai do `gsi_ativas`). Jornada
        já "encerrada" mantém o estado e a camada (Req 17.2), mas ganha o Chamado.
        Falhas, sem gravar nada: `jornada_inexistente`, `jornada_ja_escalada` (traz o
        número do Chamado existente) e `numero_em_uso`. O `status` deve ser "aberto"."""
        ...

    def obter(self, numero: str) -> Chamado | None: ...

    def listar_fila(self) -> list[Chamado]:
        """`gsi_fila` (PK constante, ascendente): Chamados não encerrados em ordem de
        prioridade, horário de criação e número (Req 14.1)."""
        ...

    def listar_todos(self) -> list[Chamado]:
        """Todos os Chamados (aberto, em_atendimento e encerrado), do mais antigo ao mais novo
        (`criado_em`, depois `numero`). Repositório vazio devolve [].
        `listar_fila` continua devolvendo só os não encerrados.
        Só o repositório em memória a implementa; o adaptador DynamoDB levanta
        ErroIndisponivelForaDoModoLocal."""
        ...

    def assumir(
        self, numero: str, usuario: str, nome: str, em: datetime
    ) -> ResultadoCondicional[Chamado]:
        """Update com `attribute_not_exists(responsavel)` (Req 14.6). Quem chegar depois
        recebe `aplicado=False` e o Chamado com o responsável vencedor. Chamado encerrado
        não pode ser assumido. Sucesso: status "em_atendimento"."""
        ...

    def reavaliar(
        self, numero: str, decisao: DecisaoRegistrada, pacote: PacoteRepasse
    ) -> ResultadoCondicional[Chamado]:
        """Eleva prioridade/classificação/canal/critério e o Pacote no mesmo Chamado e a
        decisão na Jornada, atomicamente, e reposiciona na fila. Só aplica se a nova
        prioridade for ESTRITAMENTE mais alta (a prioridade nunca diminui, Req 8.5, 9.9);
        caso contrário `aplicado=False`. Chamado encerrado não muda."""
        ...

    def atualizar_campos_ia(
        self,
        numero: str,
        resumo: str,
        sentimento: str,
        proxima_acao: str,
        status: StatusPacoteIA,
    ) -> Chamado:
        """Substitui SÓ os três campos de IA do Pacote (resumo, sentimento, próxima ação) e
        grava `pacote_ia_status` (Req 10.3, 10.4). Os campos determinísticos (prioridade,
        anexos...) ficam como estão, então o enriquecimento tardio não desfaz uma
        reavaliação. O Pacote resultante precisa continuar válido (`validar_pacote`);
        senão levanta `ErroRepositorio` sem gravar."""
        ...

    def marcar_alerta_p1_visto(self, numero: str) -> Chamado: ...

    def definir_resposta_nao_lida(self, numero: str, valor: bool) -> Chamado: ...

    def definir_os_status(self, numero: str, status: StatusOS) -> Chamado: ...

    def definir_agendamento(self, numero: str, data_hora: datetime) -> Chamado: ...

    def adicionar_anexo(
        self, numero: str, anexo: AnexoChamado, maximo: int = 3
    ) -> ResultadoCondicional[Chamado]:
        """Acrescenta a foto com condição `tamanho(anexos) < maximo` (Req 12.7)."""
        ...

    def encerrar(
        self, numero: str, encerramento: EncerramentoChamado
    ) -> ResultadoCondicional[Chamado]:
        """Update com `status <> encerrado`: o primeiro encerramento vence. Remove os
        atributos do `gsi_fila` (o Chamado sai da fila)."""
        ...


class MensagensChamadoRepo(Protocol):
    """Tabela `mensagens_chamado` (PK `numero`, SK `ts_ulid`)."""

    def adicionar(
        self,
        numero: str,
        autor: AutorMensagem,
        texto: str,
        em: datetime,
    ) -> MensagemChamado:
        """Grava uma mensagem; a chave é um ULID monotônico, então a ordem de criação é
        preservada mesmo dentro do mesmo milissegundo. `autor`: atendente ou consumidor."""
        ...

    def listar(self, numero: str) -> list[MensagemChamado]:
        """Mensagens do Chamado em ordem cronológica."""
        ...

    def marcar_lidas(self, numero: str, autor: AutorMensagem) -> int:
        """Marca como lidas as mensagens do `autor` e devolve quantas mudaram."""
        ...


class DadosPessoaisRepo(Protocol):
    """Tabela `dados_pessoais` (PK `numero`): único lugar com telefone e CEP (Req 18)."""

    def salvar(
        self,
        numero: str,
        consentimento: Consentimento,
        telefone: str | None = None,
        cep: str | None = None,
    ) -> DadosPessoaisRegistro:
        """Upsert que preserva o que já estava gravado: só os campos informados
        (não `None`) substituem os atuais (Req 12.4: não pedir de novo)."""
        ...

    def obter(self, numero: str) -> DadosPessoaisRegistro | None: ...


class AcessosPIIRepo(Protocol):
    """Tabela `acessos_pii` (PK `numero`, SK `ts_ulid`): trilha de acesso (Req 18.6)."""

    def registrar(self, numero: str, atendente_id: str, em: datetime) -> AcessoPII:
        """Grava o acesso (horário truncado em segundos). Deve ser chamada ANTES de devolver
        os dados; se levantar `ErroRepositorio`, os dados não são devolvidos (Req 18.9)."""
        ...

    def listar(self, numero: str) -> list[AcessoPII]: ...


class OrdensServicoRepo(Protocol):
    """Tabela `ordens_servico` (PK `os_id` = `OS#<numero>`)."""

    def criar_rascunho(self, ordem: OrdemServico) -> ResultadoCondicional[OrdemServico]:
        """Put com `attribute_not_exists(os_id)`: no máximo uma OS por Chamado (Req 11.8).
        Repetir devolve a existente com `aplicado=False`."""
        ...

    def obter(self, numero: str) -> OrdemServico | None: ...

    def confirmar(self, numero: str) -> ResultadoCondicional[OrdemServico]:
        """rascunho -> aberta (idempotente: já aberta devolve `aplicado=False`)."""
        ...


class CacheRespostasRepo(Protocol):
    """Tabela `cache_respostas` (PK `chave` = `modelo_id#hash`)."""

    def obter(self, chave: str) -> RegistroCache | None:
        """Leitura direta (sem camada extra): disponível logo depois de confirmada."""
        ...

    def inserir(
        self, entrada: EntradaCache, fontes: Sequence[Mapping[str, Any]] = ()
    ) -> ResultadoInsercao:
        """Regra de `dominio.aceitar_insercao_cache` + Put com `attribute_not_exists(chave)`.
        Sem `aprovador_id`: rejeita e não muda nada (Req 7.6, 7.7). Chave existente: mantém a
        entrada e devolve `DUPLICADA` (Req 16.8). A chave é `dominio.chave_cache`."""
        ...

    def registrar_hit(self, chave: str) -> int:
        """`ADD hits 1`; devolve o novo total."""
        ...


class AvaliacoesRepo(Protocol):
    """Tabela `avaliacoes` (PK `jornada_id`)."""

    def registrar(self, avaliacao: Avaliacao) -> ResultadoCondicional[Avaliacao]:
        """Put com `attribute_not_exists(jornada_id)`: uma por Jornada (Req 5.5). A
        segunda devolve a primeira com `aplicado=False`."""
        ...

    def obter(self, jornada_id: str) -> Avaliacao | None: ...

    def listar_periodo(self, inicio: datetime, fim: datetime) -> list[Avaliacao]:
        """Avaliações com `em` em `[inicio, fim]` (inclusivo), cronológicas (métricas)."""
        ...


class AgregadosDiaRepo(Protocol):
    """Tabela `agregados_dia` (PK `dia` ISO, SK `metrica`): contadores atômicos."""

    def incrementar(self, dia: date, metrica: str, delta: int = 1) -> int:
        """`ADD valor delta`; devolve o novo valor. `delta` deve ser positivo."""
        ...

    def obter(self, dia: date, metrica: str) -> int:
        """Valor atual (0 se não existe)."""
        ...

    def listar(self, inicio: date, fim: date) -> list[AgregadoDia]:
        """Agregados dos dias em `[inicio, fim]` (inclusivo), por dia e métrica."""
        ...


class UsuariosCSRepo(Protocol):
    """Tabela `usuarios_cs` (PK `usuario`)."""

    def criar(self, usuario: UsuarioCS) -> ResultadoCondicional[UsuarioCS]:
        """Put com `attribute_not_exists(usuario)`."""
        ...

    def obter(self, usuario: str) -> UsuarioCS | None: ...

    def registrar_falha(self, usuario: str, em: datetime, janela: timedelta) -> UsuarioCS:
        """Acrescenta `em` a `falhas` e descarta as anteriores a `em - janela` (Req 13.8)."""
        ...

    def limpar_falhas(self, usuario: str) -> UsuarioCS: ...

    def bloquear(self, usuario: str, ate: datetime) -> UsuarioCS: ...

    def definir_senha(
        self, usuario: str, hash_senha: str, deve_trocar_senha: bool = False
    ) -> UsuarioCS: ...

    def perfil_de(self, usuario: str) -> PerfilCS | None: ...


class SessoesCSRepo(Protocol):
    """Tabela `sessoes_cs` (PK `token_hash`, TTL no atributo `ttl`)."""

    def criar(self, sessao: SessaoCS) -> None: ...

    def obter(self, token_hash: str) -> SessaoCS | None: ...

    def renovar(self, token_hash: str, agora: datetime, inatividade: timedelta) -> SessaoCS | None:
        """Update condicional `ultima_atividade >= agora - inatividade` (Req 13.5: só passa
        de 30 min sem atividade): sessão
        viva tem `ultima_atividade` e `ttl` renovados; sessão vencida (ou inexistente)
        devolve None e é removida. Não depende da limpeza preguiçosa do TTL do DynamoDB."""
        ...

    def encerrar(self, token_hash: str) -> bool:
        """Remove a sessão (logout). Devolve True se existia."""
        ...


class ConfigRepo(Protocol):
    """Tabela `config` (PK `chave`): limiar, custo por minuto, limite, termos, preços."""

    def obter(self, chave: str) -> Any | None: ...

    def definir(self, chave: str, valor: Any) -> None: ...

    def listar(self) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class Repositorios:
    """Raiz de composição: todos os repositórios (fakes em memória ou DynamoDB)."""

    jornadas: JornadasRepo
    eventos: EventosRepo
    chamados: ChamadosRepo
    mensagens: MensagensChamadoRepo
    dados_pessoais: DadosPessoaisRepo
    acessos_pii: AcessosPIIRepo
    ordens_servico: OrdensServicoRepo
    cache: CacheRespostasRepo
    avaliacoes: AvaliacoesRepo
    agregados: AgregadosDiaRepo
    usuarios_cs: UsuariosCSRepo
    sessoes: SessoesCSRepo
    config: ConfigRepo
    catalogo: CatalogoRepo  # somente leitura (modelos, problemas, instruções)


__all__ = [
    "AcessosPIIRepo",
    "AgregadosDiaRepo",
    "AvaliacoesRepo",
    "CacheRespostasRepo",
    "ChamadosRepo",
    "ConfigRepo",
    "DadosPessoaisRepo",
    "EventosRepo",
    "JornadasRepo",
    "MensagensChamadoRepo",
    "OrdensServicoRepo",
    "Repositorios",
    "SessoesCSRepo",
    "UsuariosCSRepo",
]
