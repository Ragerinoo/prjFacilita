"""Testes de contrato dos repositórios (tarefa 9.3).

A MESMA bateria roda contra o fake em memória (`criar_repositorios_memoria`) e contra os
adaptadores DynamoDB (`criar_repositorios_dynamodb`) sobre `moto`, com as tabelas criadas
como em `infra/stacks/dados_stack.py` (ver `_tabelas_dynamodb.py`). Cada teste cobre uma
garantia de escrita condicional documentada em `repositorios/interfaces.py`:

  Um Chamado por Jornada (9.9)  | um responsável por Chamado (14.6) | uma avaliação (5.5)
  uma camada de resolução (17.1) | cache sem duplicar (16.8)       | uma OS por Chamado (11.8)
  limite de chamadas ao modelo (7.4) | evento sem duplicar (3.12)   | anexos (12.7)
  prioridade nunca diminui (8.5) | índices esparsos (14.1, 17)     | sessão e login (13.5, 13.8)
  trilha de acesso à PII antes dos dados (18.6, 18.9)

Os testes de concorrência usam threads. No DynamoDB cada thread recebe o seu próprio
`boto3.resource` (como invocações Lambda separadas); no fake todas compartilham a instância.

Divergências entre as implementações:
  * O adaptador valida o Pacote com o esquema JSON v1 ao criar o Chamado e ao reavaliar; o fake
    ganhou a mesma validação (`_exigir_pacote_valido` em `repositorios/memoria.py`).
  * Os testes `test_dynamodb_*` conferem atributos de índice no item cru e só fazem sentido no
    DynamoDB; ficam marcados com a fixture `so_dynamodb`.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import boto3
import pytest
from _tabelas_dynamodb import PREFIXO, TABELAS, criar_tabelas

from dominio import (
    EntradaCache,
    ItemJaTentado,
    PacoteRepasse,
    StatusInsercao,
    chave_cache,
    normalizar_pergunta,
)
from repositorios import (
    ErroNaoEncontrado,
    ErroRepositorio,
    Repositorios,
    criar_repositorios_memoria,
)
from repositorios.dynamodb import config_cliente_curta, criar_repositorios_dynamodb
from repositorios.ids import novo_ulid
from repositorios.modelos import (
    AnexoChamado,
    Avaliacao,
    Chamado,
    Consentimento,
    DecisaoRegistrada,
    EncerramentoChamado,
    Evento,
    GatilhoRegistrado,
    Jornada,
    OrdemServico,
    SessaoCS,
    UsuarioCS,
)

try:  # `moto` é opcional na coleta: sem ele só os casos DynamoDB são pulados (ver `amb`)
    from moto import mock_aws
except ImportError:  # pragma: no cover - depende do ambiente
    mock_aws = None

T0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
THREADS = 8

# ----------------------------------------------------------------------------- ambientes


@dataclass(frozen=True)
class Ambiente:
    """Uma implementação sob teste. `visao()` devolve repositórios sobre o MESMO armazenamento
    (no DynamoDB, com um cliente novo; no fake, a própria instância)."""

    nome: str
    repos: Repositorios
    recurso: Any | None
    visao: Callable[[], Repositorios]


def _novo_recurso() -> Any:
    sessao = boto3.session.Session(region_name="us-east-1")
    return sessao.resource("dynamodb", region_name="us-east-1", config=config_cliente_curta())


def _serializar_requisicoes_do_moto(monkeypatch: pytest.MonkeyPatch) -> None:
    """Faz o `moto` tratar cada requisição como atômica.

    O DynamoDB de verdade executa cada `PutItem`/`UpdateItem`/`TransactWriteItems` de forma
    atômica por item (a condição e a escrita não se intercalam com outra escrita). O `moto`
    não tem trava: com threads, duas escritas condicionais leem o mesmo estado e as duas
    passam (comprovado com `adicionar_anexo`, `encerrar` e `incrementar`, que deram resultados
    diferentes a cada execução). A trava global abaixo devolve ao emulador a atomicidade do
    serviço real, sem esconder falhas do adaptador: a lógica de repetição otimista do
    adaptador continua sendo exercitada, porque as leituras e as escritas dele são
    requisições separadas e se intercalam normalmente.
    """
    from moto.core.botocore_stubber import BotocoreStubber

    original = BotocoreStubber.process_request
    trava = threading.RLock()

    def atomica(self, request):
        with trava:
            return original(self, request)

    monkeypatch.setattr(BotocoreStubber, "process_request", atomica)


@pytest.fixture(params=["memoria", "dynamodb"])
def amb(request, monkeypatch):
    if request.param == "memoria":
        repos = criar_repositorios_memoria()
        yield Ambiente("memoria", repos, None, lambda: repos)
        return
    if mock_aws is None:
        pytest.skip("moto não instalado: caso DynamoDB indisponível neste ambiente")
    for chave in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(chave, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    _serializar_requisicoes_do_moto(monkeypatch)
    with mock_aws():
        recurso = _novo_recurso()
        criar_tabelas(recurso)
        yield Ambiente(
            "dynamodb",
            criar_repositorios_dynamodb(recurso, PREFIXO),
            recurso,
            lambda: criar_repositorios_dynamodb(_novo_recurso(), PREFIXO),
        )


@pytest.fixture
def repos(amb: Ambiente) -> Repositorios:
    return amb.repos


@pytest.fixture
def so_dynamodb(amb: Ambiente) -> Ambiente:
    if amb.recurso is None:
        pytest.skip("verificação de item cru: só se aplica ao DynamoDB")
    return amb


def em_paralelo[T](amb: Ambiente, n: int, tarefa: Callable[[Repositorios, int], T]) -> list[T]:
    """Executa `tarefa(repos, i)` em `n` threads liberadas ao mesmo tempo; propaga exceções."""
    visoes = [amb.visao() for _ in range(n)]  # clientes criados antes, na thread principal
    largada = threading.Barrier(n, timeout=60)

    def rodar(i: int) -> T:
        largada.wait()
        return tarefa(visoes[i], i)

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(rodar, range(n)))


# ----------------------------------------------------------------------------- fábricas


def numero(i: int) -> str:
    return "TRES-" + ALFABETO[i % 32] * 9 + ALFABETO[(i // 32) % 32]


def jornada(jid: str = "J1", em: datetime = T0) -> Jornada:
    return Jornada(
        jornada_id=jid, criada_em=em, ultima_interacao=em, origem="qr", origem_inicial="qr"
    )


def pacote(num: str, prioridade: str = "P3") -> PacoteRepasse:
    return PacoteRepasse(
        numero_chamado=num,
        modelo="Máquina Café — Modelo X",
        numero_serie="não informado",
        origem="qr",
        categoria="nao_liga",
        resumo="Resumo indisponível — ver histórico da Jornada",
        ja_tentado=(ItemJaTentado("Problema 1, passo 2", "guia", "não"),),
        classificacao="provável uso",
        prioridade=prioridade,  # type: ignore[arg-type]
        canal_recomendado="chat assíncrono",
        sentimento="neutro",
        anexos=(),
        proxima_acao="Revisar o histórico da Jornada",
    )


def chamado(num: str, jid: str = "J1", prioridade: str = "P3", em: datetime = T0) -> Chamado:
    return Chamado(
        numero=num,
        jornada_id=jid,
        criado_em=em,
        prioridade=prioridade,  # type: ignore[arg-type]
        classificacao="provável uso",
        canal="chat assíncrono",
        decisao_criterio=3,
        pacote=pacote(num, prioridade),
    )


def decisao(prioridade: str, em: datetime = T0) -> DecisaoRegistrada:
    criterio = {"P1": 1, "P2": 2, "P3": 3}[prioridade]
    return DecisaoRegistrada(prioridade, "provável defeito", "canal", criterio, em)  # type: ignore[arg-type]


def gatilho(tipo: str = "pedido_humano") -> GatilhoRegistrado:
    return GatilhoRegistrado(tipo, T0)  # type: ignore[arg-type]


def escalar(repos: Repositorios, jid: str, num: str, prioridade: str = "P3", em: datetime = T0):
    return repos.chamados.criar_com_escalada(
        chamado(num, jid, prioridade, em), gatilho(), decisao(prioridade, em)
    )


def com_chamado(repos: Repositorios, num: str = "", prioridade: str = "P3") -> str:
    """Cria a Jornada J1 e seu Chamado; devolve o número."""
    num = num or numero(1)
    repos.jornadas.criar(jornada("J1"))
    assert escalar(repos, "J1", num, prioridade).criado
    return num


def encerramento(por: str = "bruno", desfecho: str = "falso_defeito") -> EncerramentoChamado:
    return EncerramentoChamado(desfecho, "outra", f"solução de {por}", T0, por)  # type: ignore[arg-type]


# ----------------------------------------------------------------------------- infraestrutura


def test_tabelas_espelham_a_stack_cdk() -> None:
    """Acusa divergência entre as tabelas dos testes e `infra/stacks/dados_stack.py`."""
    import sys
    from pathlib import Path

    pytest.importorskip("aws_cdk")
    infra = str(Path(__file__).resolve().parents[3] / "infra")
    sys.path.insert(0, infra)
    try:
        from stacks.dados_stack import TABELAS as TABELAS_CDK
    finally:
        sys.path.remove(infra)

    esperado = {
        (
            t.nome,
            t.pk,
            "N" if t.pk_tipo.name == "NUMBER" else "S",
            t.sk,
            t.ttl,
            tuple((i.nome, i.pk, i.sk) for i in t.indices),
        )
        for t in TABELAS_CDK
    }
    atual = {(n, pk, tp, sk, ttl, tuple(ix)) for n, pk, tp, sk, ttl, ix in TABELAS}
    assert atual == esperado


# ============================================================================= Jornadas


def test_jornada_criacao_condicional_e_ida_e_volta(repos) -> None:
    j = jornada()
    assert repos.jornadas.criar(j).aplicado
    assert repos.jornadas.obter("J1") == j
    outra = repos.jornadas.criar(Jornada("J1", T0, T0, "busca", "busca"))
    assert not outra.aplicado and outra.registro.origem == "qr"
    assert repos.jornadas.obter("J1").origem == "qr"
    assert repos.jornadas.obter("nada") is None


def test_mutacao_em_registro_inexistente_levanta_erro_nao_encontrado(repos) -> None:
    with pytest.raises(ErroNaoEncontrado):
        repos.jornadas.marcar_guia_respondeu_nao("nada")
    with pytest.raises(ErroNaoEncontrado):
        repos.jornadas.incrementar_msgs_modelo("nada", 10)
    with pytest.raises(ErroNaoEncontrado):
        repos.jornadas.encerrar("nada", "guia", T0)
    with pytest.raises(ErroNaoEncontrado):
        repos.chamados.assumir("TRES-NADA", "ana", "Ana", T0)
    with pytest.raises(ErroNaoEncontrado):
        repos.chamados.encerrar("TRES-NADA", encerramento())
    with pytest.raises(ErroNaoEncontrado):
        repos.ordens_servico.confirmar(numero(9))
    with pytest.raises(ErroNaoEncontrado):
        repos.cache.registrar_hit("tres-x#nada")
    with pytest.raises(ErroNaoEncontrado):
        repos.usuarios_cs.registrar_falha("ninguem", T0, timedelta(minutes=15))


def test_mutacoes_simples_da_jornada(repos) -> None:
    repos.jornadas.criar(jornada())
    j = repos.jornadas.associar_modelo("J1", "tres-modelo-x", "ABC123")
    assert (j.modelo_id, j.numero_serie, j.origem, j.origem_inicial) == (
        "tres-modelo-x",
        "ABC123",
        "busca",
        "qr",
    )
    assert repos.jornadas.associar_modelo("J1", "tres-modelo-y").numero_serie == "ABC123"
    j = repos.jornadas.registrar_seletor("J1", "luz_1", "piscando")
    assert (j.seletor_area, j.seletor_estado) == ("luz_1", "piscando")
    assert repos.jornadas.marcar_guia_respondeu_nao("J1").guia_respondeu_nao
    assert repos.jornadas.incrementar_ia_nao("J1").ia_nao == 1
    assert repos.jornadas.incrementar_ia_nao("J1").ia_nao == 2
    assert repos.jornadas.atualizar_frustracao("J1", "alta").frustracao_alta_seq == 1
    assert repos.jornadas.atualizar_frustracao("J1", "alta").frustracao_alta_seq == 2
    assert repos.jornadas.atualizar_frustracao("J1", "média").frustracao_alta_seq == 0
    repos.jornadas.somar_custo_ia("J1", Decimal("0.0123"))
    assert repos.jornadas.somar_custo_ia("J1", Decimal("0.0002")).custo_ia_brl == Decimal("0.0125")
    with pytest.raises(ValueError):
        repos.jornadas.somar_custo_ia("J1", Decimal("-1"))


def test_problema_selecionado_so_conta_na_primeira_vez(repos) -> None:
    repos.jornadas.criar(jornada())
    assert repos.jornadas.registrar_problema_selecionado("J1", 7) is True
    assert repos.jornadas.registrar_problema_selecionado("J1", 7) is False
    assert repos.jornadas.registrar_problema_selecionado("J1", 3) is True
    j = repos.jornadas.obter("J1")
    assert j.problema_id == 3 and j.problemas_selecionados == (7, 3)


def test_problema_selecionado_concorrente_conta_uma_vez(amb) -> None:
    amb.repos.jornadas.criar(jornada())
    primeiras = em_paralelo(
        amb, THREADS, lambda r, _: r.jornadas.registrar_problema_selecionado("J1", 7)
    )
    assert primeiras.count(True) == 1
    assert amb.repos.jornadas.obter("J1").problemas_selecionados == (7,)


def test_interacao_nao_retrocede_nem_altera_jornada_encerrada(repos) -> None:
    repos.jornadas.criar(jornada())
    t1 = T0 + timedelta(minutes=5)
    assert repos.jornadas.registrar_interacao("J1", t1).ultima_interacao == t1
    assert repos.jornadas.registrar_interacao("J1", T0).ultima_interacao == t1
    repos.jornadas.encerrar("J1", "guia", t1)
    assert repos.jornadas.registrar_interacao("J1", t1 + timedelta(hours=1)).ultima_interacao == t1


# ------------------------------------------------------------- risco monotônico (Req 8.4)


def test_risco_e_monotonico(repos) -> None:
    repos.jornadas.criar(jornada())
    primeira = repos.jornadas.marcar_risco("J1", "lista", T0)
    segunda = repos.jornadas.marcar_risco("J1", "ia", T0 + timedelta(minutes=1))
    assert primeira.aplicado and not segunda.aplicado
    assert segunda.registro.risco.origem == "lista" and segunda.registro.risco.em == T0
    assert repos.jornadas.obter("J1").risco == primeira.registro.risco


def test_risco_concorrente_so_uma_marcacao_vence(amb) -> None:
    amb.repos.jornadas.criar(jornada())
    origens = ["lista", "ia", "guia"]
    rs = em_paralelo(
        amb,
        THREADS,
        lambda r, i: r.jornadas.marcar_risco("J1", origens[i % 3], T0 + timedelta(seconds=i)),
    )
    vencedoras = [r for r in rs if r.aplicado]
    assert len(vencedoras) == 1
    assert amb.repos.jornadas.obter("J1").risco == vencedoras[0].registro.risco
    assert {r.registro.risco for r in rs} == {vencedoras[0].registro.risco}


# ----------------------------------------------- limite de chamadas ao modelo (Req 7.4, 7.5)


def test_decima_chamada_ao_modelo_e_permitida_e_a_decima_primeira_recusada(repos) -> None:
    repos.jornadas.criar(jornada())
    resultados = [repos.jornadas.incrementar_msgs_modelo("J1", 10) for _ in range(11)]
    assert [r.aplicado for r in resultados] == [True] * 10 + [False]
    assert [r.registro.msgs_modelo for r in resultados] == [*range(1, 11), 10]
    assert repos.jornadas.obter("J1").msgs_modelo == 10


def test_limite_de_chamadas_ao_modelo_sob_concorrencia(amb) -> None:
    amb.repos.jornadas.criar(jornada())
    n = 25
    rs = em_paralelo(amb, n, lambda r, _: r.jornadas.incrementar_msgs_modelo("J1", 10))
    assert sum(r.aplicado for r in rs) == 10
    assert amb.repos.jornadas.obter("J1").msgs_modelo == 10


# ------------------------------------------------ uma camada de resolução (Req 17.1, 17.2)


def test_primeira_camada_de_encerramento_vence(repos) -> None:
    repos.jornadas.criar(jornada())
    fim = T0 + timedelta(minutes=10)
    primeiro = repos.jornadas.encerrar("J1", "ia", fim, Decimal("0.0456"), problema_id=4)
    segundo = repos.jornadas.encerrar("J1", "guia", fim + timedelta(minutes=1))
    assert primeiro.aplicado and not segundo.aplicado
    j = repos.jornadas.obter("J1")
    enc = j.encerramento
    assert (j.estado, enc.camada, enc.tempo_s, enc.custo_brl, enc.problema_id) == (
        "encerrada",
        "ia",
        600,
        Decimal("0.05"),
        4,
    )
    assert segundo.jornada.encerramento.camada == "ia"
    assert (j.ativa_pk, j.encerrada_pk, j.encerrada_em) == (None, "ENC", fim)


def test_encerramento_sob_concorrencia_so_uma_camada_vence(amb) -> None:
    amb.repos.jornadas.criar(jornada())
    camadas = ["guia", "ia", "humano"]
    rs = em_paralelo(
        amb,
        THREADS,
        lambda r, i: r.jornadas.encerrar("J1", camadas[i % 3], T0 + timedelta(minutes=1 + i)),
    )
    vencedoras = [r for r in rs if r.aplicado]
    assert len(vencedoras) == 1
    final = amb.repos.jornadas.obter("J1").encerramento
    assert final == vencedoras[0].jornada.encerramento
    assert {r.jornada.encerramento for r in rs} == {final}  # todos veem a camada vencedora


def test_abandono_respeita_30_minutos_exige_ausencia_de_chamado_e_e_terminal(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    repos.jornadas.criar(jornada("J2"))
    escalar(repos, "J2", numero(2))
    assert not repos.jornadas.marcar_abandono("J1", T0 + timedelta(minutes=29)).aplicado
    assert not repos.jornadas.marcar_abandono("J2", T0 + timedelta(hours=2)).aplicado  # tem Chamado
    assert repos.jornadas.marcar_abandono("J1", T0 + timedelta(minutes=30)).aplicado
    # Terminal: nem outro abandono, nem encerramento por camada, nem interação mudam algo.
    assert not repos.jornadas.marcar_abandono("J1", T0 + timedelta(hours=2)).aplicado
    assert not repos.jornadas.encerrar("J1", "ia", T0 + timedelta(hours=1)).aplicado
    j = repos.jornadas.registrar_interacao("J1", T0 + timedelta(hours=3))
    assert j.estado == "encerrada" and j.encerramento.camada == "abandonada"
    assert j.ultima_interacao == T0
    assert repos.jornadas.obter("J2").estado == "escalada"


def test_abandono_nao_vence_uma_interacao_concorrente(amb) -> None:
    """Invariante em qualquer ordem de execução: abandonou <=> Jornada ficou encerrada."""
    agora = T0 + timedelta(minutes=40)
    for rodada in range(4):
        jid = f"J{rodada}"
        amb.repos.jornadas.criar(jornada(jid))

        def tarefa(r: Repositorios, i: int, jid: str = jid):
            if i == 0:
                return r.jornadas.marcar_abandono(jid, agora)
            r.jornadas.registrar_interacao(jid, agora)
            return None

        abandono = em_paralelo(amb, 2, tarefa)[0]
        final = amb.repos.jornadas.obter(jid)
        assert abandono.aplicado == (final.estado == "encerrada")
        if abandono.aplicado:
            assert final.encerramento.camada == "abandonada" and final.ultima_interacao == T0
        else:
            assert final.estado == "ativa" and final.ultima_interacao == agora


def test_escalada_concorrente_com_encerramento_termina_encerrada_com_chamado(amb) -> None:
    for rodada in range(3):
        jid = f"J{rodada}"
        amb.repos.jornadas.criar(jornada(jid))

        def tarefa(r: Repositorios, i: int, jid: str = jid, rodada: int = rodada):
            if i == 0:
                return r.jornadas.encerrar(jid, "guia", T0 + timedelta(minutes=2))
            return escalar(r, jid, numero(rodada))

        em_paralelo(amb, 2, tarefa)
        j = amb.repos.jornadas.obter(jid)
        assert j.estado == "encerrada" and j.encerramento.camada == "guia"
        assert j.escalada is not None and j.escalada.chamado_numero == numero(rodada)


# ---------------------------------------------------------------- índices esparsos das Jornadas


def test_gsi_ativas_so_tem_jornada_ativa_sem_chamado(repos) -> None:
    for jid, minutos in (("A", 10), ("B", 40), ("C", 50), ("D", 5), ("E", 6)):
        repos.jornadas.criar(jornada(jid, T0 + timedelta(minutes=minutos)))
    ate = T0 + timedelta(minutes=45)
    ids = lambda: [j.jornada_id for j in repos.jornadas.listar_ativas_sem_interacao_ate(ate)]  # noqa: E731
    assert ids() == ["D", "E", "A", "B"]  # mais antiga primeiro; limite inclusivo (B = 40 < 45)
    assert [
        j.jornada_id
        for j in repos.jornadas.listar_ativas_sem_interacao_ate(T0 + timedelta(minutes=40))
    ] == ["D", "E", "A", "B"]  # exatamente no limite entra
    repos.jornadas.encerrar("A", "guia", T0 + timedelta(hours=2))
    escalar(repos, "D", numero(4))
    repos.jornadas.marcar_abandono("E", T0 + timedelta(hours=1))
    assert ids() == ["B"]
    repos.jornadas.registrar_interacao("B", T0 + timedelta(minutes=44))
    assert [j.ultima_interacao for j in repos.jornadas.listar_ativas_sem_interacao_ate(ate)] == [
        T0 + timedelta(minutes=44)
    ]


def test_gsi_encerradas_filtra_por_intervalo_inclusivo_em_ordem_cronologica(repos) -> None:
    for jid in ("A", "B", "C"):
        repos.jornadas.criar(jornada(jid))
    repos.jornadas.encerrar("A", "guia", T0 + timedelta(hours=2))
    repos.jornadas.encerrar("B", "ia", T0 + timedelta(hours=1))
    repos.jornadas.encerrar("C", "humano", T0 + timedelta(hours=3))
    listar = repos.jornadas.listar_encerradas
    assert [j.jornada_id for j in listar(T0, T0 + timedelta(hours=3))] == ["B", "A", "C"]
    assert [j.jornada_id for j in listar(T0 + timedelta(hours=1), T0 + timedelta(hours=2))] == [
        "B",
        "A",
    ]
    assert listar(T0, T0 + timedelta(minutes=30)) == []
    assert listar(T0 + timedelta(hours=3, seconds=1), T0 + timedelta(days=1)) == []


def test_dynamodb_atributos_de_indice_esparso_da_jornada(so_dynamodb) -> None:
    repos, tabela = so_dynamodb.repos, so_dynamodb.recurso.Table(f"{PREFIXO}-jornadas")
    item = lambda jid: tabela.get_item(Key={"jornada_id": jid}, ConsistentRead=True)["Item"]  # noqa: E731
    for jid in ("A", "B", "C"):
        repos.jornadas.criar(jornada(jid))
    assert item("A")["ativa_pk"] == "ATIVA" and "encerrada_pk" not in item("A")
    escalar(repos, "B", numero(2))
    assert "ativa_pk" not in item("B") and "encerrada_pk" not in item("B")
    repos.jornadas.encerrar("C", "guia", T0 + timedelta(minutes=5))
    assert "ativa_pk" not in item("C")
    assert item("C")["encerrada_pk"] == "ENC" and "encerrada_em" in item("C")


# ============================================================================= Eventos


def test_evento_e_idempotente_por_evento_id(repos) -> None:
    eid = novo_ulid(T0)
    original = Evento(
        "J1", eid, "problema_selecionado", T0, {"problema_id": 7, "x": 0.5, "t": "ção"}
    )
    reenvio = Evento("J1", eid, "outro", T0 + timedelta(seconds=5), {"y": 1})
    assert repos.eventos.registrar(original) is True
    assert repos.eventos.registrar(reenvio) is False
    assert repos.eventos.listar("J1") == [original]  # o original permanece


def test_eventos_voltam_em_ordem_cronologica_e_isolados_por_jornada(repos) -> None:
    ids = [novo_ulid(T0 + timedelta(seconds=i)) for i in range(3)]
    for eid in reversed(ids):
        repos.eventos.registrar(Evento("J1", eid, "x", T0))
    repos.eventos.registrar(Evento("J2", novo_ulid(T0), "x", T0))
    assert [e.evento_id for e in repos.eventos.listar("J1")] == ids
    assert repos.eventos.listar("J3") == []


def test_evento_reenviado_em_paralelo_grava_uma_vez(amb) -> None:
    eid = novo_ulid(T0)
    rs = em_paralelo(amb, THREADS, lambda r, i: r.eventos.registrar(Evento("J1", eid, f"t{i}", T0)))
    assert rs.count(True) == 1
    assert len(amb.repos.eventos.listar("J1")) == 1


# ============================================================================= Chamados


# ---------------------------------------------- um Chamado por Jornada, tudo ou nada (Req 9.9)


def test_criar_com_escalada_grava_chamado_e_marca_a_jornada(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    r = escalar(repos, "J1", numero(1), "P2")
    assert (r.criado, r.motivo, r.numero_existente) == (True, "criado", None)
    j = repos.jornadas.obter("J1")
    assert j.estado == "escalada" and j.ativa_pk is None
    assert j.escalada.chamado_numero == numero(1) and j.escalada.em == T0
    assert [g.tipo for g in j.escalada.gatilhos] == ["pedido_humano"]
    assert j.escalada.decisao == decisao("P2")
    assert repos.chamados.obter(numero(1)) == chamado(numero(1), "J1", "P2")


def test_um_chamado_por_jornada(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    escalar(repos, "J1", numero(1), "P2")
    segunda = escalar(repos, "J1", numero(2))
    assert (segunda.criado, segunda.motivo, segunda.numero_existente) == (
        False,
        "jornada_ja_escalada",
        numero(1),
    )
    assert repos.chamados.obter(numero(2)) is None  # nada gravado
    assert [c.numero for c in repos.chamados.listar_fila()] == [numero(1)]
    assert repos.jornadas.obter("J1").escalada.chamado_numero == numero(1)


def test_criar_com_escalada_sob_concorrencia_cria_um_unico_chamado(amb) -> None:
    amb.repos.jornadas.criar(jornada("J1"))
    rs = em_paralelo(amb, THREADS, lambda r, i: escalar(r, "J1", numero(10 + i)))
    criados = [i for i, r in enumerate(rs) if r.criado]
    assert len(criados) == 1
    vencedor = numero(10 + criados[0])
    assert {r.motivo for i, r in enumerate(rs) if i != criados[0]} == {"jornada_ja_escalada"}
    assert {r.numero_existente for i, r in enumerate(rs) if i != criados[0]} == {vencedor}
    assert [c.numero for c in amb.repos.chamados.listar_fila()] == [vencedor]
    for i in range(THREADS):
        existe = amb.repos.chamados.obter(numero(10 + i)) is not None
        assert existe == (i == criados[0])  # os perdedores não deixam Chamado órfão
    assert amb.repos.jornadas.obter("J1").escalada.chamado_numero == vencedor


def test_jornada_inexistente_e_numero_em_uso_nao_gravam_nada(repos) -> None:
    r = escalar(repos, "FANTASMA", numero(1))
    assert (r.criado, r.motivo) == (False, "jornada_inexistente")
    assert repos.chamados.obter(numero(1)) is None

    repos.jornadas.criar(jornada("J1"))
    repos.jornadas.criar(jornada("J2"))
    escalar(repos, "J1", numero(1))
    r = escalar(repos, "J2", numero(1))
    assert (r.criado, r.motivo) == (False, "numero_em_uso")
    assert repos.jornadas.obter("J2").escalada is None  # Jornada não foi marcada
    assert repos.jornadas.obter("J2").estado == "ativa"
    assert repos.chamados.obter(numero(1)).jornada_id == "J1"  # o Chamado original está intacto
    assert escalar(repos, "J2", numero(2)).criado  # com outro número a Jornada ainda escala


def test_precedencia_jornada_ja_escalada_sobre_numero_em_uso(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    escalar(repos, "J1", numero(1))
    r = escalar(repos, "J1", numero(1))  # mesma Jornada, mesmo número
    assert (r.motivo, r.numero_existente) == ("jornada_ja_escalada", numero(1))


def test_chamado_novo_precisa_estar_aberto_e_pacote_valido(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    with pytest.raises(ErroRepositorio):
        repos.chamados.criar_com_escalada(
            replace(chamado(numero(1)), status="encerrado"), gatilho(), decisao("P3")
        )
    with pytest.raises(ErroRepositorio):  # número fora do padrão do esquema do Pacote
        repos.chamados.criar_com_escalada(chamado("TRES-curto"), gatilho(), decisao("P3"))
    with pytest.raises(ErroRepositorio):  # resumo vazio
        invalido = replace(chamado(numero(1)), pacote=replace(pacote(numero(1)), resumo=""))
        repos.chamados.criar_com_escalada(invalido, gatilho(), decisao("P3"))
    assert repos.jornadas.obter("J1").escalada is None
    assert repos.chamados.obter("TRES-curto") is None and repos.chamados.obter(numero(1)) is None


def test_jornada_encerrada_ganha_o_chamado_sem_mudar_a_camada(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    repos.jornadas.encerrar("J1", "guia", T0 + timedelta(minutes=2))
    assert escalar(repos, "J1", numero(1), "P1").criado
    j = repos.jornadas.obter("J1")
    assert j.estado == "encerrada" and j.encerramento.camada == "guia"
    assert j.escalada.chamado_numero == numero(1)
    assert [
        j.jornada_id for j in repos.jornadas.listar_encerradas(T0, T0 + timedelta(hours=1))
    ] == ["J1"]


def test_gatilho_adicional_exige_jornada_escalada(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    sem = repos.jornadas.registrar_gatilho_adicional("J1", gatilho())
    assert not sem.aplicado and sem.registro.escalada is None
    escalar(repos, "J1", numero(1))
    r = repos.jornadas.registrar_gatilho_adicional(
        "J1", GatilhoRegistrado("risco_seguranca", T0, False)
    )
    assert r.aplicado
    assert [(g.tipo, g.registrado) for g in r.registro.escalada.gatilhos] == [
        ("pedido_humano", True),
        ("risco_seguranca", False),
    ]
    assert repos.jornadas.obter("J1").escalada.gatilhos == r.registro.escalada.gatilhos


# ---------------------------------------------------- um responsável por Chamado (Req 14.6)


def test_assumir_tem_um_so_responsavel(repos) -> None:
    num = com_chamado(repos)
    a = repos.chamados.assumir(num, "bruno", "Bruno", T0)
    b = repos.chamados.assumir(num, "ana", "Ana", T0 + timedelta(seconds=1))
    assert a.aplicado and a.registro.status == "em_atendimento"
    assert not b.aplicado
    assert (b.registro.responsavel.usuario, b.registro.responsavel.nome) == ("bruno", "Bruno")
    assert repos.chamados.obter(num).responsavel.inicio == T0
    # O próprio responsável também não "reassume".
    assert not repos.chamados.assumir(num, "bruno", "Bruno", T0 + timedelta(minutes=1)).aplicado


def test_assumir_sob_concorrencia_deixa_um_unico_responsavel(amb) -> None:
    num = com_chamado(amb.repos)
    rs = em_paralelo(
        amb,
        THREADS,
        lambda r, i: r.chamados.assumir(num, f"u{i}", f"Nome {i}", T0 + timedelta(seconds=i)),
    )
    vencedores = [i for i, r in enumerate(rs) if r.aplicado]
    assert len(vencedores) == 1
    final = amb.repos.chamados.obter(num)
    assert final.responsavel.usuario == f"u{vencedores[0]}" and final.status == "em_atendimento"
    assert {r.registro.responsavel.usuario for r in rs} == {f"u{vencedores[0]}"}


def test_chamado_encerrado_nao_pode_ser_assumido(repos) -> None:
    num = com_chamado(repos)
    repos.chamados.encerrar(num, encerramento())
    r = repos.chamados.assumir(num, "ana", "Ana", T0)
    assert not r.aplicado and r.registro.responsavel is None and r.registro.status == "encerrado"


# ------------------------------------------------- encerramento do Chamado e fila (Req 14.1)


def test_encerrar_chamado_so_o_primeiro_vence_e_sai_da_fila(repos) -> None:
    num = com_chamado(repos)
    assert [c.numero for c in repos.chamados.listar_fila()] == [num]
    primeiro = encerramento("bruno", "defeito_real")
    assert repos.chamados.encerrar(num, primeiro).aplicado
    depois = repos.chamados.encerrar(num, encerramento("ana"))
    assert not depois.aplicado and depois.registro.encerramento == primeiro
    assert repos.chamados.listar_fila() == []
    c = repos.chamados.obter(num)
    assert (c.status, c.fila_pk, c.fila_sk, c.encerramento) == ("encerrado", None, None, primeiro)


def test_encerrar_chamado_sob_concorrencia(amb) -> None:
    num = com_chamado(amb.repos)
    rs = em_paralelo(amb, THREADS, lambda r, i: r.chamados.encerrar(num, encerramento(f"u{i}")))
    vencedores = [i for i, r in enumerate(rs) if r.aplicado]
    assert len(vencedores) == 1
    assert amb.repos.chamados.obter(num).encerramento.por == f"u{vencedores[0]}"
    assert amb.repos.chamados.listar_fila() == []


def test_fila_ordena_por_prioridade_horario_e_numero(repos) -> None:
    casos = [  # (número, prioridade, minuto)
        (numero(3), "P3", 0),
        (numero(2), "P2", 5),
        (numero(1), "P1", 10),
        (numero(4), "P2", 1),
        (numero(6), "P1", 10),  # empate de prioridade e horário: desempata pelo número
        (numero(5), "P1", 3),
    ]
    for i, (num, prio, minutos) in enumerate(casos):
        repos.jornadas.criar(jornada(f"J{i}"))
        escalar(repos, f"J{i}", num, prio, T0 + timedelta(minutes=minutos))
    assert [c.numero for c in repos.chamados.listar_fila()] == [
        numero(5),
        numero(1),
        numero(6),
        numero(4),
        numero(2),
        numero(3),
    ]


def test_dynamodb_atributos_de_indice_esparso_do_chamado(so_dynamodb) -> None:
    repos, tabela = so_dynamodb.repos, so_dynamodb.recurso.Table(f"{PREFIXO}-chamados")
    num = com_chamado(repos)
    item = tabela.get_item(Key={"numero": num}, ConsistentRead=True)["Item"]
    assert item["fila_pk"] and item["fila_sk"].startswith("P3#")
    repos.chamados.encerrar(num, encerramento())
    item = tabela.get_item(Key={"numero": num}, ConsistentRead=True)["Item"]
    assert "fila_pk" not in item and "fila_sk" not in item


# --------------------------------------------- a prioridade nunca diminui (Req 8.5, 9.9)


def test_reavaliar_so_eleva_a_prioridade_e_reposiciona_na_fila(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    repos.jornadas.criar(jornada("J2"))
    escalar(repos, "J1", numero(1), "P3")
    escalar(repos, "J2", numero(2), "P2", T0 + timedelta(minutes=1))
    assert [c.numero for c in repos.chamados.listar_fila()] == [numero(2), numero(1)]

    eleva = repos.chamados.reavaliar(
        numero(1), decisao("P1", T0 + timedelta(minutes=2)), pacote(numero(1), "P1")
    )
    assert eleva.aplicado
    assert (eleva.registro.prioridade, eleva.registro.pacote.prioridade) == ("P1", "P1")
    assert eleva.registro.fila_sk.startswith("P1#")
    assert [c.numero for c in repos.chamados.listar_fila()] == [numero(1), numero(2)]
    assert repos.jornadas.obter("J1").escalada.decisao == decisao("P1", T0 + timedelta(minutes=2))

    for prio in ("P2", "P1"):  # mais baixa e igual: nada muda
        r = repos.chamados.reavaliar(numero(1), decisao(prio), pacote(numero(1), prio))
        assert not r.aplicado and r.registro.prioridade == "P1"
    c = repos.chamados.obter(numero(1))
    assert c.prioridade == "P1" and c.pacote.prioridade == "P1"
    assert repos.jornadas.obter("J1").escalada.decisao.prioridade == "P1"


def test_reavaliar_nao_muda_chamado_encerrado_e_exige_pacote_coerente_e_valido(repos) -> None:
    num = com_chamado(repos, prioridade="P3")
    with pytest.raises(ErroRepositorio):  # Pacote de outro Chamado
        repos.chamados.reavaliar(num, decisao("P1"), pacote(numero(9), "P1"))
    with pytest.raises(ErroRepositorio):  # Pacote não reflete a nova decisão
        repos.chamados.reavaliar(num, decisao("P1"), pacote(num, "P3"))
    with pytest.raises(ErroRepositorio):  # Pacote inválido no esquema (resumo vazio)
        repos.chamados.reavaliar(num, decisao("P1"), replace(pacote(num, "P1"), resumo=""))
    assert repos.chamados.obter(num).prioridade == "P3"

    repos.chamados.encerrar(num, encerramento())
    r = repos.chamados.reavaliar(num, decisao("P1"), pacote(num, "P1"))
    assert not r.aplicado and repos.chamados.obter(num).prioridade == "P3"


def test_reavaliacoes_concorrentes_terminam_na_maior_prioridade(amb) -> None:
    num = com_chamado(amb.repos, prioridade="P3")
    prios = ["P2", "P1", "P2", "P1"]
    rs = em_paralelo(
        amb,
        len(prios),
        lambda r, i: r.chamados.reavaliar(num, decisao(prios[i]), pacote(num, prios[i])),
    )
    assert any(r.aplicado for r in rs)
    final = amb.repos.chamados.obter(num)
    assert final.prioridade == "P1" and final.pacote.prioridade == "P1"
    assert amb.repos.jornadas.obter("J1").escalada.decisao.prioridade == "P1"
    assert [c.numero for c in amb.repos.chamados.listar_fila()] == [num]


def test_campos_de_ia_nao_desfazem_reavaliacao_e_o_pacote_segue_valido(repos) -> None:
    num = com_chamado(repos)
    repos.chamados.reavaliar(num, decisao("P1"), pacote(num, "P1"))
    c = repos.chamados.atualizar_campos_ia(
        num, "Cliente sem café há dois dias.", "frustração alta", "Ligar agora.", "ok"
    )
    assert c.pacote.prioridade == "P1" and c.pacote_ia_status == "ok"
    assert (c.pacote.resumo, c.pacote.sentimento, c.pacote.proxima_acao) == (
        "Cliente sem café há dois dias.",
        "frustração alta",
        "Ligar agora.",
    )
    assert c.pacote.modelo == "Máquina Café — Modelo X"
    with pytest.raises(ErroRepositorio):  # resumo acima de 300 caracteres
        repos.chamados.atualizar_campos_ia(num, "x" * 301, "neutro", "Ligar.", "fallback")
    with pytest.raises(ErroRepositorio):  # resumo vazio
        repos.chamados.atualizar_campos_ia(num, "", "neutro", "Ligar.", "fallback")
    depois = repos.chamados.obter(num)
    assert depois.pacote.resumo.startswith("Cliente") and depois.pacote_ia_status == "ok"
    with pytest.raises(ErroNaoEncontrado):
        repos.chamados.atualizar_campos_ia(numero(9), "r", "neutro", "a", "ok")


# ---------------------------------------------------------------- anexos (máximo 3, Req 12.7)


def test_anexos_respeitam_o_maximo_e_entram_no_pacote(repos) -> None:
    num = com_chamado(repos)
    resultados = [
        repos.chamados.adicionar_anexo(num, AnexoChamado(f"fotos/{i}.jpg", "image/jpeg", 10))
        for i in range(4)
    ]
    assert [r.aplicado for r in resultados] == [True, True, True, False]
    c = repos.chamados.obter(num)
    assert [a.chave for a in c.anexos] == [f"fotos/{i}.jpg" for i in range(3)]
    assert [a.chave for a in c.pacote.anexos] == [f"fotos/{i}.jpg" for i in range(3)]
    assert resultados[3].registro.anexos == c.anexos  # a recusada devolve o estado atual


def test_anexos_usam_o_maximo_informado_e_sob_concorrencia_ficam_em_tres(amb) -> None:
    num = com_chamado(amb.repos)
    rs = em_paralelo(
        amb,
        6,
        lambda r, i: r.chamados.adicionar_anexo(num, AnexoChamado(f"f/{i}.png", "image/png", 1)),
    )
    assert sum(r.aplicado for r in rs) == 3
    c = amb.repos.chamados.obter(num)
    assert len(c.anexos) == 3 and len(c.pacote.anexos) == 3
    assert not amb.repos.chamados.adicionar_anexo(
        num, AnexoChamado("f/9.png", "image/png", 1), maximo=3
    ).aplicado

    outro = com_chamado_na_jornada(amb.repos, "J2", numero(2))
    resultados = [
        amb.repos.chamados.adicionar_anexo(
            outro, AnexoChamado(f"g/{i}.png", "image/png", 1), maximo=2
        ).aplicado
        for i in range(3)
    ]
    assert resultados == [True, True, False]


def com_chamado_na_jornada(repos: Repositorios, jid: str, num: str) -> str:
    repos.jornadas.criar(jornada(jid))
    assert escalar(repos, jid, num).criado
    return num


def test_flags_agendamento_e_alerta(repos) -> None:
    num = com_chamado(repos, prioridade="P1")
    brasilia = datetime(2025, 1, 2, 14, 0, tzinfo=timezone(timedelta(hours=-3)))
    c = repos.chamados.definir_agendamento(num, brasilia)
    assert c.agendamento == brasilia and c.agendamento.utcoffset() == brasilia.utcoffset()
    assert repos.chamados.marcar_alerta_p1_visto(num).alerta_p1_visto
    assert repos.chamados.definir_resposta_nao_lida(num, True).resposta_nao_lida
    assert repos.chamados.definir_os_status(num, "ok").os_status == "ok"
    assert repos.chamados.obter(num).agendamento == brasilia


# ============================================================================= Mensagens


def test_mensagens_preservam_a_ordem_de_criacao_no_mesmo_instante(repos) -> None:
    textos = [f"m{i}" for i in range(15)]
    for t in textos:
        repos.mensagens.adicionar(numero(1), "atendente", t, T0)
    assert [m.texto for m in repos.mensagens.listar(numero(1))] == textos
    assert repos.mensagens.listar(numero(2)) == []


def test_marcar_lidas_so_do_autor_pedido_e_conta_uma_vez(repos) -> None:
    repos.mensagens.adicionar(numero(1), "atendente", "a", T0)
    repos.mensagens.adicionar(numero(1), "consumidor", "b", T0)
    repos.mensagens.adicionar(numero(1), "consumidor", "c", T0)
    assert repos.mensagens.marcar_lidas(numero(1), "consumidor") == 2
    assert repos.mensagens.marcar_lidas(numero(1), "consumidor") == 0
    lidas = {m.texto: m.lida for m in repos.mensagens.listar(numero(1))}
    assert lidas == {"a": False, "b": True, "c": True}


def test_mensagens_concorrentes_nao_se_perdem(amb) -> None:
    rs = em_paralelo(
        amb, THREADS, lambda r, i: r.mensagens.adicionar(numero(1), "consumidor", f"t{i}", T0)
    )
    listadas = amb.repos.mensagens.listar(numero(1))
    assert len(listadas) == THREADS and len({m.ts_ulid for m in listadas}) == THREADS
    assert {m.texto for m in listadas} == {m.texto for m in rs}


# ============================================================================= PII (Req 18)


def test_dados_pessoais_preservam_o_que_ja_foi_informado(repos) -> None:
    repos.dados_pessoais.salvar(numero(1), Consentimento(T0, "v1"), telefone="11999990000")
    d = repos.dados_pessoais.salvar(numero(1), Consentimento(T0, "v2"), cep="01001000")
    assert (d.telefone, d.cep, d.consentimento.versao_finalidade) == (
        "11999990000",
        "01001000",
        "v2",
    )
    assert repos.dados_pessoais.obter(numero(1)) == d
    assert repos.dados_pessoais.obter(numero(9)) is None


def test_acesso_pii_fica_gravado_assim_que_registrar_devolve(repos) -> None:
    """O log é gravado e legível imediatamente: a rota o grava ANTES de devolver os dados."""
    repos.dados_pessoais.salvar(numero(1), Consentimento(T0, "v1"), telefone="11999990000")
    acesso = repos.acessos_pii.registrar(numero(1), "bruno", T0 + timedelta(microseconds=987654))
    assert acesso.em == T0 and (acesso.numero, acesso.atendente_id) == (numero(1), "bruno")
    assert repos.acessos_pii.listar(numero(1)) == [acesso]  # leitura logo depois, sem atraso
    assert repos.dados_pessoais.obter(numero(1)).telefone == "11999990000"  # só então os dados


def test_acessos_pii_no_mesmo_segundo_nao_se_sobrescrevem_e_mantem_a_ordem(repos) -> None:
    acessos = [repos.acessos_pii.registrar(numero(1), f"u{i}", T0) for i in range(6)]
    assert repos.acessos_pii.listar(numero(1)) == acessos
    repos.acessos_pii.registrar(numero(2), "ana", T0)
    assert (
        len(repos.acessos_pii.listar(numero(1))) == 6 and repos.acessos_pii.listar(numero(3)) == []
    )


def test_acessos_pii_concorrentes_nao_perdem_registros(amb) -> None:
    em_paralelo(amb, THREADS, lambda r, i: r.acessos_pii.registrar(numero(1), f"u{i}", T0))
    assert sorted(a.atendente_id for a in amb.repos.acessos_pii.listar(numero(1))) == sorted(
        f"u{i}" for i in range(THREADS)
    )


def test_dynamodb_falha_na_trilha_levanta_erro_e_nao_grava(so_dynamodb) -> None:
    """Sem trilha, sem dados (Req 18.9): a falha do log sobe como `ErroRepositorio`.

    Só o DynamoDB tem uma falha de infraestrutura natural a provocar (tabela indisponível).
    """
    so_dynamodb.recurso.Table(f"{PREFIXO}-acessos_pii").delete()
    with pytest.raises(ErroRepositorio):
        so_dynamodb.repos.acessos_pii.registrar(numero(1), "bruno", T0)


# ============================================================================= OS, cache


def test_uma_ordem_de_servico_por_chamado_com_chave_deterministica(repos) -> None:
    os1 = OrdemServico(
        numero(1), "Modelo X", "S1", "nao_liga", (ItemJaTentado("p", "guia", "não"),)
    )
    primeira = repos.ordens_servico.criar_rascunho(os1)
    segunda = repos.ordens_servico.criar_rascunho(OrdemServico(numero(1), "Outro", "S2", "outro"))
    assert primeira.aplicado and not segunda.aplicado
    assert segunda.registro == os1 and repos.ordens_servico.obter(numero(1)) == os1
    assert os1.os_id == f"OS#{numero(1)}"
    assert repos.ordens_servico.obter(numero(2)) is None
    assert repos.ordens_servico.confirmar(numero(1)).registro.status == "aberta"
    assert not repos.ordens_servico.confirmar(numero(1)).aplicado  # idempotente


def test_ordem_de_servico_sob_concorrencia_uma_unica_vence(amb) -> None:
    rs = em_paralelo(
        amb,
        THREADS,
        lambda r, i: r.ordens_servico.criar_rascunho(
            OrdemServico(numero(1), f"Modelo {i}", f"S{i}", "nao_liga")
        ),
    )
    vencedores = [i for i, r in enumerate(rs) if r.aplicado]
    assert len(vencedores) == 1
    assert amb.repos.ordens_servico.obter(numero(1)).modelo == f"Modelo {vencedores[0]}"
    assert {r.registro.modelo for r in rs} == {f"Modelo {vencedores[0]}"}


def test_cache_so_com_aprovador_e_sem_duplicar(repos) -> None:
    entrada = EntradaCache("tres-x", "Como limpo o filtro?", "Retire e lave.", "bruno", T0)
    chave = chave_cache("tres-x", "Como limpo o filtro?")

    for aprovador in (None, "", "   "):
        r = repos.cache.inserir(EntradaCache("tres-x", "Como limpo o filtro?", "r", aprovador, T0))
        assert r.status is StatusInsercao.REJEITADA_SEM_APROVADOR
    assert repos.cache.obter(chave) is None  # nada foi gravado sem aprovador

    assert repos.cache.inserir(entrada, fontes=[{"manual": "m.pdf", "pontuacao": 0.8}]).aceita
    dup = repos.cache.inserir(EntradaCache("tres-x", "como limpo o FILTRO?", "outra", "ana", T0))
    assert dup.status is StatusInsercao.DUPLICADA and dup.entrada.resposta == "Retire e lave."
    r = repos.cache.obter(chave)
    assert (r.resposta, r.aprovador_id, r.aprovado_em, r.hits) == ("Retire e lave.", "bruno", T0, 0)
    assert r.pergunta_normalizada == normalizar_pergunta("Como limpo o filtro?")
    assert r.fontes == ({"manual": "m.pdf", "pontuacao": 0.8},)
    assert repos.cache.registrar_hit(chave) == 1 and repos.cache.registrar_hit(chave) == 2
    assert repos.cache.obter(chave).hits == 2


def test_cache_separa_modelos(repos) -> None:
    for modelo in ("m1", "m2"):
        assert repos.cache.inserir(EntradaCache(modelo, "pergunta", "r", "bruno", T0)).aceita


def test_cache_insercao_concorrente_da_mesma_chave_aceita_uma_so(amb) -> None:
    rs = em_paralelo(
        amb,
        THREADS,
        lambda r, i: r.cache.inserir(EntradaCache("m1", "Como limpar?", f"resp{i}", f"u{i}", T0)),
    )
    aceitas = [i for i, r in enumerate(rs) if r.aceita]
    assert len(aceitas) == 1
    assert all(r.status is StatusInsercao.DUPLICADA for i, r in enumerate(rs) if i != aceitas[0])
    registro = amb.repos.cache.obter(chave_cache("m1", "Como limpar?"))
    assert registro.resposta == f"resp{aceitas[0]}"
    assert {r.entrada.resposta for r in rs} == {f"resp{aceitas[0]}"}  # todos veem a vencedora


def test_cache_hits_concorrentes_nao_se_perdem(amb) -> None:
    chave = chave_cache("m1", "pergunta")
    amb.repos.cache.inserir(EntradaCache("m1", "pergunta", "r", "bruno", T0))
    totais = em_paralelo(amb, THREADS, lambda r, _: r.cache.registrar_hit(chave))
    assert sorted(totais) == list(range(1, THREADS + 1))


# ============================================================================= Avaliações


def test_uma_avaliacao_por_jornada(repos) -> None:
    a1 = Avaliacao("J1", 5, "guia", T0, "ótimo")
    assert repos.avaliacoes.registrar(a1).aplicado
    segunda = repos.avaliacoes.registrar(Avaliacao("J1", 1, "ia", T0, "péssimo"))
    assert not segunda.aplicado and segunda.registro == a1
    assert repos.avaliacoes.obter("J1") == a1 and repos.avaliacoes.obter("J9") is None


def test_avaliacao_sob_concorrencia_uma_unica_vence(amb) -> None:
    rs = em_paralelo(
        amb, THREADS, lambda r, i: r.avaliacoes.registrar(Avaliacao("J1", 1 + i % 5, "ia", T0))
    )
    vencedores = [i for i, r in enumerate(rs) if r.aplicado]
    assert len(vencedores) == 1
    assert amb.repos.avaliacoes.obter("J1").nota == 1 + vencedores[0] % 5
    assert {r.registro.nota for r in rs} == {1 + vencedores[0] % 5}


def test_avaliacoes_por_periodo_inclusivo_e_cronologico(repos) -> None:
    for jid, dias in (("J3", 2), ("J1", 0), ("J2", 1)):
        repos.avaliacoes.registrar(Avaliacao(jid, 3, "humano", T0 + timedelta(days=dias)))
    ids = lambda ini, fim: [a.jornada_id for a in repos.avaliacoes.listar_periodo(ini, fim)]  # noqa: E731
    assert ids(T0, T0 + timedelta(days=2)) == ["J1", "J2", "J3"]  # extremos inclusivos
    assert ids(T0 + timedelta(hours=1), T0 + timedelta(days=1)) == ["J2"]
    assert ids(T0 + timedelta(days=3), T0 + timedelta(days=4)) == []


# ============================================================================= Agregados


def test_agregados_contam_por_dia_e_metrica(repos) -> None:
    d1, d2, d3 = date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3)
    assert repos.agregados.obter(d1, "ia_cache") == 0
    assert repos.agregados.incrementar(d1, "ia_cache") == 1
    assert repos.agregados.incrementar(d1, "ia_cache", 4) == 5
    repos.agregados.incrementar(d2, "problema_sel#7")
    repos.agregados.incrementar(d3, "ia_cache")
    assert repos.agregados.obter(d1, "ia_cache") == 5 and repos.agregados.obter(d1, "outra") == 0
    assert [(a.dia, a.metrica, a.valor) for a in repos.agregados.listar(d1, d2)] == [
        ("2025-01-01", "ia_cache", 5),
        ("2025-01-02", "problema_sel#7", 1),
    ]
    assert len(repos.agregados.listar(d2, d2)) == 1
    with pytest.raises(ValueError):
        repos.agregados.incrementar(d1, "x", 0)
    with pytest.raises(ValueError):
        repos.agregados.incrementar(d1, "x", -1)


def test_incrementos_concorrentes_de_agregado_sao_atomicos(amb) -> None:
    dia = date(2025, 1, 1)
    n = 20
    novos = em_paralelo(amb, n, lambda r, _: r.agregados.incrementar(dia, "ia_modelo"))
    assert sorted(novos) == list(range(1, n + 1))  # nenhum incremento perdido ou repetido
    assert amb.repos.agregados.obter(dia, "ia_modelo") == n


# ============================================================================= Painel_CS


def test_usuario_unico_e_perfil(repos) -> None:
    u = UsuarioCS("bruno", "hash", "atendente")
    assert repos.usuarios_cs.criar(u).aplicado
    dup = repos.usuarios_cs.criar(UsuarioCS("bruno", "outro", "gestor"))
    assert not dup.aplicado and dup.registro == u
    assert repos.usuarios_cs.obter("bruno") == u and repos.usuarios_cs.obter("ninguem") is None
    assert repos.usuarios_cs.perfil_de("bruno") == "atendente"
    assert repos.usuarios_cs.perfil_de("ninguem") is None
    s = repos.usuarios_cs.definir_senha("bruno", "novo-hash")
    assert (s.hash_senha, s.deve_trocar_senha) == ("novo-hash", False)


def test_falhas_de_login_ficam_so_dentro_da_janela_e_bloqueio(repos) -> None:
    repos.usuarios_cs.criar(UsuarioCS("bruno", "hash", "atendente"))
    janela = timedelta(minutes=15)
    repos.usuarios_cs.registrar_falha("bruno", T0, janela)
    dois = repos.usuarios_cs.registrar_falha("bruno", T0 + timedelta(minutes=10), janela)
    assert dois.falhas == (T0, T0 + timedelta(minutes=10))
    tres = repos.usuarios_cs.registrar_falha("bruno", T0 + timedelta(minutes=20), janela)
    assert tres.falhas == (T0 + timedelta(minutes=10), T0 + timedelta(minutes=20))
    assert repos.usuarios_cs.obter("bruno").falhas == tres.falhas
    ate = T0 + timedelta(minutes=35)
    assert repos.usuarios_cs.bloquear("bruno", ate).bloqueado_ate == ate
    assert repos.usuarios_cs.limpar_falhas("bruno").falhas == ()
    assert repos.usuarios_cs.obter("bruno").bloqueado_ate == ate  # limpar não desbloqueia


def test_falhas_de_login_simultaneas_nao_se_perdem(amb) -> None:
    amb.repos.usuarios_cs.criar(UsuarioCS("bruno", "hash", "atendente"))
    janela = timedelta(minutes=15)
    n = 5
    em_paralelo(
        amb,
        n,
        lambda r, i: r.usuarios_cs.registrar_falha("bruno", T0 + timedelta(seconds=i), janela),
    )
    assert len(amb.repos.usuarios_cs.obter("bruno").falhas) == n


# --------------------------------------------------------------- sessões (Req 13.5)


def test_sessao_renova_dentro_da_janela_e_expira_depois(repos) -> None:
    inatividade = timedelta(minutes=30)
    repos.sessoes.criar(SessaoCS("h1", "bruno", "atendente", T0, int(T0.timestamp())))
    t1 = T0 + timedelta(minutes=30)  # exatamente 30 min sem atividade ainda vale
    s = repos.sessoes.renovar("h1", t1, inatividade)
    assert s.ultima_atividade == t1 and s.ttl == int((t1 + inatividade).timestamp())
    assert repos.sessoes.obter("h1") == s
    # Renovação deslizante: 30 min depois da renovação ainda vale; a janela anda junto.
    t2 = t1 + timedelta(minutes=30)
    assert repos.sessoes.renovar("h1", t2, inatividade).ultima_atividade == t2
    # 30 min e 1 s sem atividade: vencida, removida (sem depender do TTL do DynamoDB).
    assert repos.sessoes.renovar("h1", t2 + timedelta(minutes=30, seconds=1), inatividade) is None
    assert repos.sessoes.obter("h1") is None
    assert repos.sessoes.renovar("h1", t2, inatividade) is None
    assert repos.sessoes.renovar("inexistente", T0, inatividade) is None


def test_renovacao_nao_faz_a_atividade_retroceder(repos) -> None:
    inatividade = timedelta(minutes=30)
    repos.sessoes.criar(SessaoCS("h1", "bruno", "gestor", T0 + timedelta(minutes=10), 0))
    s = repos.sessoes.renovar("h1", T0 + timedelta(minutes=5), inatividade)
    assert s.ultima_atividade == T0 + timedelta(minutes=10)


def test_renovacoes_concorrentes_mantem_a_ultima_atividade_mais_recente(amb) -> None:
    inatividade = timedelta(minutes=30)
    amb.repos.sessoes.criar(SessaoCS("h1", "bruno", "atendente", T0, 0))
    rs = em_paralelo(
        amb,
        4,
        lambda r, i: r.sessoes.renovar("h1", T0 + timedelta(minutes=1 + i), inatividade),
    )
    assert all(s is not None for s in rs)
    assert amb.repos.sessoes.obter("h1").ultima_atividade == T0 + timedelta(minutes=4)


def test_logout_remove_a_sessao(repos) -> None:
    repos.sessoes.criar(SessaoCS("h2", "ana", "gestor", T0, 0))
    assert repos.sessoes.encerrar("h2") is True
    assert repos.sessoes.encerrar("h2") is False
    assert repos.sessoes.obter("h2") is None


# ============================================================================= Config


def test_config_ida_e_volta(repos) -> None:
    repos.config.definir("limite_msgs_modelo", 10)
    repos.config.definir("limiar_relevancia", Decimal("0.5"))
    repos.config.definir("termos_risco", ["fumaça", "choque"])
    assert repos.config.obter("limite_msgs_modelo") == 10
    assert repos.config.obter("limiar_relevancia") == Decimal("0.5")
    assert repos.config.obter("termos_risco") == ["fumaça", "choque"]
    assert repos.config.obter("nada") is None
    assert set(repos.config.listar()) == {"limite_msgs_modelo", "limiar_relevancia", "termos_risco"}


# ====================================================== listar_todos (somente em memória)
# Teste_De_Contrato_Memoria (Req 8.1, 8.3, 8.4, 12.3): `listar_todos` só existe no repositório
# em memória; o adaptador DynamoDB apenas declara o método e levanta erro explícito. Por isso
# estes testes NÃO usam a fixture parametrizada `amb` e não há caso DynamoDB/moto.


@pytest.fixture
def repos_memoria() -> Repositorios:
    return criar_repositorios_memoria()


def test_listar_todos_em_repositorio_vazio_devolve_lista_vazia(repos_memoria) -> None:
    assert repos_memoria.chamados.listar_todos() == []


def test_listar_todos_inclui_todos_os_status_e_listar_fila_so_os_nao_encerrados(
    repos_memoria,
) -> None:
    repos = repos_memoria
    aberto, atendimento, encerrado = numero(1), numero(2), numero(3)
    for i, num in enumerate((aberto, atendimento, encerrado)):
        repos.jornadas.criar(jornada(f"J{i}"))
        assert escalar(repos, f"J{i}", num, em=T0 + timedelta(minutes=i)).criado
    assert repos.chamados.assumir(atendimento, "bruno", "Bruno", T0).aplicado
    assert repos.chamados.encerrar(encerrado, encerramento()).aplicado

    todos = repos.chamados.listar_todos()
    assert {c.numero: c.status for c in todos} == {
        aberto: "aberto",
        atendimento: "em_atendimento",
        encerrado: "encerrado",
    }
    assert [c.numero for c in todos] == [aberto, atendimento, encerrado]
    # listar_fila continua devolvendo só os não encerrados.
    assert {c.numero for c in repos.chamados.listar_fila()} == {aberto, atendimento}
    # Os registros devolvidos são os mesmos de `obter`.
    assert all(c == repos.chamados.obter(c.numero) for c in todos)


def test_listar_todos_ordena_por_criado_em_e_depois_por_numero(repos_memoria) -> None:
    repos = repos_memoria
    casos = [  # (número, prioridade, minuto); inserção fora de ordem e com empate de horário
        (numero(3), "P1", 2),
        (numero(2), "P3", 0),
        (numero(4), "P2", 1),
        (numero(1), "P2", 0),  # empata o horário com numero(2): desempata pelo número
    ]
    for i, (num, prioridade, minutos) in enumerate(casos):
        repos.jornadas.criar(jornada(f"J{i}"))
        escalar(repos, f"J{i}", num, prioridade, T0 + timedelta(minutes=minutos))
    # A prioridade não interfere na ordem (diferente da fila).
    assert [c.numero for c in repos.chamados.listar_todos()] == [
        numero(1),
        numero(2),
        numero(4),
        numero(3),
    ]
    assert repos.chamados.listar_todos() == repos.chamados.listar_todos()


def test_listar_todos_devolve_lista_independente_do_armazenamento(repos_memoria) -> None:
    num = com_chamado(repos_memoria)
    resultado = repos_memoria.chamados.listar_todos()
    resultado.clear()
    assert [c.numero for c in repos_memoria.chamados.listar_todos()] == [num]
