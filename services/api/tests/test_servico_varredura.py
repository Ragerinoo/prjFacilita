"""Testes da varredura de abandono (tarefa 20.1; Req 17.2).
As regras de negócio rodam nos dois repositórios (fake em memória e DynamoDB sob `moto`, com
as tabelas e os índices de `infra/stacks/dados_stack.py`), para exercitar o `gsi_ativas` de
verdade. Cobrem: limite de 30 min, Chamado, interação e escalada concorrentes, reexecução,
isolamento de falhas por item, orçamento de tempo, resumo, custo/problema e o handler.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import boto3
import pytest
from hypothesis import given
from hypothesis import strategies as st
from moto import mock_aws

from dominio import ItemJaTentado, PacoteRepasse
from handlers import varredura as handler
from repositorios import ErroNaoEncontrado, ErroRepositorio, criar_repositorios_memoria
from repositorios.dynamodb import config_cliente_curta, criar_repositorios_dynamodb
from repositorios.modelos import Chamado, DecisaoRegistrada, GatilhoRegistrado, Jornada
from servicos.varredura import (
    INTERROMPIDA_LIMITE,
    INTERROMPIDA_TEMPO,
    MARGEM_S,
    varrer_abandonadas,
)

T0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
TRINTA_MIN = timedelta(minutes=30)
PREFIXO = "tres"
# ------------------------------------------------------------------------------- fábricas
def jornada(jid: str, ultima: datetime = T0, **campos) -> Jornada:
    return Jornada(
        jornada_id=jid,
        criada_em=T0 - timedelta(minutes=10),
        ultima_interacao=ultima,
        origem="qr",
        origem_inicial="qr",
        **campos,
    )
def escalar(repos, jid: str, numero: str = "TRES-AAAAAAAAAA") -> None:
    pacote = PacoteRepasse(
        numero_chamado=numero,
        modelo="Máquina Café — Modelo X",
        numero_serie="não informado",
        origem="qr",
        categoria="nao_liga",
        resumo="Resumo indisponível — ver histórico da Jornada",
        ja_tentado=(ItemJaTentado("Problema 1, passo 2", "guia", "não"),),
        classificacao="provável uso",
        prioridade="P3",
        canal_recomendado="chat assíncrono",
        sentimento="neutro",
        anexos=(),
        proxima_acao="Revisar o histórico da Jornada",
    )
    chamado = Chamado(
        numero=numero,
        jornada_id=jid,
        criado_em=T0,
        prioridade="P3",
        classificacao="provável uso",
        canal="chat assíncrono",
        decisao_criterio=3,
        pacote=pacote,
    )
    resultado = repos.chamados.criar_com_escalada(
        chamado,
        GatilhoRegistrado("pedido_humano", T0),
        DecisaoRegistrada("P3", "provável uso", "chat assíncrono", 3, T0),
    )
    assert resultado.criado
# Tabelas usadas pela varredura e pela criação de Chamado (espelha dados_stack.py).
_TABELAS = [
    ("jornadas", "jornada_id", None, [("gsi_ativas", "ativa_pk", "ultima_interacao")]),
    ("chamados", "numero", None, [("gsi_fila", "fila_pk", "fila_sk")]),
    ("mensagens_chamado", "numero", "ts_ulid", []),
    ("eventos", "jornada_id", "ts_ulid", []),
]
def _criar_tabelas(recurso, prefixo: str = PREFIXO) -> None:
    for nome, pk, sk, indices in _TABELAS:
        atributos = {pk, *([sk] if sk else [])}
        for _, ipk, isk in indices:
            atributos |= {ipk, isk}
        args = {
            "TableName": f"{prefixo}-{nome}",
            "KeySchema": [{"AttributeName": pk, "KeyType": "HASH"}]
            + ([{"AttributeName": sk, "KeyType": "RANGE"}] if sk else []),
            "AttributeDefinitions": [
                {"AttributeName": a, "AttributeType": "S"} for a in sorted(atributos)
            ],
            "BillingMode": "PAY_PER_REQUEST",
        }
        if indices:
            args["GlobalSecondaryIndexes"] = [
                {
                    "IndexName": i,
                    "KeySchema": [
                        {"AttributeName": ipk, "KeyType": "HASH"},
                        {"AttributeName": isk, "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
                for i, ipk, isk in indices
            ]
        recurso.create_table(**args)
@pytest.fixture
def ambiente_aws(monkeypatch):
    for chave in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(chave, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        yield
@pytest.fixture(params=["memoria", "dynamodb"])
def repos(request, ambiente_aws):
    if request.param == "memoria":
        yield criar_repositorios_memoria()
        return
    recurso = boto3.resource("dynamodb", region_name="us-east-1", config=config_cliente_curta())
    _criar_tabelas(recurso)
    yield criar_repositorios_dynamodb(recurso, PREFIXO)
class ComGancho:
    """Repositório que dispara `gancho(jornadas_listadas)` logo depois da listagem.
    Simula o que acontece entre a listagem do `gsi_ativas` e a gravação do abandono."""
    def __init__(self, real, gancho) -> None:
        self._real = real
        self._gancho = gancho
    def listar_ativas_sem_interacao_ate(self, limite):
        listadas = self._real.listar_ativas_sem_interacao_ate(limite)
        self._gancho(listadas)
        return listadas
    def __getattr__(self, nome):
        return getattr(self._real, nome)
class ComFalhas:
    """Repositório cujo `marcar_abandono` falha para certos ids (erro por item)."""
    def __init__(self, real, falhas: dict[str, Exception]) -> None:
        self._real = real
        self._falhas = falhas
        self.chamadas: list[str] = []
    def marcar_abandono(self, jornada_id, agora, custo_brl=Decimal("0")):
        self.chamadas.append(jornada_id)
        if jornada_id in self._falhas:
            raise self._falhas[jornada_id]
        return self._real.marcar_abandono(jornada_id, agora, custo_brl)
    def __getattr__(self, nome):
        return getattr(self._real, nome)
def camada(repos, jid: str) -> str | None:
    enc = repos.jornadas.obter(jid).encerramento
    return enc.camada if enc else None
# ------------------------------------------------------------------------------- limite
def test_jornada_com_exatamente_30_min_e_abandonada(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    resumo = varrer_abandonadas(repos.jornadas, T0 + TRINTA_MIN)
    assert resumo["abandonadas"] == 1
    j = repos.jornadas.obter("J1")
    assert j.estado == "encerrada" and j.encerramento.camada == "abandonada"
    # Tempo vai do início até a última interação (Req 17.1); o horário é o da varredura.
    assert j.encerramento.tempo_s == 600
    assert j.encerramento.encerrada_em == T0 + TRINTA_MIN
def test_jornada_com_29_min_59_s_nao_e_abandonada(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    resumo = varrer_abandonadas(repos.jornadas, T0 + TRINTA_MIN - timedelta(seconds=1))
    assert resumo["candidatas"] == 0 and resumo["abandonadas"] == 0
    assert repos.jornadas.obter("J1").estado == "ativa"
def test_jornada_com_chamado_nao_e_abandonada(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    repos.jornadas.criar(jornada("J2"))
    escalar(repos, "J2")
    resumo = varrer_abandonadas(repos.jornadas, T0 + timedelta(hours=2))
    assert (resumo["candidatas"], resumo["abandonadas"]) == (1, 1)
    assert camada(repos, "J1") == "abandonada"
    j2 = repos.jornadas.obter("J2")
    assert j2.estado == "escalada" and j2.encerramento is None
def test_escalada_concorrente_cancela_o_abandono(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    # A Jornada é listada, e só então o Consumidor pede atendimento (gsi_ativas ainda a mostra).
    sob_teste = ComGancho(repos.jornadas, lambda _: escalar(repos, "J1"))
    resumo = varrer_abandonadas(sob_teste, T0 + timedelta(hours=1))
    assert (resumo["candidatas"], resumo["abandonadas"], resumo["ignoradas"]) == (1, 0, 1)
    assert repos.jornadas.obter("J1").estado == "escalada"
def test_interacao_concorrente_cancela_o_abandono(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    agora = T0 + timedelta(hours=1)
    sob_teste = ComGancho(
        repos.jornadas,
        lambda _: repos.jornadas.registrar_interacao("J1", agora - timedelta(minutes=1)),
    )
    resumo = varrer_abandonadas(sob_teste, agora)
    assert (resumo["abandonadas"], resumo["ignoradas"], resumo["falhas"]) == (0, 1, 0)
    j = repos.jornadas.obter("J1")
    assert j.estado == "ativa" and j.encerramento is None
def test_interacao_depois_do_abandono_nao_altera_a_classificacao(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    agora = T0 + TRINTA_MIN
    varrer_abandonadas(repos.jornadas, agora)
    antes = repos.jornadas.obter("J1")
    repos.jornadas.registrar_interacao("J1", agora + timedelta(minutes=5))
    assert repos.jornadas.obter("J1") == antes  # terminal (Req 17.2)
def test_jornada_ja_encerrada_nao_e_tocada(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    repos.jornadas.encerrar("J1", "guia", T0 + timedelta(minutes=5))
    antes = repos.jornadas.obter("J1")
    resumo = varrer_abandonadas(repos.jornadas, T0 + timedelta(hours=3))
    assert resumo["candidatas"] == 0
    assert repos.jornadas.obter("J1") == antes
def test_encerramento_concorrente_vence_o_abandono(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    sob_teste = ComGancho(
        repos.jornadas, lambda _: repos.jornadas.encerrar("J1", "ia", T0 + timedelta(minutes=29))
    )
    resumo = varrer_abandonadas(sob_teste, T0 + timedelta(hours=1))
    assert (resumo["abandonadas"], resumo["ignoradas"]) == (0, 1)
    assert camada(repos, "J1") == "ia"
# ------------------------------------------------------------------------------- reexecução
def test_reexecucao_e_idempotente(repos) -> None:
    for i in range(3):
        repos.jornadas.criar(jornada(f"J{i}", T0 + timedelta(minutes=i)))
    agora = T0 + timedelta(hours=1)
    primeira = varrer_abandonadas(repos.jornadas, agora)
    fotografia = [repos.jornadas.obter(f"J{i}") for i in range(3)]
    segunda = varrer_abandonadas(repos.jornadas, agora + timedelta(minutes=5))
    assert primeira["abandonadas"] == 3
    assert (segunda["candidatas"], segunda["abandonadas"], segunda["falhas"]) == (0, 0, 0)
    assert [repos.jornadas.obter(f"J{i}") for i in range(3)] == fotografia
def test_duas_execucoes_sobrepostas_marcam_uma_vez(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    agora = T0 + timedelta(hours=1)
    # A outra execução marca a Jornada depois que esta a listou.
    sob_teste = ComGancho(
        repos.jornadas, lambda _: repos.jornadas.marcar_abandono("J1", agora - timedelta(seconds=5))
    )
    resumo = varrer_abandonadas(sob_teste, agora)
    assert (resumo["abandonadas"], resumo["ignoradas"]) == (0, 1)
    enc = repos.jornadas.obter("J1").encerramento
    assert enc.encerrada_em == agora - timedelta(seconds=5)  # a primeira vence
# ------------------------------------------------------------------------------- custo
def test_custo_e_problema_vao_para_o_registro_de_abandono(repos) -> None:
    repos.jornadas.criar(jornada("J1", custo_ia_brl=Decimal("0.0456"), problema_id=4))
    repos.jornadas.criar(jornada("J2"))
    varrer_abandonadas(repos.jornadas, T0 + timedelta(hours=1))
    e1 = repos.jornadas.obter("J1").encerramento
    assert (e1.camada, e1.custo_brl, e1.problema_id) == ("abandonada", Decimal("0.05"), 4)
    e2 = repos.jornadas.obter("J2").encerramento
    assert (e2.custo_brl, e2.problema_id) == (Decimal("0"), None)
def test_custo_por_jornada_pode_ser_substituido(repos) -> None:
    repos.jornadas.criar(jornada("J1", custo_ia_brl=Decimal("1.00")))
    varrer_abandonadas(
        repos.jornadas, T0 + timedelta(hours=1), custo_por_jornada=lambda _: Decimal("0.20")
    )
    assert repos.jornadas.obter("J1").encerramento.custo_brl == Decimal("0.20")
# ------------------------------------------------------------------------------- falhas
def test_falhas_sao_isoladas_por_item_e_contadas(repos) -> None:
    for i in range(5):
        repos.jornadas.criar(jornada(f"J{i}", T0 + timedelta(seconds=i)))
    sob_teste = ComFalhas(
        repos.jornadas,
        {
            "J1": ErroRepositorio("jornadas: timeout"),
            "J2": ErroNaoEncontrado("jornadas", "J2"),
            "J3": RuntimeError("inesperado"),
        },
    )
    resumo = varrer_abandonadas(sob_teste, T0 + timedelta(hours=1))
    assert sob_teste.chamadas == ["J0", "J1", "J2", "J3", "J4"]  # nenhuma falha aborta a rodada
    assert resumo["candidatas"] == 5 and resumo["processadas"] == 5
    assert (resumo["abandonadas"], resumo["ignoradas"], resumo["falhas"]) == (2, 1, 2)
    assert [camada(repos, f"J{i}") for i in range(5)] == [
        "abandonada",
        None,
        None,
        None,
        "abandonada",
    ]
    # As com falha seguem no gsi_ativas e a próxima rodada as conclui.
    proxima = varrer_abandonadas(repos.jornadas, T0 + timedelta(hours=1, minutes=5))
    assert proxima["abandonadas"] == 3
def test_falha_da_listagem_sobe_para_o_agendador() -> None:
    class ListagemQuebrada:
        def listar_ativas_sem_interacao_ate(self, limite):
            raise ErroRepositorio("jornadas: query falhou (ThrottlingException)")
    with pytest.raises(ErroRepositorio):
        varrer_abandonadas(ListagemQuebrada(), T0 + timedelta(hours=1))
# ------------------------------------------------------------------------------- orçamento
def test_para_no_limite_por_execucao_e_a_proxima_rodada_continua(repos) -> None:
    for i in range(5):
        repos.jornadas.criar(jornada(f"J{i}", T0 + timedelta(seconds=i)))
    agora = T0 + timedelta(hours=1)
    primeira = varrer_abandonadas(repos.jornadas, agora, limite_por_execucao=2)
    assert (primeira["processadas"], primeira["abandonadas"]) == (2, 2)
    assert primeira["nao_processadas"] == 3 and primeira["interrompida_por"] == INTERROMPIDA_LIMITE
    assert [camada(repos, f"J{i}") for i in range(5)][:2] == ["abandonada"] * 2  # mais antigas
    segunda = varrer_abandonadas(repos.jornadas, agora, limite_por_execucao=10)
    assert (segunda["candidatas"], segunda["abandonadas"]) == (3, 3)
    assert segunda["interrompida_por"] is None
def test_para_com_margem_de_tempo_antes_de_estourar_a_lambda(repos) -> None:
    for i in range(4):
        repos.jornadas.criar(jornada(f"J{i}", T0 + timedelta(seconds=i)))
    restantes = iter([50.0, 40.0, MARGEM_S - 0.1, 10.0])
    resumo = varrer_abandonadas(
        repos.jornadas, T0 + timedelta(hours=1), restante_s=lambda: next(restantes)
    )
    assert (resumo["processadas"], resumo["abandonadas"]) == (2, 2)
    assert resumo["nao_processadas"] == 2 and resumo["interrompida_por"] == INTERROMPIDA_TEMPO
def test_margem_exata_ainda_processa(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    resumo = varrer_abandonadas(
        repos.jornadas, T0 + timedelta(hours=1), restante_s=lambda: MARGEM_S
    )
    assert resumo["abandonadas"] == 1
def test_margem_cabe_no_timeout_da_lambda() -> None:
    # Timeout da Lambda de varredura (infra/stacks/api_stack.py: VARREDURA_TIMEOUT_S = 60).
    assert 5 <= MARGEM_S < 60 / 2
# ------------------------------------------------------------------------------- resumo
def test_resumo_completo(repos) -> None:
    agora = T0 + timedelta(hours=1)
    repos.jornadas.criar(jornada("A", T0))
    repos.jornadas.criar(jornada("B", T0 + timedelta(minutes=1)))
    repos.jornadas.criar(jornada("RECENTE", agora - timedelta(minutes=5)))
    repos.jornadas.criar(jornada("COM_CHAMADO", T0))
    escalar(repos, "COM_CHAMADO")
    resumo = varrer_abandonadas(repos.jornadas, agora)
    assert resumo == {
        "limite_ate": (agora - TRINTA_MIN).isoformat(),
        "candidatas": 2,
        "processadas": 2,
        "abandonadas": 2,
        "ignoradas": 0,
        "falhas": 0,
        "nao_processadas": 0,
        "interrompida_por": None,
    }
def test_sem_candidatas_devolve_resumo_zerado(repos) -> None:
    resumo = varrer_abandonadas(repos.jornadas, T0)
    assert resumo["candidatas"] == resumo["processadas"] == resumo["abandonadas"] == 0
def test_exige_horario_com_fuso() -> None:
    with pytest.raises(ValueError):
        varrer_abandonadas(criar_repositorios_memoria().jornadas, datetime(2025, 1, 1))
# ------------------------------------------------------------------------------- propriedade
@given(st.lists(st.integers(min_value=0, max_value=7200), min_size=0, max_size=12))
def test_propriedade_abandona_so_quem_passou_de_30_min(ociosidades: list[int]) -> None:
    """Abandonada <=> ociosa há 1800 s ou mais; reexecutar não muda nada.
    **Validates: Requirements 17.2**
    """
    repos = criar_repositorios_memoria()
    agora = T0 + timedelta(hours=3)
    for i, ocio in enumerate(ociosidades):
        repos.jornadas.criar(jornada(f"J{i}", agora - timedelta(seconds=ocio)))
    resumo = varrer_abandonadas(repos.jornadas, agora)
    esperadas = {f"J{i}" for i, ocio in enumerate(ociosidades) if ocio >= 1800}
    marcadas = {f"J{i}" for i in range(len(ociosidades)) if camada(repos, f"J{i}") == "abandonada"}
    assert marcadas == esperadas and resumo["abandonadas"] == len(esperadas)
    assert resumo["falhas"] == 0
    assert varrer_abandonadas(repos.jornadas, agora)["abandonadas"] == 0
# ------------------------------------------------------------------------------- handler
class ContextoLambda:
    def __init__(self, restante_ms: int) -> None:
        self._ms = restante_ms
    def get_remaining_time_in_millis(self) -> int:
        return self._ms
@pytest.fixture
def container_limpo():
    handler.redefinir()
    yield
    handler.redefinir()
def test_handler_modo_local_usa_fakes_em_memoria(monkeypatch, container_limpo) -> None:
    monkeypatch.setenv("TRES_MODO", "local")
    resumo = handler.lambda_handler({"origem": "scheduler"}, ContextoLambda(60_000))
    assert resumo["candidatas"] == 0 and resumo["falhas"] == 0
    assert resumo["interrompida_por"] is None
def test_handler_com_dynamodb_marca_as_antigas_e_respeita_o_prefixo(
    monkeypatch, ambiente_aws, container_limpo
) -> None:
    monkeypatch.delenv("TRES_MODO", raising=False)
    monkeypatch.setenv("TRES_PREFIXO", "demo")
    recurso = boto3.resource("dynamodb", region_name="us-east-1")
    _criar_tabelas(recurso, "demo")
    repos = criar_repositorios_dynamodb(recurso, "demo")
    agora = datetime.now(UTC)
    repos.jornadas.criar(jornada("ANTIGA", agora - timedelta(minutes=45)))
    repos.jornadas.criar(jornada("RECENTE", agora - timedelta(minutes=10)))
    resumo = handler.lambda_handler({"origem": "scheduler"}, ContextoLambda(60_000))
    assert (resumo["candidatas"], resumo["abandonadas"]) == (1, 1)
    assert camada(repos, "ANTIGA") == "abandonada" and camada(repos, "RECENTE") is None
def test_handler_sem_tempo_suficiente_nao_processa_e_sinaliza(
    monkeypatch, container_limpo
) -> None:
    monkeypatch.setenv("TRES_MODO", "local")
    repos = criar_repositorios_memoria()
    repos.jornadas.criar(jornada("J1", datetime.now(UTC) - timedelta(hours=1)))
    handler._jornadas = repos.jornadas
    resumo = handler.lambda_handler({}, ContextoLambda(int((MARGEM_S - 1) * 1000)))
    assert resumo["processadas"] == 0 and resumo["interrompida_por"] == INTERROMPIDA_TEMPO
    assert repos.jornadas.obter("J1").estado == "ativa"
def test_handler_propaga_falha_da_listagem(monkeypatch, container_limpo) -> None:
    class Quebrado:
        def listar_ativas_sem_interacao_ate(self, limite):
            raise ErroRepositorio("jornadas: indisponível")
    handler._jornadas = Quebrado()
    with pytest.raises(ErroRepositorio):
        handler.lambda_handler({}, ContextoLambda(60_000))
