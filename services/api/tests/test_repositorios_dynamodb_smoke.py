"""Testes de fumaça dos adaptadores DynamoDB contra `moto` (tarefa 9.2).

Exercitam as escritas condicionais e os índices esparsos de cada adaptador. A bateria de
contrato completa (mesmos testes no fake em memória e no DynamoDB) é a tarefa 9.3.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from dominio import EntradaCache, ItemJaTentado, PacoteRepasse, StatusInsercao, chave_cache
from repositorios import ErroNaoEncontrado, ErroRepositorio, Repositorios
from repositorios.dynamodb import (
    ORCAMENTO_GRAVACAO_S,
    config_cliente_curta,
    config_cliente_leitura_cache,
    criar_repositorios_dynamodb,
    pior_caso_chamada_s,
)
from repositorios.dynamodb._base import Tabela, de_dynamo, dt_str, para_dynamo
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

T0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
PREFIXO = "tres"

# (nome, pk, sk, [(indice, pk, sk)]): espelha infra/stacks/dados_stack.py.
TABELAS = [
    (
        "jornadas",
        "jornada_id",
        None,
        [
            ("gsi_ativas", "ativa_pk", "ultima_interacao"),
            ("gsi_encerradas", "encerrada_pk", "encerrada_em"),
        ],
    ),
    ("eventos", "jornada_id", "ts_ulid", []),
    ("chamados", "numero", None, [("gsi_fila", "fila_pk", "fila_sk")]),
    ("mensagens_chamado", "numero", "ts_ulid", []),
    ("dados_pessoais", "numero", None, []),
    ("acessos_pii", "numero", "ts_ulid", []),
    ("ordens_servico", "os_id", None, []),
    ("cache_respostas", "chave", None, []),
    ("avaliacoes", "jornada_id", None, []),
    ("agregados_dia", "dia", "metrica", []),
    ("usuarios_cs", "usuario", None, []),
    ("sessoes_cs", "token_hash", None, []),
    ("config", "chave", None, []),
]


def _criar_tabelas(recurso) -> None:
    for nome, pk, sk, indices in TABELAS:
        atributos = {pk, *([sk] if sk else [])}
        for _, ipk, isk in indices:
            atributos |= {ipk, isk}
        args = {
            "TableName": f"{PREFIXO}-{nome}",
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
def recurso(monkeypatch):
    for chave in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(chave, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        r = boto3.resource("dynamodb", region_name="us-east-1", config=config_cliente_curta())
        _criar_tabelas(r)
        yield r


@pytest.fixture
def repos(recurso) -> Repositorios:
    return criar_repositorios_dynamodb(recurso, PREFIXO)


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


# ----------------------------------------------------------------------------- timeouts


def test_orcamento_de_timeout_respeita_o_limite_de_gravacao() -> None:
    cfg = config_cliente_curta()
    assert cfg.connect_timeout + cfg.read_timeout < ORCAMENTO_GRAVACAO_S
    assert cfg.retries["total_max_attempts"] <= 2
    assert pior_caso_chamada_s() < ORCAMENTO_GRAVACAO_S
    cache = config_cliente_leitura_cache()
    assert cache.connect_timeout + cache.read_timeout <= 2.0


def test_falha_de_infraestrutura_vira_erro_de_repositorio(recurso) -> None:
    repos = criar_repositorios_dynamodb(recurso, "prefixo-sem-tabelas")
    with pytest.raises(ErroRepositorio):
        repos.jornadas.criar(jornada())
    with pytest.raises(ErroRepositorio):
        repos.acessos_pii.registrar("TRES-X", "bruno", T0)  # Req 18.9: sem log, sem dados


# ----------------------------------------------------------------------------- conversões


def test_conversao_de_numeros_ida_e_volta() -> None:
    valor = {"a": 1, "b": 0.5, "c": [1, 2.25, None, True], "d": ("x",)}
    assert de_dynamo(para_dynamo(valor)) == {
        "a": 1,
        "b": 0.5,
        "c": [1, 2.25, None, True],
        "d": ["x"],
    }
    assert de_dynamo(Decimal("0.0123"), fracionario_como_float=False) == Decimal("0.0123")
    with pytest.raises(ValueError):
        dt_str(datetime(2025, 1, 1))  # sem fuso


# ----------------------------------------------------------------------------- Jornadas


def test_jornada_ida_e_volta_e_criacao_condicional(repos) -> None:
    j = jornada()
    assert repos.jornadas.criar(j).aplicado
    assert repos.jornadas.obter("J1") == j
    outra = repos.jornadas.criar(Jornada("J1", T0, T0, "busca", "busca"))
    assert not outra.aplicado and outra.registro.origem == "qr"
    assert repos.jornadas.obter("nada") is None
    with pytest.raises(ErroNaoEncontrado):
        repos.jornadas.marcar_guia_respondeu_nao("nada")


def test_jornada_mutacoes_simples(repos) -> None:
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
    assert repos.jornadas.atualizar_frustracao("J1", "alta").frustracao_alta_seq == 1
    assert repos.jornadas.atualizar_frustracao("J1", "alta").frustracao_alta_seq == 2
    assert repos.jornadas.atualizar_frustracao("J1", "baixa").frustracao_alta_seq == 0
    j = repos.jornadas.somar_custo_ia("J1", Decimal("0.0123"))
    j = repos.jornadas.somar_custo_ia("J1", Decimal("0.0002"))
    assert j.custo_ia_brl == Decimal("0.0125")
    with pytest.raises(ValueError):
        repos.jornadas.somar_custo_ia("J1", Decimal("-1"))


def test_problema_selecionado_so_conta_na_primeira_vez(repos) -> None:
    repos.jornadas.criar(jornada())
    assert repos.jornadas.registrar_problema_selecionado("J1", 7) is True
    assert repos.jornadas.registrar_problema_selecionado("J1", 7) is False
    assert repos.jornadas.registrar_problema_selecionado("J1", 3) is True
    j = repos.jornadas.obter("J1")
    assert j.problema_id == 3 and j.problemas_selecionados == (7, 3)


def test_interacao_nao_retrocede_nem_altera_jornada_encerrada(repos) -> None:
    repos.jornadas.criar(jornada())
    t1 = T0 + timedelta(minutes=5)
    assert repos.jornadas.registrar_interacao("J1", t1).ultima_interacao == t1
    assert repos.jornadas.registrar_interacao("J1", T0).ultima_interacao == t1
    repos.jornadas.encerrar("J1", "guia", t1)
    assert repos.jornadas.registrar_interacao("J1", t1 + timedelta(hours=1)).ultima_interacao == t1


def test_risco_e_monotonico(repos) -> None:
    repos.jornadas.criar(jornada())
    primeira = repos.jornadas.marcar_risco("J1", "lista", T0)
    segunda = repos.jornadas.marcar_risco("J1", "ia", T0 + timedelta(minutes=1))
    assert primeira.aplicado and not segunda.aplicado
    assert segunda.registro.risco.origem == "lista" and segunda.registro.risco.em == T0


def test_limite_de_chamadas_ao_modelo(repos) -> None:
    repos.jornadas.criar(jornada())
    resultados = [repos.jornadas.incrementar_msgs_modelo("J1", 10) for _ in range(11)]
    assert [r.aplicado for r in resultados] == [True] * 10 + [False]
    assert repos.jornadas.obter("J1").msgs_modelo == 10


def test_encerramento_unico_e_indices_esparsos(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    repos.jornadas.criar(jornada("J2"))
    fim = T0 + timedelta(minutes=10)
    assert [j.jornada_id for j in repos.jornadas.listar_ativas_sem_interacao_ate(fim)] == [
        "J1",
        "J2",
    ]

    primeiro = repos.jornadas.encerrar("J1", "ia", fim, Decimal("0.0456"), problema_id=4)
    segundo = repos.jornadas.encerrar("J1", "guia", fim + timedelta(minutes=1))
    assert primeiro.aplicado and not segundo.aplicado
    enc = repos.jornadas.obter("J1").encerramento
    assert (enc.camada, enc.tempo_s, enc.custo_brl, enc.problema_id) == (
        "ia",
        600,
        Decimal("0.05"),
        4,
    )
    # ativa_pk sai; encerrada_pk/encerrada_em entram.
    assert [j.jornada_id for j in repos.jornadas.listar_ativas_sem_interacao_ate(fim)] == ["J2"]
    assert [j.jornada_id for j in repos.jornadas.listar_encerradas(T0, fim)] == ["J1"]
    assert (
        repos.jornadas.listar_encerradas(fim + timedelta(seconds=1), fim + timedelta(hours=1)) == []
    )
    with pytest.raises(ErroNaoEncontrado):
        repos.jornadas.encerrar("nada", "guia", fim)


def test_abandono_so_apos_30_min_sem_chamado_e_e_terminal(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    repos.jornadas.criar(jornada("J2"))
    escalar(repos, "J2", numero(2))
    tarde = T0 + timedelta(minutes=31)
    assert not repos.jornadas.marcar_abandono("J1", T0 + timedelta(minutes=29)).aplicado
    assert not repos.jornadas.marcar_abandono("J2", tarde).aplicado  # tem Chamado
    assert repos.jornadas.marcar_abandono("J1", tarde).aplicado
    assert not repos.jornadas.marcar_abandono("J1", tarde + timedelta(hours=1)).aplicado
    j = repos.jornadas.obter("J1")
    assert j.estado == "encerrada" and j.encerramento.camada == "abandonada"
    assert repos.jornadas.listar_ativas_sem_interacao_ate(tarde) == []


# ----------------------------------------------------------------------------- Chamados


def test_um_chamado_por_jornada_na_transacao(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    assert escalar(repos, "J1", numero(1), "P2").criado
    j = repos.jornadas.obter("J1")
    assert j.estado == "escalada" and j.escalada.chamado_numero == numero(1)
    assert j.ativa_pk is None and repos.jornadas.listar_ativas_sem_interacao_ate(T0) == []

    segunda = escalar(repos, "J1", numero(2))
    assert (segunda.criado, segunda.motivo, segunda.numero_existente) == (
        False,
        "jornada_ja_escalada",
        numero(1),
    )
    assert repos.chamados.obter(numero(2)) is None  # nada gravado
    assert escalar(repos, "NADA", numero(3)).motivo == "jornada_inexistente"
    assert repos.chamados.obter(numero(3)) is None


def test_numero_em_uso_nao_marca_a_jornada(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    repos.jornadas.criar(jornada("J2"))
    escalar(repos, "J1", numero(1))
    r = escalar(repos, "J2", numero(1))
    assert (r.criado, r.motivo) == (False, "numero_em_uso")
    assert repos.jornadas.obter("J2").escalada is None
    assert repos.jornadas.obter("J2").estado == "ativa"


def test_jornada_encerrada_ganha_o_chamado_sem_mudar_a_camada(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    repos.jornadas.encerrar("J1", "guia", T0 + timedelta(minutes=1))
    assert escalar(repos, "J1", numero(1)).criado
    j = repos.jornadas.obter("J1")
    assert j.estado == "encerrada" and j.encerramento.camada == "guia"
    assert j.escalada.chamado_numero == numero(1)
    assert [
        x.jornada_id for x in repos.jornadas.listar_encerradas(T0, T0 + timedelta(hours=1))
    ] == ["J1"]


def test_chamado_ida_e_volta_com_acentos_e_pacote(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    escalar(repos, "J1", numero(1))
    c = repos.chamados.obter(numero(1))
    assert c == chamado(numero(1))
    assert c.pacote.modelo == "Máquina Café — Modelo X"
    assert c.pacote.ja_tentado == (ItemJaTentado("Problema 1, passo 2", "guia", "não"),)


def test_pacote_invalido_e_status_invalido_nao_gravam(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    with pytest.raises(ErroRepositorio):  # número fora do padrão do esquema
        repos.chamados.criar_com_escalada(chamado("TRES-curto", "J1"), gatilho(), decisao("P3"))
    ja_encerrado = replace(chamado(numero(1)), status="encerrado")
    with pytest.raises(ErroRepositorio):  # Chamado novo deve nascer "aberto"
        repos.chamados.criar_com_escalada(ja_encerrado, gatilho(), decisao("P3"))
    assert repos.jornadas.obter("J1").escalada is None
    assert repos.chamados.obter("TRES-curto") is None


def test_fila_ordena_por_prioridade_horario_e_numero(repos) -> None:
    for i, (prio, minuto) in enumerate([("P3", 0), ("P1", 5), ("P2", 1), ("P1", 2)], start=1):
        repos.jornadas.criar(jornada(f"J{i}"))
        escalar(repos, f"J{i}", numero(i), prio, T0 + timedelta(minutes=minuto))
    assert [c.numero for c in repos.chamados.listar_fila()] == [
        numero(4),
        numero(2),
        numero(3),
        numero(1),
    ]


def test_assumir_tem_um_so_responsavel(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    escalar(repos, "J1", numero(1))
    a = repos.chamados.assumir(numero(1), "bruno", "Bruno", T0)
    b = repos.chamados.assumir(numero(1), "ana", "Ana", T0 + timedelta(seconds=1))
    assert a.aplicado and not b.aplicado
    assert b.registro.responsavel.usuario == "bruno" and b.registro.status == "em_atendimento"
    with pytest.raises(ErroNaoEncontrado):
        repos.chamados.assumir("TRES-NADA", "ana", "Ana", T0)


def test_encerrar_chamado_uma_vez_e_sai_da_fila(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    escalar(repos, "J1", numero(1))
    enc = EncerramentoChamado(
        "falso_defeito", "instrução do manual", "Limpou o filtro", T0, "bruno"
    )
    assert [c.numero for c in repos.chamados.listar_fila()] == [numero(1)]
    assert repos.chamados.encerrar(numero(1), enc).aplicado
    depois = repos.chamados.encerrar(
        numero(1), EncerramentoChamado("defeito_real", "outra", "x", T0, "ana")
    )
    assert not depois.aplicado and depois.registro.encerramento == enc
    assert repos.chamados.listar_fila() == []
    c = repos.chamados.obter(numero(1))
    assert c.status == "encerrado" and c.fila_pk is None
    assert not repos.chamados.assumir(numero(1), "ana", "Ana", T0).aplicado


def test_reavaliar_so_eleva_a_prioridade_e_atualiza_a_jornada(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    escalar(repos, "J1", numero(1), "P3")
    repos.jornadas.criar(jornada("J2"))
    escalar(repos, "J2", numero(2), "P2", T0 + timedelta(minutes=1))

    eleva = repos.chamados.reavaliar(
        numero(1), decisao("P1", T0 + timedelta(minutes=2)), pacote(numero(1), "P1")
    )
    assert eleva.aplicado and eleva.registro.prioridade == "P1"
    assert eleva.registro.pacote.prioridade == "P1"
    assert [c.numero for c in repos.chamados.listar_fila()] == [numero(1), numero(2)]
    assert repos.jornadas.obter("J1").escalada.decisao.prioridade == "P1"

    # A prioridade nunca diminui.
    baixa = repos.chamados.reavaliar(numero(1), decisao("P2"), pacote(numero(1), "P2"))
    igual = repos.chamados.reavaliar(numero(1), decisao("P1"), pacote(numero(1), "P1"))
    assert not baixa.aplicado and not igual.aplicado
    assert repos.chamados.obter(numero(1)).prioridade == "P1"
    with pytest.raises(ErroRepositorio):
        repos.chamados.reavaliar(numero(1), decisao("P1"), pacote(numero(9), "P1"))


def test_campos_de_ia_e_anexos(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    escalar(repos, "J1", numero(1))
    c = repos.chamados.atualizar_campos_ia(
        numero(1), "Cliente sem café.", "frustração moderada", "Ligar hoje.", "ok"
    )
    assert (c.pacote.resumo, c.pacote.sentimento, c.pacote_ia_status) == (
        "Cliente sem café.",
        "frustração moderada",
        "ok",
    )
    assert c.pacote.prioridade == "P3" and c.pacote.modelo == "Máquina Café — Modelo X"
    with pytest.raises(ErroRepositorio):
        repos.chamados.atualizar_campos_ia(numero(1), "", "neutro", "x", "ok")  # resumo vazio
    assert repos.chamados.obter(numero(1)).pacote.resumo == "Cliente sem café."

    resultados = [
        repos.chamados.adicionar_anexo(numero(1), AnexoChamado(f"fotos/{i}.jpg", "image/jpeg", 10))
        for i in range(4)
    ]
    assert [r.aplicado for r in resultados] == [True, True, True, False]
    final = repos.chamados.obter(numero(1))
    assert len(final.anexos) == 3 and len(final.pacote.anexos) == 3


def test_flags_agendamento_e_alerta(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    escalar(repos, "J1", numero(1), "P1")
    brasilia = datetime(2025, 1, 2, 14, 0, tzinfo=timezone(timedelta(hours=-3)))
    c = repos.chamados.definir_agendamento(numero(1), brasilia)
    assert c.agendamento == brasilia and c.agendamento.utcoffset() == brasilia.utcoffset()
    assert repos.chamados.marcar_alerta_p1_visto(numero(1)).alerta_p1_visto
    assert repos.chamados.definir_resposta_nao_lida(numero(1), True).resposta_nao_lida
    assert repos.chamados.definir_os_status(numero(1), "ok").os_status == "ok"


def test_gatilho_adicional_exige_escalada(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    assert not repos.jornadas.registrar_gatilho_adicional("J1", gatilho()).aplicado
    escalar(repos, "J1", numero(1))
    r = repos.jornadas.registrar_gatilho_adicional(
        "J1", GatilhoRegistrado("risco_seguranca", T0, False)
    )
    assert r.aplicado
    assert [(g.tipo, g.registrado) for g in r.registro.escalada.gatilhos] == [
        ("pedido_humano", True),
        ("risco_seguranca", False),
    ]


# ----------------------------------------------------------------------------- demais tabelas


def test_evento_repetido_nao_duplica(repos) -> None:
    primeiro = Evento("J1", novo_ulid(T0), "problema_selecionado", T0, {"problema_id": 7, "x": 0.5})
    repetido = Evento("J1", primeiro.evento_id, "outro", T0, {})
    assert repos.eventos.registrar(primeiro) and not repos.eventos.registrar(repetido)
    posterior = Evento("J1", novo_ulid(T0 + timedelta(seconds=1)), "passo", T0, {})
    repos.eventos.registrar(posterior)
    assert repos.eventos.listar("J1") == [primeiro, posterior]


def test_mensagens_e_leitura(repos) -> None:
    m1 = repos.mensagens.adicionar("N1", "consumidor", "oi", T0)
    m2 = repos.mensagens.adicionar("N1", "atendente", "olá", T0)
    m3 = repos.mensagens.adicionar("N1", "consumidor", "obrigado", T0)
    assert [m.ts_ulid for m in repos.mensagens.listar("N1")] == [m1.ts_ulid, m2.ts_ulid, m3.ts_ulid]
    assert repos.mensagens.marcar_lidas("N1", "consumidor") == 2
    assert repos.mensagens.marcar_lidas("N1", "consumidor") == 0
    lidas = {m.autor: m.lida for m in repos.mensagens.listar("N1")}
    assert lidas == {"consumidor": True, "atendente": False}


def test_dados_pessoais_preservam_o_que_ja_existe_e_acesso_e_registrado(repos) -> None:
    c1 = Consentimento(T0, "v1")
    repos.dados_pessoais.salvar("N1", c1, telefone="11999990000")
    d = repos.dados_pessoais.salvar("N1", Consentimento(T0, "v2"), cep="01001000")
    assert (d.telefone, d.cep, d.consentimento.versao_finalidade) == (
        "11999990000",
        "01001000",
        "v2",
    )
    assert repos.dados_pessoais.obter("N1") == d and repos.dados_pessoais.obter("N2") is None

    acesso = repos.acessos_pii.registrar("N1", "bruno", T0 + timedelta(microseconds=900))
    assert acesso.em == T0 and repos.acessos_pii.listar("N1") == [acesso]


def test_ordem_servico_unica_por_chamado(repos) -> None:
    os1 = OrdemServico(
        numero(1), "Modelo X", "S1", "nao_liga", (ItemJaTentado("p", "guia", "não"),)
    )
    assert repos.ordens_servico.criar_rascunho(os1).aplicado
    dup = repos.ordens_servico.criar_rascunho(OrdemServico(numero(1), "Outro", "S2", "x"))
    assert not dup.aplicado and dup.registro == os1
    assert repos.ordens_servico.obter(numero(1)) == os1
    assert os1.os_id == f"OS#{numero(1)}"
    assert repos.ordens_servico.confirmar(numero(1)).aplicado
    assert not repos.ordens_servico.confirmar(numero(1)).aplicado
    with pytest.raises(ErroNaoEncontrado):
        repos.ordens_servico.confirmar(numero(2))


def test_cache_so_com_aprovador_e_sem_duplicar(repos) -> None:
    entrada = EntradaCache("tres-x", "Como limpo o filtro?", "Retire e lave.", "bruno", T0)
    chave = chave_cache("tres-x", "como limpo o filtro")
    sem = repos.cache.inserir(EntradaCache("tres-x", "Outra?", "r", None, None))
    assert sem.status is StatusInsercao.REJEITADA_SEM_APROVADOR
    assert repos.cache.obter(chave_cache("tres-x", "Outra?")) is None

    assert repos.cache.inserir(entrada, fontes=[{"manual": "m.pdf", "pontuacao": 0.8}]).aceita
    dup = repos.cache.inserir(EntradaCache("tres-x", "como limpo o FILTRO", "outra", "ana", T0))
    assert dup.status is StatusInsercao.DUPLICADA and dup.entrada.resposta == "Retire e lave."
    r = repos.cache.obter(chave)
    assert (r.resposta, r.aprovador_id, r.aprovado_em, r.fontes) == (
        "Retire e lave.",
        "bruno",
        T0,
        ({"manual": "m.pdf", "pontuacao": 0.8},),
    )
    assert repos.cache.registrar_hit(chave) == 1 and repos.cache.registrar_hit(chave) == 2
    with pytest.raises(ErroNaoEncontrado):
        repos.cache.registrar_hit("tres-x#nada")


def test_uma_avaliacao_por_jornada_e_listagem_por_periodo(repos) -> None:
    a1 = Avaliacao("J1", 5, "guia", T0, "ótimo")
    assert repos.avaliacoes.registrar(a1).aplicado
    segunda = repos.avaliacoes.registrar(Avaliacao("J1", 1, "ia", T0))
    assert not segunda.aplicado and segunda.registro == a1
    repos.avaliacoes.registrar(Avaliacao("J2", 3, "humano", T0 + timedelta(days=2)))
    assert repos.avaliacoes.obter("J1") == a1
    assert repos.avaliacoes.listar_periodo(T0, T0 + timedelta(hours=1)) == [a1]
    assert len(repos.avaliacoes.listar_periodo(T0, T0 + timedelta(days=3))) == 2


def test_agregados_atomicos(repos) -> None:
    d1, d2 = date(2025, 1, 1), date(2025, 1, 2)
    assert repos.agregados.obter(d1, "ia_cache") == 0
    assert repos.agregados.incrementar(d1, "ia_cache") == 1
    assert repos.agregados.incrementar(d1, "ia_cache", 4) == 5
    repos.agregados.incrementar(d2, "problema_sel#7")
    assert repos.agregados.obter(d1, "ia_cache") == 5
    assert [(a.dia, a.metrica, a.valor) for a in repos.agregados.listar(d1, d2)] == [
        ("2025-01-01", "ia_cache", 5),
        ("2025-01-02", "problema_sel#7", 1),
    ]
    with pytest.raises(ValueError):
        repos.agregados.incrementar(d1, "x", 0)


def test_usuarios_cs_e_falhas_de_login(repos) -> None:
    u = UsuarioCS("bruno", "hash", "atendente")
    assert repos.usuarios_cs.criar(u).aplicado
    assert not repos.usuarios_cs.criar(UsuarioCS("bruno", "outro", "gestor")).aplicado
    assert (
        repos.usuarios_cs.obter("bruno") == u
        and repos.usuarios_cs.perfil_de("bruno") == "atendente"
    )
    assert repos.usuarios_cs.perfil_de("ninguem") is None
    janela = timedelta(minutes=15)
    repos.usuarios_cs.registrar_falha("bruno", T0, janela)
    repos.usuarios_cs.registrar_falha("bruno", T0 + timedelta(minutes=10), janela)
    falhas = repos.usuarios_cs.registrar_falha("bruno", T0 + timedelta(minutes=20), janela).falhas
    assert falhas == (T0 + timedelta(minutes=10), T0 + timedelta(minutes=20))
    assert repos.usuarios_cs.bloquear("bruno", T0 + timedelta(hours=1)).bloqueado_ate is not None
    assert repos.usuarios_cs.limpar_falhas("bruno").falhas == ()
    s = repos.usuarios_cs.definir_senha("bruno", "novo-hash")
    assert (s.hash_senha, s.deve_trocar_senha) == ("novo-hash", False)
    with pytest.raises(ErroNaoEncontrado):
        repos.usuarios_cs.registrar_falha("ninguem", T0, janela)


def test_sessao_renova_dentro_da_janela_e_expira_depois(repos) -> None:
    inatividade = timedelta(minutes=30)
    repos.sessoes.criar(SessaoCS("h1", "bruno", "atendente", T0, int(T0.timestamp())))
    t1 = T0 + timedelta(minutes=20)
    s = repos.sessoes.renovar("h1", t1, inatividade)
    assert s.ultima_atividade == t1 and s.ttl == int((t1 + inatividade).timestamp())
    assert repos.sessoes.obter("h1") == s
    assert repos.sessoes.renovar("h1", t1 + timedelta(minutes=31), inatividade) is None
    assert repos.sessoes.obter("h1") is None
    assert repos.sessoes.renovar("h1", t1, inatividade) is None
    repos.sessoes.criar(SessaoCS("h2", "ana", "gestor", T0, 0))
    assert repos.sessoes.encerrar("h2") and not repos.sessoes.encerrar("h2")


def test_config_ida_e_volta(repos) -> None:
    repos.config.definir("limite_msgs_modelo", 10)
    repos.config.definir("limiar_relevancia", 0.5)
    repos.config.definir("termos_risco", ["fumaça", "choque"])
    assert repos.config.obter("limite_msgs_modelo") == 10
    assert repos.config.obter("limiar_relevancia") == Decimal("0.5")
    assert repos.config.obter("termos_risco") == ["fumaça", "choque"]
    assert repos.config.obter("nada") is None
    assert set(repos.config.listar()) == {"limite_msgs_modelo", "limiar_relevancia", "termos_risco"}


def test_tabela_nao_cria_item_por_engano(recurso) -> None:
    t = Tabela(recurso, f"{PREFIXO}-config", "config", pk="chave")
    with pytest.raises(ErroNaoEncontrado):
        t.atualizar(t.chave("fantasma"), "SET #v = :v", {"#v": "valor"}, {":v": 1})
    assert t.obter(t.chave("fantasma")) is None


def test_erros_de_cliente_nao_vazam_valores(recurso) -> None:
    t = Tabela(recurso, "tabela-inexistente", "x", pk="chave")
    with pytest.raises(ErroRepositorio) as exc:
        t.gravar({"chave": "segredo-123"})
    assert "segredo-123" not in str(exc.value)
    assert isinstance(exc.value.__cause__, ClientError)


# ----------------------------------------------------------------------------- concorrência


def _com_leitura_obsoleta(repo, instantaneo: Jornada):
    """Faz a primeira leitura da Jornada devolver um instantâneo antigo (escrita concorrente)."""
    original = repo.ler
    chamadas = {"n": 0}

    def ler(jornada_id: str):
        chamadas["n"] += 1
        return instantaneo if chamadas["n"] == 1 else original(jornada_id)

    repo.ler = ler
    return chamadas


def test_escalada_refaz_a_leitura_quando_o_estado_da_jornada_mudou(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    velho = repos.jornadas.obter("J1")  # "ativa"
    repos.jornadas.encerrar("J1", "guia", T0 + timedelta(minutes=1))  # muda depois da leitura
    _com_leitura_obsoleta(repos.chamados._jornadas, velho)

    assert escalar(repos, "J1", numero(1)).criado
    j = repos.jornadas.obter("J1")
    assert j.estado == "encerrada" and j.encerramento.camada == "guia"
    assert j.escalada.chamado_numero == numero(1)


def test_abandono_nao_vence_uma_interacao_concorrente(repos) -> None:
    repos.jornadas.criar(jornada("J1"))
    velho = repos.jornadas.obter("J1")
    agora = T0 + timedelta(minutes=40)
    repos.jornadas.registrar_interacao("J1", agora - timedelta(minutes=1))  # depois da leitura
    _com_leitura_obsoleta(repos.jornadas, velho)

    assert not repos.jornadas.marcar_abandono("J1", agora).aplicado
    assert repos.jornadas.obter("J1").estado == "ativa"
