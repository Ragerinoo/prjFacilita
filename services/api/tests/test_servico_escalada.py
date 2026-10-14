"""Testes do serviço de escalada e marcação de risco (tarefa 12.1).

Usam os repositórios em memória. Falhas são injetadas com decoradores finos sobre os repositórios
reais (o comportamento condicional continua sendo o do fake). A propriedade 5 (PBT) é a 12.5.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from dominio import validar_pacote
from dominio.pacote import (
    PROXIMA_ACAO_FALLBACK,
    RESUMO_FALLBACK,
    SENTIMENTO_FALLBACK,
    pacote_para_dict,
)
from repositorios import ErroNaoEncontrado, ErroRepositorio, criar_repositorios_memoria
from repositorios.ids import novo_ulid
from repositorios.modelos import Evento, Jornada
from servicos.escalada import (
    ALFABETO_CROCKFORD,
    DisparadorEnriquecimentoFake,
    ServicoEscalada,
    apresentar_prioridade,
    categoria_do_problema,
    envelope_jornada,
    estado_publico,
    gerar_numero_chamado,
    ja_tentado_de_eventos,
)

T0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
JID = "01JTESTJORNADA0000000000AA"
JID2 = "01JTESTJORNADA0000000000BB"
PADRAO_NUMERO = re.compile(r"^TRES-[0-9A-HJKMNP-TV-Z]{10}$")


# ----------------------------------------------------------------------------- apoio


def nova_jornada(jid: str = JID, **campos) -> Jornada:
    base = {
        "jornada_id": jid,
        "criada_em": T0,
        "ultima_interacao": T0,
        "origem": "qr",
        "origem_inicial": "qr",
        "modelo_id": "tres-modelo-x",
        "numero_serie": "ABC123",
        "problema_id": 7,
    }
    base.update(campos)
    return Jornada(**base)


class Relogio:
    def __init__(self) -> None:
        self.agora = T0

    def __call__(self) -> datetime:
        self.agora += timedelta(seconds=1)
        return self.agora


class Quebrado:
    """Decorador que faz os métodos listados levantarem `ErroRepositorio`."""

    def __init__(self, alvo, *metodos: str) -> None:
        self._alvo = alvo
        self._metodos = set(metodos)
        self.chamadas: dict[str, int] = {}

    def __getattr__(self, nome: str):
        if nome in self._metodos:

            def falha(*_a, **_k):
                self.chamadas[nome] = self.chamadas.get(nome, 0) + 1
                raise ErroRepositorio(f"{nome} indisponível")

            return falha
        return getattr(self._alvo, nome)


class Sequencia:
    """Gerador de números controlado; repete o último quando acaba."""

    def __init__(self, *numeros: str) -> None:
        self._numeros = list(numeros)
        self.usados = 0

    def __call__(self) -> str:
        self.usados += 1
        return self._numeros.pop(0) if len(self._numeros) > 1 else self._numeros[0]


@pytest.fixture
def repos():
    r = criar_repositorios_memoria()
    r.jornadas.criar(nova_jornada())
    return r


@pytest.fixture
def disparador():
    return DisparadorEnriquecimentoFake()


def criar_servico(repos, disparador=None, **extra) -> ServicoEscalada:
    extra.setdefault("gerar_numero", gerar_numero_chamado)
    return ServicoEscalada(repos, relogio=Relogio(), disparador=disparador, **extra)


@pytest.fixture
def servico(repos, disparador):
    return criar_servico(repos, disparador)


def com(repos, **substituicoes):
    return replace(repos, **substituicoes)


# ------------------------------------------------------------------ funções puras


def test_apresentacao_usa_linguagem_simples_com_prazos():
    p1, p2, p3 = (apresentar_prioridade(p) for p in ("P1", "P2", "P3"))
    assert "15 minutos" in p1.prazo and "15 minutos" in p1.proximo_passo
    assert "4 horas úteis" in p2.prazo
    assert "1 dia útil" in p3.prazo
    assert len({p1.rotulo, p2.rotulo, p3.rotulo}) == 3
    for texto in (p1, p2, p3):
        for campo in (texto.rotulo, texto.prazo, texto.proximo_passo):
            assert not re.search(r"\bP[123]\b", campo)


def test_apresentacao_prioridade_desconhecida():
    with pytest.raises(ValueError):
        apresentar_prioridade("P9")  # type: ignore[arg-type]


def test_numero_do_chamado_tem_formato_crockford_e_nao_e_sequencial():
    numeros = {gerar_numero_chamado() for _ in range(2000)}
    assert len(numeros) == 2000
    assert all(PADRAO_NUMERO.match(n) for n in numeros)
    consecutivos = gerar_numero_chamado(lambda _bits: 1), gerar_numero_chamado(lambda _bits: 2)
    assert consecutivos == ("TRES-0000000001", "TRES-0000000002")  # a função usa só o sorteio
    assert gerar_numero_chamado(lambda bits: (1 << bits) - 1) == "TRES-" + "Z" * 10
    assert set("TRES-".join(numeros)) <= set(ALFABETO_CROCKFORD + "TRES-")


def test_categoria_do_problema():
    assert categoria_do_problema(1) == "nao_liga"
    assert categoria_do_problema(7) == "bebida_aguada"
    assert categoria_do_problema(13) == "alavanca_nao_fecha_com_capsula"
    for invalido in (None, 0, 14, -1):
        assert categoria_do_problema(invalido) == "outro"


def test_ja_tentado_ignora_eventos_fora_do_contrato_e_preserva_a_ordem():
    def ev(tipo, dados, i):
        return Evento(JID, novo_ulid(T0 + timedelta(seconds=i)), tipo, T0, dados)

    eventos = [
        ev(
            "passo_concluido",
            {"passo": "Verifique a tomada", "camada": "guia", "resultado": "não"},
            1,
        ),
        ev("problema_selecionado", {"passo": "ignorado"}, 2),
        ev("passo_concluido", {"passo": "   "}, 3),
        ev("passo_concluido", {"passo": "Limpe o bico"}, 4),
        ev("passo_concluido", {"passo": "x" * 500, "camada": "ia", "resultado": "sim"}, 5),
        ev("passo_concluido", {"passo": "Reinicie", "camada": "outra", "resultado": "talvez"}, 6),
    ]
    itens = ja_tentado_de_eventos(eventos)
    assert [i.passo[:12] for i in itens] == [
        "Verifique a ",
        "Limpe o bico",
        "xxxxxxxxxxxx",
        "Reinicie",
    ]
    assert (itens[0].camada, itens[0].resultado) == ("guia", "não")
    assert (itens[1].camada, itens[1].resultado) == ("guia", "sem resposta")
    assert len(itens[2].passo) == 200 and itens[2].camada == "ia"
    assert (itens[3].camada, itens[3].resultado) == ("guia", "sem resposta")


def test_estado_publico_e_envelope(repos):
    j = repos.jornadas.obter(JID)
    assert estado_publico(j) == "ativa"
    env = envelope_jornada(j)
    assert env == {
        "jornada_id": JID,
        "estado": "ativa",
        "risco": {"marcado": False},
        "contato_cs": "pendente",
    }
    repos.jornadas.encerrar(JID, "ia", T0 + timedelta(minutes=1))
    assert estado_publico(repos.jornadas.obter(JID)) == "encerrada_ia"
    j2 = nova_jornada(JID2)
    repos.jornadas.criar(j2)
    repos.jornadas.marcar_abandono(JID2, T0 + timedelta(hours=2))
    assert estado_publico(repos.jornadas.obter(JID2)) == "abandonada"


# ------------------------------------------------------------------ escalar: P3


def test_escalar_sem_fatos_cria_chamado_p3_com_pacote_valido(repos, servico, disparador):
    r = servico.escalar(JID, "pedido_humano")

    assert r.criado and not r.prioridade_elevada and r.gatilho_registrado
    c = r.chamado
    assert PADRAO_NUMERO.match(c.numero)
    assert (c.prioridade, c.classificacao, c.canal, c.decisao_criterio) == (
        "P3",
        "provável uso",
        "chat assíncrono",
        3,
    )
    assert c.status == "aberto" and c.pacote_ia_status == "pendente"
    assert c.gatilho_nao_registrado is False and c.os_status == "nao_aplicavel"
    # Pacote determinístico com valores provisórios de IA (Req 10.2, 10.4)
    p = c.pacote
    assert validar_pacote(pacote_para_dict(p)) == []
    assert (p.resumo, p.sentimento, p.proxima_acao) == (
        RESUMO_FALLBACK,
        SENTIMENTO_FALLBACK,
        PROXIMA_ACAO_FALLBACK,
    )
    assert (p.modelo, p.numero_serie, p.origem, p.categoria) == (
        "tres-modelo-x",
        "ABC123",
        "qr",
        "bebida_aguada",
    )
    assert p.anexos == () and p.numero_chamado == c.numero
    # Jornada: escalada, decisão com critério e horário, gatilho (Req 9.7, 11.7)
    j = r.jornada
    assert j.estado == "escalada" and j.chamado_numero == c.numero
    assert j.escalada.decisao.criterio == 3 and j.escalada.decisao.em == c.criado_em
    assert [(g.tipo, g.registrado) for g in j.escalada.gatilhos] == [("pedido_humano", True)]
    # Enriquecimento disparado uma vez; sem Ordem_Servico em P3
    assert disparador.disparados == [c.numero]
    assert repos.ordens_servico.obter(c.numero) is None
    assert [x.numero for x in repos.chamados.listar_fila()] == [c.numero]


def test_pacote_sem_serie_e_sem_modelo_usa_nao_informado(repos, servico):
    repos.jornadas.criar(nova_jornada(JID2, modelo_id=None, numero_serie=None, problema_id=None))
    p = servico.escalar(JID2, "pedido_humano").chamado.pacote
    assert (p.modelo, p.numero_serie, p.categoria) == ("não informado", "não informado", "outro")
    assert validar_pacote(pacote_para_dict(p)) == []


def test_nome_do_modelo_vem_do_resolvedor_e_e_truncado(repos, disparador):
    s = criar_servico(repos, disparador, nome_modelo=lambda mid: "Máquina " + "é" * 100)
    p = s.escalar(JID, "pedido_humano").chamado.pacote
    assert p.modelo.startswith("Máquina é") and len(p.modelo) == 80


def test_ja_tentado_vem_dos_eventos_da_jornada(repos, servico):
    repos.eventos.registrar(
        Evento(
            JID,
            novo_ulid(T0),
            "passo_concluido",
            T0,
            {"passo": "Verifique a tomada", "camada": "guia", "resultado": "não"},
        )
    )
    p = servico.escalar(JID, "pedido_humano").chamado.pacote
    assert [(i.passo, i.camada, i.resultado) for i in p.ja_tentado] == [
        ("Verifique a tomada", "guia", "não")
    ]


def test_o_gatilho_e_registrado_como_evento(repos, servico):
    servico.escalar(JID, "limite_mensagens")
    tipos = [(e.tipo, e.dados) for e in repos.eventos.listar(JID)]
    assert tipos == [("escalada_gatilho", {"gatilho": "limite_mensagens"})]


# ------------------------------------------------------------------ escalar: P2 e Ordem_Servico


def test_p2_cria_ordem_servico_rascunho_com_dados_da_jornada(repos, servico):
    repos.jornadas.marcar_guia_respondeu_nao(JID)
    c = servico.escalar(JID, "instrucao_sem_solucao").chamado

    assert (c.prioridade, c.classificacao, c.decisao_criterio) == ("P2", "provável defeito", 2)
    assert c.canal == "chat ou ligação, à escolha do Consumidor"
    assert c.os_status == "ok"
    os_ = repos.ordens_servico.obter(c.numero)
    assert os_.status == "rascunho" and os_.os_id == f"OS#{c.numero}"
    assert (os_.modelo, os_.numero_serie, os_.categoria) == (
        "tres-modelo-x",
        "ABC123",
        "bebida_aguada",
    )
    assert os_.ja_tentado == c.pacote.ja_tentado


def test_falha_na_ordem_servico_nao_desfaz_o_chamado_e_marca_falha(repos, disparador):
    repos.jornadas.marcar_guia_respondeu_nao(JID)
    quebrada = Quebrado(repos.ordens_servico, "criar_rascunho")
    s = criar_servico(com(repos, ordens_servico=quebrada), disparador)

    r = s.escalar(JID, "instrucao_sem_solucao")

    assert r.criado and r.chamado.prioridade == "P2" and r.chamado.os_status == "falha"
    assert repos.chamados.obter(r.numero) is not None
    assert repos.ordens_servico.obter(r.numero) is None
    assert disparador.disparados == [r.numero]  # o enriquecimento segue


def test_nova_escalada_tenta_de_novo_a_ordem_servico_sem_duplicar(repos, disparador):
    repos.jornadas.marcar_guia_respondeu_nao(JID)
    quebrada = Quebrado(repos.ordens_servico, "criar_rascunho")
    numero = (
        criar_servico(com(repos, ordens_servico=quebrada), disparador)
        .escalar(JID, "instrucao_sem_solucao")
        .numero
    )
    assert repos.chamados.obter(numero).os_status == "falha"

    r = criar_servico(repos, disparador).escalar(JID, "pedido_humano")  # repositório saudável

    assert not r.criado and r.chamado.os_status == "ok"
    assert repos.ordens_servico.obter(numero).status == "rascunho"
    r2 = criar_servico(repos, disparador).escalar(JID, "pedido_humano")
    assert r2.chamado.os_status == "ok"


def test_falha_no_registro_do_ordem_servico_status_mantem_o_chamado(repos, disparador):
    repos.jornadas.marcar_guia_respondeu_nao(JID)
    s = criar_servico(com(repos, chamados=_SemOsStatus(repos.chamados)), disparador)
    r = s.escalar(JID, "instrucao_sem_solucao")
    assert r.criado and r.chamado.prioridade == "P2"
    assert repos.ordens_servico.obter(r.numero) is not None


class _SemOsStatus(Quebrado):
    def __init__(self, alvo) -> None:
        super().__init__(alvo, "definir_os_status")


# ------------------------------------------------------------------ falhas do registro do gatilho


def test_falha_ao_registrar_o_gatilho_escala_mesmo_assim_e_marca_nao_registrado(repos, disparador):
    s = criar_servico(com(repos, eventos=Quebrado(repos.eventos, "registrar")), disparador)

    r = s.escalar(JID, "sem_embasamento")

    assert r.criado and not r.gatilho_registrado
    assert r.chamado.gatilho_nao_registrado is True
    assert r.chamado.prioridade == "P3"
    assert [(g.tipo, g.registrado) for g in r.jornada.escalada.gatilhos] == [
        ("sem_embasamento", False)
    ]
    assert validar_pacote(pacote_para_dict(r.chamado.pacote)) == []  # o Pacote não muda de esquema
    assert repos.eventos.listar(JID) == []


def test_eventos_indisponiveis_ao_listar_nao_impedem_o_chamado(repos, disparador):
    s = criar_servico(com(repos, eventos=Quebrado(repos.eventos, "listar")), disparador)
    r = s.escalar(JID, "pedido_humano")
    assert r.criado and r.chamado.pacote.ja_tentado == ()


def test_falha_no_enriquecimento_nao_afeta_o_chamado(repos):
    s = criar_servico(repos, DisparadorEnriquecimentoFake(erro=RuntimeError("sem rede")))
    r = s.escalar(JID, "pedido_humano")
    assert r.criado and r.chamado.pacote_ia_status == "pendente"


def test_sem_disparador_configurado_o_servico_funciona(repos):
    assert criar_servico(repos).escalar(JID, "pedido_humano").criado


# ------------------------------------------------------------------ número e transação


def test_colisao_de_numero_gera_outro(repos, disparador):
    repos.jornadas.criar(nova_jornada(JID2))
    seq = Sequencia("TRES-AAAAAAAAAA", "TRES-AAAAAAAAAA", "TRES-BBBBBBBBBB")
    s = criar_servico(repos, disparador, gerar_numero=seq)
    assert s.escalar(JID, "pedido_humano").numero == "TRES-AAAAAAAAAA"
    assert s.escalar(JID2, "pedido_humano").numero == "TRES-BBBBBBBBBB"
    assert seq.usados == 3


def test_numero_sempre_em_uso_desiste_sem_gravar_nada(repos, disparador):
    repos.jornadas.criar(nova_jornada(JID2))
    seq = Sequencia("TRES-AAAAAAAAAA")
    s = criar_servico(repos, disparador, gerar_numero=seq)
    s.escalar(JID, "pedido_humano")
    with pytest.raises(ErroRepositorio):
        s.escalar(JID2, "pedido_humano")
    assert repos.jornadas.obter(JID2).escalada is None
    assert repos.jornadas.obter(JID2).estado == "ativa"


def test_jornada_inexistente(servico):
    with pytest.raises(ErroNaoEncontrado):
        servico.escalar("naoexiste", "pedido_humano")
    with pytest.raises(ErroNaoEncontrado):
        servico.marcar_risco("naoexiste", "lista")


def test_falha_da_transacao_nao_grava_nada_e_pode_ser_repetida(repos, disparador):
    quebrado = Quebrado(repos.chamados, "criar_com_escalada")
    with pytest.raises(ErroRepositorio):
        criar_servico(com(repos, chamados=quebrado), disparador).escalar(JID, "pedido_humano")
    assert repos.jornadas.obter(JID).estado == "ativa" and repos.chamados.listar_fila() == []
    assert disparador.disparados == []

    r = criar_servico(repos, disparador).escalar(JID, "pedido_humano")
    assert r.criado


# ------------------------------------------------------------------ idempotência (Req 9.9)


def test_segunda_escalada_devolve_o_chamado_existente_e_registra_o_gatilho(
    repos, servico, disparador
):
    primeira = servico.escalar(JID, "pedido_humano")
    segunda = servico.escalar(JID, "frustracao_alta")
    repetida = servico.escalar(JID, "frustracao_alta")

    assert segunda.numero == repetida.numero == primeira.numero
    assert not segunda.criado and not segunda.prioridade_elevada and segunda.gatilho_registrado
    assert len(repos.chamados.listar_fila()) == 1
    tipos = [g.tipo for g in repos.jornadas.obter(JID).escalada.gatilhos]
    assert tipos == ["pedido_humano", "frustracao_alta"]  # sem duplicar o tipo repetido
    assert disparador.disparados == [primeira.numero]  # sem novo enriquecimento nem novo Pacote
    assert segunda.chamado.pacote == primeira.chamado.pacote


def test_escalada_concorrente_cria_um_unico_chamado(repos, disparador):
    s = criar_servico(repos, disparador)
    resultados, erros = [], []

    def trabalhar() -> None:
        try:
            resultados.append(s.escalar(JID, "pedido_humano"))
        except Exception as exc:  # noqa: BLE001
            erros.append(exc)

    threads = [threading.Thread(target=trabalhar) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not erros
    assert len({r.numero for r in resultados}) == 1
    assert sum(r.criado for r in resultados) == 1
    assert len(repos.chamados.listar_fila()) == 1 and disparador.disparados == [
        resultados[0].numero
    ]


# ------------------------------------------------------------------ reavaliação (nunca reduz)


def test_p3_vira_p2_no_mesmo_chamado_e_cria_ordem_servico(repos, servico):
    c3 = servico.escalar(JID, "pedido_humano").chamado
    assert c3.prioridade == "P3" and repos.ordens_servico.obter(c3.numero) is None

    repos.jornadas.marcar_guia_respondeu_nao(JID)
    r = servico.escalar(JID, "instrucao_sem_solucao")

    assert not r.criado and r.prioridade_elevada and r.numero == c3.numero
    assert (r.chamado.prioridade, r.chamado.decisao_criterio) == ("P2", 2)
    assert (
        r.chamado.pacote.prioridade == "P2"
        and r.chamado.pacote.canal_recomendado == r.chamado.canal
    )
    assert validar_pacote(pacote_para_dict(r.chamado.pacote)) == []
    assert r.chamado.os_status == "ok" and repos.ordens_servico.obter(c3.numero) is not None
    assert r.jornada.escalada.decisao.prioridade == "P2"


def test_prioridade_nunca_diminui(repos, servico):
    p1 = servico.marcar_risco(JID, "lista").escalada.chamado
    assert p1.prioridade == "P1"
    for gatilho in ("pedido_humano", "instrucao_sem_solucao", "duas_negativas_ia"):
        r = servico.escalar(JID, gatilho)
        assert r.numero == p1.numero and not r.prioridade_elevada
        assert r.chamado.prioridade == "P1" and r.chamado.decisao_criterio == 1


# ------------------------------------------------------------------ marcar_risco


def test_marcar_risco_cria_chamado_p1_com_ligacao_imediata(repos, servico, disparador):
    r = servico.marcar_risco(JID, "lista")

    assert r.nova_marcacao and not r.repasse_falhou
    c = r.escalada.chamado
    assert (c.prioridade, c.classificacao, c.canal, c.decisao_criterio) == (
        "P1",
        "provável defeito",
        "ligação imediata",
        1,
    )
    assert c.os_status == "nao_aplicavel" and repos.ordens_servico.obter(c.numero) is None
    j = repos.jornadas.obter(JID)
    assert j.risco.origem == "lista" and j.risco.em <= c.criado_em
    assert [g.tipo for g in j.escalada.gatilhos] == ["risco_seguranca"]
    assert j.escalada.decisao.criterio == 1
    assert disparador.disparados == [c.numero]
    assert r.envelope == {
        "jornada_id": JID,
        "estado": "escalada",
        "risco": {
            "marcado": True,
            "origem": "lista",
            "em": j.risco.em.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "contato_cs": "confirmado",
    }


@pytest.mark.parametrize("origem", ["lista", "ia", "guia"])
def test_todas_as_origens_de_risco_geram_p1(repos, servico, origem):
    r = servico.marcar_risco(JID, origem)
    assert r.escalada.chamado.prioridade == "P1"
    assert repos.jornadas.obter(JID).risco.origem == origem


def test_risco_com_gatilho_de_risco_prevalece_sobre_o_p2(repos, servico):
    repos.jornadas.marcar_guia_respondeu_nao(JID)
    assert servico.marcar_risco(JID, "ia").escalada.chamado.prioridade == "P1"


def test_marcacoes_repetidas_sao_monotonicas_e_nao_criam_outro_chamado(repos, servico, disparador):
    primeira = servico.marcar_risco(JID, "lista")
    marcada_em = repos.jornadas.obter(JID).risco.em
    segunda = servico.marcar_risco(JID, "ia")
    terceira = servico.marcar_risco(JID, "guia")

    assert primeira.nova_marcacao and not segunda.nova_marcacao and not terceira.nova_marcacao
    numeros = {primeira.escalada.numero, segunda.escalada.numero, terceira.escalada.numero}
    assert len(numeros) == 1 and len(repos.chamados.listar_fila()) == 1
    risco = repos.jornadas.obter(JID).risco
    assert (risco.origem, risco.em) == (
        "lista",
        marcada_em,
    )  # a primeira origem permanece (Req 8.4)
    assert [g.tipo for g in repos.jornadas.obter(JID).escalada.gatilhos] == ["risco_seguranca"]
    assert disparador.disparados == [primeira.escalada.numero]


def test_risco_depois_de_p3_reavalia_para_p1_sem_novo_chamado(repos, servico, disparador):
    outra = nova_jornada(JID2)
    repos.jornadas.criar(outra)
    servico.escalar(JID2, "pedido_humano")  # um P3 anterior, de outra Jornada, fica na fila
    c3 = servico.escalar(JID, "pedido_humano").chamado

    r = servico.marcar_risco(JID, "lista")

    assert r.nova_marcacao and not r.escalada.criado and r.escalada.prioridade_elevada
    assert r.escalada.numero == c3.numero
    c = repos.chamados.obter(c3.numero)
    assert (c.prioridade, c.canal, c.decisao_criterio) == ("P1", "ligação imediata", 1)
    assert c.pacote.prioridade == "P1" and c.pacote.classificacao == "provável defeito"
    assert validar_pacote(pacote_para_dict(c.pacote)) == []
    assert [x.prioridade for x in repos.chamados.listar_fila()] == ["P1", "P3"]  # reposicionado
    assert [g.tipo for g in repos.jornadas.obter(JID).escalada.gatilhos] == [
        "pedido_humano",
        "risco_seguranca",
    ]
    assert disparador.disparados.count(c3.numero) == 1
    assert r.envelope["contato_cs"] == "confirmado"


def test_risco_depois_de_p2_reavalia_para_p1_mantendo_a_ordem_servico(repos, servico):
    repos.jornadas.marcar_guia_respondeu_nao(JID)
    c2 = servico.escalar(JID, "instrucao_sem_solucao").chamado
    assert c2.prioridade == "P2"

    r = servico.marcar_risco(JID, "ia")

    assert r.escalada.chamado.prioridade == "P1" and r.escalada.numero == c2.numero
    assert repos.ordens_servico.obter(c2.numero).status == "rascunho"
    assert len(repos.chamados.listar_fila()) == 1


def test_falha_do_repasse_mantem_a_marcacao_e_informa_contato_nao_registrado(repos, disparador):
    s = criar_servico(
        com(repos, chamados=Quebrado(repos.chamados, "criar_com_escalada")), disparador
    )

    r = s.marcar_risco(JID, "lista")

    assert r.repasse_falhou and r.escalada is None and r.nova_marcacao
    assert (
        repos.jornadas.obter(JID).risco is not None and repos.jornadas.obter(JID).escalada is None
    )
    assert r.envelope["risco"]["marcado"] is True
    assert r.envelope["contato_cs"] == "nao_registrado"
    assert r.para_dict()["jornada"] == r.envelope

    # "Tentar novamente" (Req 8.6): escalar de novo refaz o repasse, uma vez só.
    nova = criar_servico(repos, disparador).escalar(JID, "risco_seguranca")
    assert nova.criado and nova.chamado.prioridade == "P1"
    assert nova.envelope["contato_cs"] == "confirmado"
    again = criar_servico(repos, disparador).escalar(JID, "risco_seguranca")
    assert not again.criado and again.numero == nova.numero


def test_falha_ao_gravar_a_marcacao_ainda_escala_p1(repos, disparador):
    s = criar_servico(com(repos, jornadas=_JornadasSemMarcacao(repos.jornadas)), disparador)

    r = s.marcar_risco(JID, "lista")

    assert not r.repasse_falhou and r.escalada.chamado.prioridade == "P1"
    assert r.escalada.chamado.decisao_criterio == 1


class _JornadasSemMarcacao(Quebrado):
    def __init__(self, alvo) -> None:
        super().__init__(alvo, "marcar_risco")


def test_escalar_por_gatilho_de_risco_sem_marcacao_marca_o_risco(repos, servico):
    r = servico.escalar(JID, "risco_seguranca", origem_risco="ia")
    assert r.chamado.prioridade == "P1"
    assert repos.jornadas.obter(JID).risco.origem == "ia"


def test_marcacoes_concorrentes_criam_um_unico_chamado_p1(repos, disparador):
    s = criar_servico(repos, disparador)
    resultados, erros = [], []

    def trabalhar(origem: str) -> None:
        try:
            resultados.append(s.marcar_risco(JID, origem))  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            erros.append(exc)

    threads = [threading.Thread(target=trabalhar, args=(o,)) for o in ["lista", "ia", "guia"] * 4]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not erros and len(repos.chamados.listar_fila()) == 1
    assert {r.escalada.numero for r in resultados} == {repos.chamados.listar_fila()[0].numero}
    assert sum(r.nova_marcacao for r in resultados) == 1
    assert len(disparador.disparados) == 1


# ------------------------------------------------------------------ resposta ao Consumidor


def test_para_dict_nao_expoe_siglas_nem_dados_pessoais(repos, servico):
    p1 = servico.marcar_risco(JID, "lista").para_dict()
    repos.jornadas.criar(nova_jornada(JID2))
    repos.jornadas.marcar_guia_respondeu_nao(JID2)
    p2 = servico.escalar(JID2, "instrucao_sem_solucao").para_dict()

    assert p1["chamado"]["dados_solicitados"] == ["telefone"]
    assert p2["chamado"]["dados_solicitados"] == ["telefone", "cep"]
    assert "15 minutos" in p1["chamado"]["prazo"] and "4 horas úteis" in p2["chamado"]["prazo"]
    assert p1["novo"] is True
    for corpo in (p1, p2):
        texto = json.dumps(corpo, ensure_ascii=False)
        assert not re.search(r'"P[123]"|\bP[123]\b', texto)
        assert "ABC123" not in texto
        assert set(corpo["jornada"]) == {"jornada_id", "estado", "risco", "contato_cs"}
        assert PADRAO_NUMERO.match(corpo["chamado"]["numero"])


def test_chamado_p3_confirma_contato_no_envelope(repos, servico):
    r = servico.escalar(JID, "pedido_humano")
    assert r.envelope["contato_cs"] == "confirmado" and r.envelope["risco"] == {"marcado": False}
    assert r.para_dict()["chamado"]["dados_solicitados"] == []
