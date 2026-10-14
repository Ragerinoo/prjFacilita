"""Testes do serviço de encerramento de Jornada (tarefa 9.4).

Cobrem a porta `encerrar_jornada` (nunca levanta, sem PII), o consumidor (idempotente, falha
parcial de lote, 3 tentativas e DLQ) e o sinal de falha para o Painel_Metricas.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import boto3
import pytest
from hypothesis import given
from hypothesis import strategies as st
from moto import mock_aws

from core.logs import Log
from handlers import encerramento as handler
from repositorios import ErroNaoEncontrado, ErroRepositorio, criar_repositorios_memoria
from repositorios.modelos import Jornada
from servicos.encerramento import (
    CAMADAS_ENFILEIRAVEIS,
    METRICA_FALHA_ENCERRAMENTO,
    EncerradorSqs,
    MensagemEncerramento,
    MensagemInvalida,
    consultar_falhas_encerramento,
    criar_encerrador,
    processar_lote,
)
from servicos.sqs_memoria import SqsMemoria

T0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
T_FIM = T0 + timedelta(seconds=312)
JID = "01JTESTJORNADA0000000000AA"


def nova_jornada(jid: str = JID) -> Jornada:
    return Jornada(
        jornada_id=jid, criada_em=T0, ultima_interacao=T0, origem="qr", origem_inicial="qr"
    )


@pytest.fixture
def repos():
    r = criar_repositorios_memoria()
    r.jornadas.criar(nova_jornada())
    return r


@pytest.fixture
def sqs():
    return SqsMemoria()


@pytest.fixture
def encerrador(sqs, repos):
    return EncerradorSqs(sqs, sqs.fila_url, relogio=lambda: T_FIM, agregados=repos.agregados)


@pytest.fixture
def consumidor(repos):
    """Handler de Lambda ligado ao repositório de teste (sem DynamoDB)."""
    handler.redefinir()
    handler._jornadas = repos.jornadas
    yield handler.lambda_handler
    handler.redefinir()


class JornadasInstavel:
    """Repositório que falha nas primeiras `falhas` chamadas de `encerrar` (infraestrutura)."""

    def __init__(self, real, falhas: int) -> None:
        self._real = real
        self.falhas = falhas
        self.chamadas = 0

    def encerrar(self, *args, **kwargs):
        self.chamadas += 1
        if self.falhas > 0:
            self.falhas -= 1
            raise ErroRepositorio("jornadas: timeout")
        return self._real.encerrar(*args, **kwargs)


# --------------------------------------------------------------------------- mensagem


def test_mensagem_vai_e_volta_sem_perder_campos():
    original = MensagemEncerramento(
        JID, "humano", T_FIM, Decimal("0.0500"), problema_id=3, desfecho="falso_defeito"
    )
    corpo = original.para_json()
    assert MensagemEncerramento.de_json(corpo) == original
    assert set(json.loads(corpo)) == {
        "v",
        "jornada_id",
        "camada",
        "em",
        "custo_brl",
        "problema_id",
        "desfecho",
    }


@pytest.mark.parametrize(
    "campos",
    [
        {"jornada_id": ""},
        {"jornada_id": "tem espaço"},
        {"camada": "abandonada"},  # só a varredura produz abandono
        {"camada": "outra"},
        {"em": datetime(2025, 1, 1)},  # sem fuso
        {"custo_brl": Decimal("-0.01")},
        {"custo_brl": Decimal("NaN")},
        {"problema_id": 0},
        {"problema_id": True},
        {"desfecho": "texto livre do atendente"},
    ],
)
def test_mensagem_invalida_e_recusada(campos):
    base = {"jornada_id": JID, "camada": "guia", "em": T_FIM}
    with pytest.raises(MensagemInvalida):
        MensagemEncerramento(**{**base, **campos})


@pytest.mark.parametrize("corpo", ["", "não é json", "[]", "{}", '{"v": 2}', '{"v": 1, "em": 3}'])
def test_corpo_malformado_vira_mensagem_invalida(corpo):
    with pytest.raises(MensagemInvalida):
        MensagemEncerramento.de_json(corpo)


@given(
    camada=st.sampled_from(CAMADAS_ENFILEIRAVEIS),
    custo=st.decimals(min_value=0, max_value=1000, places=4),
    problema=st.none() | st.integers(min_value=1, max_value=99),
    desfecho=st.none() | st.sampled_from(["falso_defeito", "defeito_real"]),
    segundos=st.integers(min_value=0, max_value=10**8),
)
def test_propriedade_ida_e_volta_da_mensagem(camada, custo, problema, desfecho, segundos):
    """**Validates: Requirements 17.1, 17.12**"""
    original = MensagemEncerramento(
        JID, camada, T0 + timedelta(seconds=segundos), custo, problema, desfecho
    )
    assert MensagemEncerramento.de_json(original.para_json()) == original


# --------------------------------------------------------------------------- porta (produtor)


def test_porta_enfileira_json_com_o_instante_do_fluxo(encerrador, sqs):
    resultado = encerrador.encerrar_jornada(JID, "guia", problema_id=2)
    assert resultado.enfileirado and resultado.motivo is None and resultado.message_id
    (corpo,) = sqs.corpos_na_fila
    mensagem = MensagemEncerramento.de_json(corpo)
    assert (mensagem.jornada_id, mensagem.camada, mensagem.em) == (JID, "guia", T_FIM)
    assert mensagem.problema_id == 2


def test_porta_nao_levanta_quando_o_sqs_falha_e_sinaliza(encerrador, sqs, repos):
    sqs.falhar_proximos_envios(1)
    resultado = encerrador.encerrar_jornada(JID, "ia")  # não levanta
    assert not resultado.enfileirado and resultado.motivo == "falha_envio"
    assert sqs.tamanho == 0
    assert repos.agregados.obter(T_FIM.date(), METRICA_FALHA_ENCERRAMENTO) == 1


def test_porta_nao_levanta_com_argumentos_invalidos(encerrador, sqs, repos):
    resultado = encerrador.encerrar_jornada(JID, "abandonada")  # type: ignore[arg-type]
    assert resultado.motivo == "mensagem_invalida" and sqs.envios == 0
    assert repos.agregados.obter(T_FIM.date(), METRICA_FALHA_ENCERRAMENTO) == 1


def test_porta_sem_fila_configurada_devolve_falha(repos):
    encerrador = criar_encerrador({}, agregados=repos.agregados, relogio=lambda: T_FIM)
    resultado = encerrador.encerrar_jornada(JID, "guia")
    assert resultado.motivo == "fila_nao_configurada"


def test_porta_sobrevive_a_falha_do_proprio_contador(sqs):
    class AgregadosQuebrado:
        def incrementar(self, *_a, **_k):
            raise ErroRepositorio("agregados_dia indisponível")

    sqs.falhar_proximos_envios(1)
    porta = EncerradorSqs(sqs, sqs.fila_url, relogio=lambda: T_FIM, agregados=AgregadosQuebrado())
    assert porta.encerrar_jornada(JID, "guia").enfileirado is False


def test_log_da_falha_nao_contem_pii(sqs, caplog):
    sqs.falhar_proximos_envios(1, ConnectionError("telefone 11 91234-5678"))
    porta = EncerradorSqs(sqs, sqs.fila_url, relogio=lambda: T_FIM, log=Log())
    with caplog.at_level("ERROR", logger="tres"):
        porta.encerrar_jornada(JID, "guia")
    assert "91234" not in caplog.text and "encerramento_nao_enfileirado" in caplog.text


# --------------------------------------------------------------------------- consumidor


def test_consumidor_grava_encerramento_da_porta(encerrador, sqs, repos, consumidor):
    encerrador.encerrar_jornada(JID, "ia", custo_brl=Decimal("0.0345"), problema_id=4)
    sqs.drenar(consumidor)
    j = repos.jornadas.obter(JID)
    assert j.estado == "encerrada" and j.encerramento is not None
    assert j.encerramento.camada == "ia"
    assert j.encerramento.encerrada_em == T_FIM
    assert j.encerramento.tempo_s == 312
    assert j.encerramento.custo_brl == Decimal("0.03")  # 2 casas, como o domínio
    assert j.encerramento.problema_id == 4
    assert sqs.tamanho == 0 and sqs.corpos_na_dlq == []


def test_primeira_camada_vence_quando_a_mensagem_chega_depois(encerrador, sqs, repos, consumidor):
    repos.jornadas.encerrar(JID, "guia", T0 + timedelta(seconds=10))
    encerrador.encerrar_jornada(JID, "humano")
    sqs.drenar(consumidor)
    j = repos.jornadas.obter(JID)
    assert j.encerramento.camada == "guia" and j.encerramento.tempo_s == 10
    assert sqs.corpos_na_dlq == []  # concluir sem alterar não é falha


@given(
    entregas=st.integers(min_value=1, max_value=5), camada=st.sampled_from(CAMADAS_ENFILEIRAVEIS)
)
def test_propriedade_reprocessar_a_mesma_mensagem_e_idempotente(entregas, camada):
    """**Validates: Requirements 17.1**"""
    repos = criar_repositorios_memoria()
    repos.jornadas.criar(nova_jornada())
    corpo = MensagemEncerramento(JID, camada, T_FIM, Decimal("0.5")).para_json()
    evento = {"Records": [{"messageId": "m", "body": corpo}]}
    estados = []
    for _ in range(entregas):
        assert processar_lote(evento, repos.jornadas) == {"batchItemFailures": []}
        estados.append(repos.jornadas.obter(JID))
    assert all(e == estados[0] for e in estados)


def test_falha_devolve_so_a_mensagem_com_problema(repos):
    ok = MensagemEncerramento(JID, "guia", T_FIM).para_json()
    ausente = MensagemEncerramento("JORNADA-INEXISTENTE", "guia", T_FIM).para_json()
    evento = {
        "Records": [
            {"messageId": "a", "body": ok},
            {"messageId": "b", "body": ausente},
            {"messageId": "c", "body": "veneno"},
        ]
    }
    resposta = processar_lote(evento, repos.jornadas)
    assert resposta == {"batchItemFailures": [{"itemIdentifier": "b"}, {"itemIdentifier": "c"}]}
    assert repos.jornadas.obter(JID).estado == "encerrada"  # a boa foi gravada


def test_jornada_inexistente_levanta_nao_encontrado_no_repositorio(repos):
    with pytest.raises(ErroNaoEncontrado):
        repos.jornadas.encerrar("JORNADA-INEXISTENTE", "guia", T_FIM)


def test_falha_transitoria_se_recupera_na_nova_tentativa(encerrador, sqs, repos):
    instavel = JornadasInstavel(repos.jornadas, falhas=2)
    encerrador.encerrar_jornada(JID, "guia")
    sqs.drenar(lambda ev, ctx: processar_lote(ev, instavel))
    assert instavel.chamadas == 3  # 2 falhas + sucesso na 3ª tentativa
    assert repos.jornadas.obter(JID).estado == "encerrada"
    assert sqs.corpos_na_dlq == []


def test_esgotadas_as_3_tentativas_a_mensagem_vai_para_a_dlq(encerrador, sqs, repos, caplog):
    instavel = JornadasInstavel(repos.jornadas, falhas=99)
    encerrador.encerrar_jornada(JID, "guia")
    with caplog.at_level("ERROR", logger="tres"):
        sqs.drenar(lambda ev, ctx: processar_lote(ev, instavel))
    assert instavel.chamadas == 3
    assert sqs.tamanho == 0 and len(sqs.corpos_na_dlq) == 1
    assert repos.jornadas.obter(JID).estado == "ativa"  # dados da Jornada mantidos (Req 17.12)
    assert caplog.text.count("encerramento_falhou") == 2
    assert caplog.text.count("encerramento_tentativas_esgotadas") == 1


def test_lote_sem_registros_e_evento_estranho_nao_quebram(repos):
    assert processar_lote({}, repos.jornadas) == {"batchItemFailures": []}
    assert processar_lote({"Records": []}, repos.jornadas) == {"batchItemFailures": []}
    assert processar_lote({"Records": [None, {}]}, repos.jornadas) == {"batchItemFailures": []}


def test_handler_cria_repositorio_local_por_modo(monkeypatch):
    monkeypatch.setenv("TRES_MODO", "local")
    handler.redefinir()
    try:
        corpo = MensagemEncerramento(JID, "guia", T_FIM).para_json()
        # Jornada não existe no repositório novo: a mensagem deve voltar à fila.
        resposta = handler.lambda_handler({"Records": [{"messageId": "x", "body": corpo}]})
        assert resposta == {"batchItemFailures": [{"itemIdentifier": "x"}]}
    finally:
        handler.redefinir()


# --------------------------------------------------------------------------- sinal ao Painel


def test_sinal_reune_dlq_e_envios_perdidos(encerrador, sqs, repos):
    # um encerramento perdido no envio e outro esgotado na DLQ
    sqs.falhar_proximos_envios(1)
    encerrador.encerrar_jornada(JID, "guia")
    repos.jornadas.criar(nova_jornada("OUTRA-JORNADA"))
    encerrador.encerrar_jornada("OUTRA-JORNADA", "guia")
    instavel = JornadasInstavel(repos.jornadas, falhas=99)
    sqs.drenar(lambda ev, ctx: processar_lote(ev, instavel))

    sinal = consultar_falhas_encerramento(
        sqs=sqs,
        dlq_url=sqs.dlq_url,
        agregados=repos.agregados,
        inicio=date(2025, 1, 1),
        fim=date(2025, 1, 1),
    )
    assert (sinal.na_dlq, sinal.nao_enfileirados) == (1, 1)
    assert sinal.houve_falha and sinal.total == 2


def test_sinal_sem_falhas_e_respeita_o_periodo(repos, sqs):
    repos.agregados.incrementar(date(2025, 1, 5), METRICA_FALHA_ENCERRAMENTO)
    sinal = consultar_falhas_encerramento(
        sqs=sqs,
        dlq_url=sqs.dlq_url,
        agregados=repos.agregados,
        inicio=date(2025, 1, 1),
        fim=date(2025, 1, 4),
    )
    assert (sinal.na_dlq, sinal.nao_enfileirados) == (0, 0) and not sinal.houve_falha


def test_dlq_indisponivel_vira_desconhecido_e_nao_zero(repos):
    class SqsQuebrado:
        def get_queue_attributes(self, **_):
            raise ConnectionError("sem rede")

    sinal = consultar_falhas_encerramento(
        sqs=SqsQuebrado(),
        dlq_url="mem://dlq",
        agregados=repos.agregados,
        inicio=date(2025, 1, 1),
        fim=date(2025, 1, 1),
    )
    assert sinal.na_dlq is None


# --------------------------------------------------------------------------- SQS real (moto)


@mock_aws
def test_porta_e_sinal_com_sqs_do_moto(monkeypatch):
    for nome in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(nome, "teste")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    cliente = boto3.client("sqs")
    dlq_url = cliente.create_queue(QueueName="tres-encerramentos-dlq")["QueueUrl"]
    dlq_arn = cliente.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"])[
        "Attributes"
    ]["QueueArn"]
    fila_url = cliente.create_queue(
        QueueName="tres-encerramentos",
        Attributes={
            "VisibilityTimeout": "10",
            "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": 3}),
        },
    )["QueueUrl"]

    porta = criar_encerrador(
        {"TRES_FILA_ENCERRAMENTOS_URL": fila_url}, sqs=cliente, relogio=lambda: T_FIM
    )
    assert porta.encerrar_jornada(JID, "humano", desfecho="defeito_real").enfileirado

    recebida = cliente.receive_message(QueueUrl=fila_url, VisibilityTimeout=0)["Messages"][0]
    mensagem = MensagemEncerramento.de_json(recebida["Body"])
    assert (mensagem.camada, mensagem.desfecho, mensagem.em) == ("humano", "defeito_real", T_FIM)

    repos = criar_repositorios_memoria()
    sinal = consultar_falhas_encerramento(
        sqs=cliente,
        dlq_url=dlq_url,
        agregados=repos.agregados,
        inicio=date(2025, 1, 1),
        fim=date(2025, 1, 1),
    )
    assert sinal.na_dlq == 0
    cliente.send_message(QueueUrl=dlq_url, MessageBody="{}")
    assert (
        consultar_falhas_encerramento(
            sqs=cliente,
            dlq_url=dlq_url,
            agregados=repos.agregados,
            inicio=date(2025, 1, 1),
            fim=date(2025, 1, 1),
        ).na_dlq
        == 1
    )
