"""Testes dos fakes em memória: garantias condicionais dos repositórios (tarefa 9.1).

Os testes de contrato contra DynamoDB/moto vêm na tarefa 9.3.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dominio import (
    EntradaCache,
    ItemJaTentado,
    PacoteRepasse,
    StatusInsercao,
    chave_cache,
)
from repositorios import ErroNaoEncontrado, ErroRepositorio, criar_repositorios_memoria
from repositorios.ids import eh_ulid, novo_ulid
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


def numero(i: int) -> str:
    return "TRES-" + ALFABETO[i % 32] * 9 + ALFABETO[(i // 32) % 32]


def jornada(jid: str = "J1", em: datetime = T0) -> Jornada:
    return Jornada(
        jornada_id=jid, criada_em=em, ultima_interacao=em, origem="qr", origem_inicial="qr"
    )


def pacote(num: str, prioridade: str = "P3") -> PacoteRepasse:
    return PacoteRepasse(
        numero_chamado=num,
        modelo="Modelo X",
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


@pytest.fixture
def repos():
    return criar_repositorios_memoria()


# ----------------------------------------------------------------------------- IDs


def test_ulid_formato_e_ordem_monotonica_no_mesmo_instante() -> None:
    ids = [novo_ulid(T0) for _ in range(50)]
    assert all(eh_ulid(i) for i in ids)
    assert ids == sorted(ids)
    assert len(set(ids)) == 50


# ----------------------------------------------------------------------------- Jornadas


def test_criar_jornada_duplicada_nao_sobrescreve(repos) -> None:
    assert repos.jornadas.criar(jornada()).aplicado
    outra = repos.jornadas.criar(Jornada("J1", T0, T0, "busca", "busca"))
    assert not outra.aplicado and outra.registro.origem == "qr"
    assert repos.jornadas.obter("J1").origem == "qr"


def test_mutacao_em_jornada_inexistente_levanta(repos) -> None:
    with pytest.raises(ErroNaoEncontrado):
        repos.jornadas.marcar_guia_respondeu_nao("nada")


def test_marcar_risco_e_monotonico(repos) -> None:
    repos.jornadas.criar(jornada())
    primeira = repos.jornadas.marcar_risco("J1", "lista", T0)
    segunda = repos.jornadas.marcar_risco("J1", "ia", T0 + timedelta(minutes=1))
    assert primeira.aplicado and not segunda.aplicado
    assert segunda.registro.risco.origem == "lista"
    assert segunda.registro.risco.em == T0


def test_limite_de_chamadas_ao_modelo_permite_a_decima_e_recusa_a_seguinte(repos) -> None:
    repos.jornadas.criar(jornada())
    resultados = [repos.jornadas.incrementar_msgs_modelo("J1", 10) for _ in range(11)]
    assert [r.aplicado for r in resultados] == [True] * 10 + [False]
    assert repos.jornadas.obter("J1").msgs_modelo == 10


@given(n=st.integers(min_value=0, max_value=30), limite=st.integers(min_value=1, max_value=12))
def test_propriedade_contador_nunca_ultrapassa_o_limite(n: int, limite: int) -> None:
    r = criar_repositorios_memoria()
    r.jornadas.criar(jornada())
    aceitas = sum(r.jornadas.incrementar_msgs_modelo("J1", limite).aplicado for _ in range(n))
    assert aceitas == min(n, limite)
    assert r.jornadas.obter("J1").msgs_modelo == min(n, limite)


def test_contadores_de_negativas_e_frustracao(repos) -> None:
    repos.jornadas.criar(jornada())
    repos.jornadas.incrementar_ia_nao("J1")
    assert repos.jornadas.incrementar_ia_nao("J1").ia_nao == 2
    assert repos.jornadas.atualizar_frustracao("J1", "alta").frustracao_alta_seq == 1
    assert repos.jornadas.atualizar_frustracao("J1", "alta").frustracao_alta_seq == 2
    assert repos.jornadas.atualizar_frustracao("J1", "média").frustracao_alta_seq == 0


def test_custo_ia_acumula_com_quatro_casas(repos) -> None:
    repos.jornadas.criar(jornada())
    repos.jornadas.somar_custo_ia("J1", Decimal("0.01234"))
    j = repos.jornadas.somar_custo_ia("J1", Decimal("0.0001"))
    assert j.custo_ia_brl == Decimal("0.0124")
    with pytest.raises(ValueError):
        repos.jornadas.somar_custo_ia("J1", Decimal("-1"))


def test_primeira_selecao_do_problema_so_conta_uma_vez(repos) -> None:
    repos.jornadas.criar(jornada())
    assert repos.jornadas.registrar_problema_selecionado("J1", 7) is True
    assert repos.jornadas.registrar_problema_selecionado("J1", 7) is False
    assert repos.jornadas.registrar_problema_selecionado("J1", 3) is True
    assert repos.jornadas.obter("J1").problemas_selecionados == (7, 3)


def test_encerrar_jornada_so_a_primeira_camada_vence(repos) -> None:
    repos.jornadas.criar(jornada())
    primeiro = repos.jornadas.encerrar("J1", "guia", T0 + timedelta(minutes=5))
    segundo = repos.jornadas.encerrar("J1", "ia", T0 + timedelta(minutes=9))
    assert primeiro.aplicado and not segundo.aplicado
    j = repos.jornadas.obter("J1")
    assert j.estado == "encerrada" and j.encerramento.camada == "guia"
    assert (j.encerrada_pk, j.ativa_pk) == ("ENC", None)
    assert j.encerrada_em == T0 + timedelta(minutes=5)


def test_abandono_e_terminal_e_respeita_os_30_minutos(repos) -> None:
    repos.jornadas.criar(jornada())
    assert not repos.jornadas.marcar_abandono("J1", T0 + timedelta(minutes=29)).aplicado
    assert repos.jornadas.marcar_abandono("J1", T0 + timedelta(minutes=30)).aplicado
    assert not repos.jornadas.encerrar("J1", "ia", T0 + timedelta(hours=1)).aplicado
    j = repos.jornadas.registrar_interacao("J1", T0 + timedelta(hours=2))
    assert j.encerramento.camada == "abandonada"
    assert j.ultima_interacao == T0


def test_listagens_dos_indices_esparsos(repos) -> None:
    for jid, minutos in (("A", 10), ("B", 40), ("C", 50)):
        repos.jornadas.criar(jornada(jid, T0 + timedelta(minutes=minutos)))
    ate = T0 + timedelta(minutes=45)
    assert [j.jornada_id for j in repos.jornadas.listar_ativas_sem_interacao_ate(ate)] == ["A", "B"]
    repos.jornadas.encerrar("A", "guia", T0 + timedelta(hours=2))
    repos.jornadas.encerrar("B", "ia", T0 + timedelta(hours=1))
    assert [j.jornada_id for j in repos.jornadas.listar_ativas_sem_interacao_ate(ate)] == []
    ids = [j.jornada_id for j in repos.jornadas.listar_encerradas(T0, T0 + timedelta(hours=2))]
    assert ids == ["B", "A"]
    assert repos.jornadas.listar_encerradas(T0, T0 + timedelta(minutes=30)) == []


# ----------------------------------------------------------------------------- Eventos


def test_evento_e_idempotente_por_evento_id(repos) -> None:
    eid = novo_ulid(T0)
    original = Evento("J1", eid, "passo_exibido", T0, {"passo": 1})
    reenvio = Evento("J1", eid, "passo_exibido", T0 + timedelta(seconds=5), {"passo": 99})
    assert repos.eventos.registrar(original) is True
    assert repos.eventos.registrar(reenvio) is False
    eventos = repos.eventos.listar("J1")
    assert len(eventos) == 1 and eventos[0].dados == {"passo": 1}


def test_eventos_voltam_em_ordem_cronologica_e_isolados_por_jornada(repos) -> None:
    ids = [novo_ulid(T0 + timedelta(seconds=i)) for i in range(3)]
    for eid in reversed(ids):
        repos.eventos.registrar(Evento("J1", eid, "x", T0))
    repos.eventos.registrar(Evento("J2", novo_ulid(T0), "x", T0))
    assert [e.evento_id for e in repos.eventos.listar("J1")] == ids


def test_evento_exige_ulid() -> None:
    with pytest.raises(ValueError):
        Evento("J1", "nao-e-ulid", "x", T0)


# ----------------------------------------------------------------------------- Chamados


def test_criar_com_escalada_grava_chamado_e_marca_a_jornada(repos) -> None:
    repos.jornadas.criar(jornada())
    r = repos.chamados.criar_com_escalada(chamado(numero(1)), gatilho(), decisao("P3"))
    assert r.criado and r.motivo == "criado"
    j = repos.jornadas.obter("J1")
    assert j.estado == "escalada" and j.ativa_pk is None
    assert j.escalada.chamado_numero == numero(1)
    assert [g.tipo for g in j.escalada.gatilhos] == ["pedido_humano"]
    assert repos.chamados.obter(numero(1)) is not None


def test_um_chamado_por_jornada(repos) -> None:
    repos.jornadas.criar(jornada())
    repos.chamados.criar_com_escalada(chamado(numero(1)), gatilho(), decisao("P3"))
    r = repos.chamados.criar_com_escalada(
        chamado(numero(2)), gatilho("sem_embasamento"), decisao("P3")
    )
    assert not r.criado and r.motivo == "jornada_ja_escalada"
    assert r.numero_existente == numero(1)
    assert repos.chamados.obter(numero(2)) is None
    assert len(repos.chamados.listar_fila()) == 1


def test_criar_com_escalada_e_tudo_ou_nada(repos) -> None:
    # Jornada inexistente: nada é gravado.
    r = repos.chamados.criar_com_escalada(chamado(numero(1), "FANTASMA"), gatilho(), decisao("P3"))
    assert (r.criado, r.motivo) == (False, "jornada_inexistente")
    assert repos.chamados.obter(numero(1)) is None
    # Número em uso por outra Jornada: a segunda Jornada não é marcada.
    repos.jornadas.criar(jornada("J1"))
    repos.jornadas.criar(jornada("J2"))
    repos.chamados.criar_com_escalada(chamado(numero(1), "J1"), gatilho(), decisao("P3"))
    r = repos.chamados.criar_com_escalada(chamado(numero(1), "J2"), gatilho(), decisao("P3"))
    assert (r.criado, r.motivo) == (False, "numero_em_uso")
    assert repos.jornadas.obter("J2").escalada is None
    assert repos.chamados.obter(numero(1)).jornada_id == "J1"


def test_chamado_novo_precisa_estar_aberto(repos) -> None:
    repos.jornadas.criar(jornada())
    encerrado = replace(chamado(numero(1)), status="encerrado")
    with pytest.raises(ErroRepositorio):
        repos.chamados.criar_com_escalada(encerrado, gatilho(), decisao("P3"))
    assert repos.jornadas.obter("J1").escalada is None


def test_jornada_encerrada_mantem_estado_ao_ganhar_chamado(repos) -> None:
    repos.jornadas.criar(jornada())
    repos.jornadas.encerrar("J1", "guia", T0 + timedelta(minutes=2))
    r = repos.chamados.criar_com_escalada(
        chamado(numero(1)), gatilho("risco_seguranca"), decisao("P1")
    )
    assert r.criado
    j = repos.jornadas.obter("J1")
    assert j.estado == "encerrada" and j.encerramento.camada == "guia"
    assert j.escalada.chamado_numero == numero(1)


def test_gatilho_adicional_so_em_jornada_escalada(repos) -> None:
    repos.jornadas.criar(jornada())
    assert not repos.jornadas.registrar_gatilho_adicional("J1", gatilho()).aplicado
    repos.chamados.criar_com_escalada(chamado(numero(1)), gatilho(), decisao("P3"))
    r = repos.jornadas.registrar_gatilho_adicional("J1", gatilho("frustracao_alta"))
    assert r.aplicado
    assert [g.tipo for g in r.registro.escalada.gatilhos] == ["pedido_humano", "frustracao_alta"]


def test_assumir_chamado_so_o_primeiro_vence(repos) -> None:
    repos.jornadas.criar(jornada())
    repos.chamados.criar_com_escalada(chamado(numero(1)), gatilho(), decisao("P3"))
    a = repos.chamados.assumir(numero(1), "bruno", "Bruno", T0)
    b = repos.chamados.assumir(numero(1), "carla", "Carla", T0 + timedelta(seconds=1))
    assert a.aplicado and a.registro.status == "em_atendimento"
    assert not b.aplicado
    assert b.registro.responsavel.nome == "Bruno"
    assert repos.chamados.obter(numero(1)).responsavel.usuario == "bruno"


def test_fila_ordena_por_prioridade_horario_e_numero_e_exclui_encerrados(repos) -> None:
    casos = [
        (numero(3), "P3", 0),
        (numero(2), "P2", 5),
        (numero(1), "P1", 10),
        (numero(4), "P2", 1),
    ]
    for i, (num, prio, minutos) in enumerate(casos):
        jid = f"J{i}"
        repos.jornadas.criar(jornada(jid))
        c = chamado(num, jid, prio, T0 + timedelta(minutes=minutos))
        repos.chamados.criar_com_escalada(c, gatilho(), decisao(prio))
    ordem = [c.numero for c in repos.chamados.listar_fila()]
    assert ordem == [numero(1), numero(4), numero(2), numero(3)]
    enc = EncerramentoChamado("falso_defeito", "outra", "ok", T0, "bruno")
    assert repos.chamados.encerrar(numero(1), enc).aplicado
    assert numero(1) not in [c.numero for c in repos.chamados.listar_fila()]
    assert repos.chamados.obter(numero(1)).fila_sk is None


STATUS_CHAMADO = ("aberto", "em_atendimento", "encerrado")


@given(
    casos=st.dictionaries(
        keys=st.integers(min_value=0, max_value=1023),
        values=st.tuples(
            st.sampled_from(STATUS_CHAMADO),
            st.sampled_from(("P1", "P2", "P3")),
            st.integers(min_value=0, max_value=3),  # poucos minutos: força empates em criado_em
        ),
        max_size=12,
    )
)
def test_propriedade_listar_todos_devolve_todos_ordenados_sem_alterar_a_fila(casos) -> None:
    """Feature: persistencia-local-demo, Property 10: `listar_todos` devolve todos os Chamados

    **Validates: Requirements 8.1, 8.2, 8.4**
    """
    r = criar_repositorios_memoria()
    assert r.chamados.listar_todos() == []  # repositório vazio (8.4)

    for i, (status, prio, minutos) in casos.items():
        jid, num = f"J{i}", numero(i)
        r.jornadas.criar(jornada(jid))
        c = chamado(num, jid, prio, T0 + timedelta(minutes=minutos))
        assert r.chamados.criar_com_escalada(c, gatilho(), decisao(prio)).criado
        if status == "em_atendimento":
            assert r.chamados.assumir(num, "bruno", "Bruno", T0).aplicado
        elif status == "encerrado":
            enc = EncerramentoChamado("falso_defeito", "outra", "ok", T0, "bruno")
            assert r.chamados.encerrar(num, enc).aplicado

    todos = r.chamados.listar_todos()
    esperado = sorted(
        (r.chamados.obter(numero(i)) for i in casos), key=lambda c: (c.criado_em, c.numero)
    )
    # Todos os status presentes, sem perder encerrados, na ordem (criado_em, numero) (8.1, 8.2).
    assert todos == esperado
    assert {c.numero: c.status for c in todos} == {numero(i): s for i, (s, _, _) in casos.items()}

    # listar_fila continua só com os não encerrados (8.3): mesmo conjunto de `listar_todos` sem encerrados.
    fila = r.chamados.listar_fila()
    assert len(fila) == len({c.numero for c in fila})
    assert {c.numero for c in fila} == {c.numero for c in todos if c.status != "encerrado"}

    # Ler não altera o estado: nova chamada devolve o mesmo resultado.
    assert r.chamados.listar_todos() == todos


def test_encerrar_chamado_so_o_primeiro_vence(repos) -> None:
    repos.jornadas.criar(jornada())
    repos.chamados.criar_com_escalada(chamado(numero(1)), gatilho(), decisao("P3"))
    primeiro = EncerramentoChamado("defeito_real", "outra", "troca", T0, "bruno")
    segundo = EncerramentoChamado("falso_defeito", "outra", "outra coisa", T0, "carla")
    assert repos.chamados.encerrar(numero(1), primeiro).aplicado
    r = repos.chamados.encerrar(numero(1), segundo)
    assert not r.aplicado and r.registro.encerramento.por == "bruno"
    assert not repos.chamados.assumir(numero(1), "carla", "Carla", T0).aplicado


def test_reavaliar_eleva_a_prioridade_e_nunca_reduz(repos) -> None:
    repos.jornadas.criar(jornada())
    repos.chamados.criar_com_escalada(chamado(numero(1), prioridade="P3"), gatilho(), decisao("P3"))
    sobe = repos.chamados.reavaliar(numero(1), decisao("P1"), pacote(numero(1), "P1"))
    assert sobe.aplicado and sobe.registro.prioridade == "P1"
    assert sobe.registro.fila_sk.startswith("P1#")
    assert repos.jornadas.obter("J1").escalada.decisao.prioridade == "P1"
    desce = repos.chamados.reavaliar(numero(1), decisao("P2"), pacote(numero(1), "P2"))
    igual = repos.chamados.reavaliar(numero(1), decisao("P1"), pacote(numero(1), "P1"))
    assert not desce.aplicado and not igual.aplicado
    assert repos.chamados.obter(numero(1)).prioridade == "P1"
    with pytest.raises(ErroRepositorio):
        repos.chamados.reavaliar(numero(1), decisao("P1"), pacote(numero(1), "P3"))


def test_campos_de_ia_nao_desfazem_reavaliacao_e_o_pacote_segue_valido(repos) -> None:
    repos.jornadas.criar(jornada())
    repos.chamados.criar_com_escalada(chamado(numero(1)), gatilho(), decisao("P3"))
    repos.chamados.reavaliar(numero(1), decisao("P1"), pacote(numero(1), "P1"))
    c = repos.chamados.atualizar_campos_ia(
        numero(1), "Cliente sem café há dois dias.", "frustração alta", "Ligar agora.", "ok"
    )
    assert c.pacote.prioridade == "P1" and c.pacote.resumo.startswith("Cliente")
    assert c.pacote_ia_status == "ok"
    with pytest.raises(ErroRepositorio):
        repos.chamados.atualizar_campos_ia(numero(1), "x" * 301, "neutro", "Ligar.", "ok")
    assert repos.chamados.obter(numero(1)).pacote.resumo.startswith("Cliente")


def test_anexos_respeitam_o_maximo_e_entram_no_pacote(repos) -> None:
    repos.jornadas.criar(jornada())
    repos.chamados.criar_com_escalada(chamado(numero(1)), gatilho(), decisao("P3"))
    resultados = [
        repos.chamados.adicionar_anexo(numero(1), AnexoChamado(f"fotos/{i}.jpg", "image/jpeg", 10))
        for i in range(4)
    ]
    assert [r.aplicado for r in resultados] == [True, True, True, False]
    c = repos.chamados.obter(numero(1))
    assert len(c.anexos) == 3 and len(c.pacote.anexos) == 3


def test_flags_simples_do_chamado(repos) -> None:
    repos.jornadas.criar(jornada())
    repos.chamados.criar_com_escalada(chamado(numero(1)), gatilho(), decisao("P3"))
    assert repos.chamados.marcar_alerta_p1_visto(numero(1)).alerta_p1_visto
    assert repos.chamados.definir_resposta_nao_lida(numero(1), True).resposta_nao_lida
    assert repos.chamados.definir_os_status(numero(1), "ok").os_status == "ok"
    quando = T0 + timedelta(days=1)
    assert repos.chamados.definir_agendamento(numero(1), quando).agendamento == quando


# ----------------------------------------------------------------------------- Mensagens, PII


def test_mensagens_preservam_a_ordem_de_criacao_no_mesmo_instante(repos) -> None:
    textos = [f"m{i}" for i in range(20)]
    for t in textos:
        repos.mensagens.adicionar(numero(1), "atendente", t, T0)
    assert [m.texto for m in repos.mensagens.listar(numero(1))] == textos
    assert repos.mensagens.listar(numero(2)) == []


def test_marcar_lidas_so_do_autor_pedido(repos) -> None:
    repos.mensagens.adicionar(numero(1), "atendente", "a", T0)
    repos.mensagens.adicionar(numero(1), "consumidor", "b", T0)
    assert repos.mensagens.marcar_lidas(numero(1), "consumidor") == 1
    assert repos.mensagens.marcar_lidas(numero(1), "consumidor") == 0
    lidas = {m.texto: m.lida for m in repos.mensagens.listar(numero(1))}
    assert lidas == {"a": False, "b": True}


def test_dados_pessoais_preservam_o_que_ja_foi_informado(repos) -> None:
    consentimento = Consentimento(T0, "v1")
    repos.dados_pessoais.salvar(numero(1), consentimento, telefone="11999998888")
    r = repos.dados_pessoais.salvar(numero(1), consentimento, cep="01310100")
    assert (r.telefone, r.cep) == ("11999998888", "01310100")
    assert repos.dados_pessoais.obter(numero(9)) is None


def test_acesso_pii_registra_com_resolucao_de_segundos(repos) -> None:
    repos.acessos_pii.registrar(numero(1), "bruno", T0.replace(microsecond=987654))
    repos.acessos_pii.registrar(numero(1), "carla", T0 + timedelta(seconds=3))
    acessos = repos.acessos_pii.listar(numero(1))
    assert [(a.atendente_id, a.em.microsecond) for a in acessos] == [("bruno", 0), ("carla", 0)]


# ----------------------------------------------------------------------------- OS, cache, avaliação


def test_uma_ordem_de_servico_por_chamado_com_chave_deterministica(repos) -> None:
    os1 = OrdemServico(numero(1), "Modelo X", "S1", "nao_liga")
    primeira = repos.ordens_servico.criar_rascunho(os1)
    segunda = repos.ordens_servico.criar_rascunho(OrdemServico(numero(1), "Outro", "S2", "outro"))
    assert primeira.aplicado and not segunda.aplicado
    assert segunda.registro.modelo == "Modelo X"
    assert os1.os_id == f"OS#{numero(1)}"
    assert repos.ordens_servico.confirmar(numero(1)).registro.status == "aberta"
    assert not repos.ordens_servico.confirmar(numero(1)).aplicado
    with pytest.raises(ErroNaoEncontrado):
        repos.ordens_servico.confirmar(numero(7))


def test_cache_exige_aprovador_e_nao_duplica(repos) -> None:
    sem = EntradaCache("m1", "Como limpar o bico?", "Passe um pano.", None, None)
    r = repos.cache.inserir(sem)
    assert r.status is StatusInsercao.REJEITADA_SEM_APROVADOR
    chave = chave_cache("m1", "Como limpar o bico?")
    assert repos.cache.obter(chave) is None

    com = EntradaCache("m1", "Como limpar o bico?", "Passe um pano.", "bruno", T0)
    assert repos.cache.inserir(com, fontes=[{"manual": "M", "secao": "4.2"}]).aceita
    rep = repos.cache.inserir(
        EntradaCache("m1", "como limpar o BICO", "Outra resposta", "carla", T0)
    )
    assert rep.status is StatusInsercao.DUPLICADA
    registro = repos.cache.obter(chave)
    assert registro.resposta == "Passe um pano." and registro.aprovador_id == "bruno"
    assert registro.pergunta_normalizada == "como limpar o bico"
    assert registro.fontes == ({"manual": "M", "secao": "4.2"},)
    assert repos.cache.registrar_hit(chave) == 1 and repos.cache.registrar_hit(chave) == 2


def test_cache_separa_modelos(repos) -> None:
    for modelo in ("m1", "m2"):
        assert repos.cache.inserir(EntradaCache(modelo, "pergunta", "r", "bruno", T0)).aceita


def test_uma_avaliacao_por_jornada(repos) -> None:
    primeira = repos.avaliacoes.registrar(Avaliacao("J1", 5, "guia", T0, "ótimo"))
    segunda = repos.avaliacoes.registrar(Avaliacao("J1", 1, "ia", T0, "péssimo"))
    assert primeira.aplicado and not segunda.aplicado
    assert repos.avaliacoes.obter("J1").nota == 5
    assert repos.avaliacoes.listar_periodo(T0, T0) == [primeira.registro]
    with pytest.raises(ValueError):
        Avaliacao("J2", 6, "guia", T0)
    with pytest.raises(ValueError):
        Avaliacao("J2", 3, "guia", T0, "x" * 501)


# -------------------------------------------------------------- Agregados, CS, config


def test_agregados_contam_por_dia_e_metrica(repos) -> None:
    d1, d2 = date(2025, 1, 1), date(2025, 1, 2)
    assert repos.agregados.incrementar(d1, "ia_cache") == 1
    assert repos.agregados.incrementar(d1, "ia_cache", 4) == 5
    repos.agregados.incrementar(d2, "problema_sel#7")
    assert repos.agregados.obter(d1, "ia_modelo") == 0
    assert [(a.dia, a.metrica, a.valor) for a in repos.agregados.listar(d1, d2)] == [
        ("2025-01-01", "ia_cache", 5),
        ("2025-01-02", "problema_sel#7", 1),
    ]
    assert len(repos.agregados.listar(d2, d2)) == 1
    with pytest.raises(ValueError):
        repos.agregados.incrementar(d1, "x", 0)


def test_usuarios_cs_janela_de_falhas_e_bloqueio(repos) -> None:
    u = UsuarioCS("bruno", "hash", "atendente")
    assert repos.usuarios_cs.criar(u).aplicado
    assert not repos.usuarios_cs.criar(UsuarioCS("bruno", "outro", "gestor")).aplicado
    janela = timedelta(minutes=15)
    repos.usuarios_cs.registrar_falha("bruno", T0, janela)
    repos.usuarios_cs.registrar_falha("bruno", T0 + timedelta(minutes=10), janela)
    atual = repos.usuarios_cs.registrar_falha("bruno", T0 + timedelta(minutes=20), janela)
    assert len(atual.falhas) == 2  # a de T0 saiu da janela de 15 min
    ate = T0 + timedelta(minutes=35)
    assert repos.usuarios_cs.bloquear("bruno", ate).bloqueado_ate == ate
    assert repos.usuarios_cs.limpar_falhas("bruno").falhas == ()
    assert repos.usuarios_cs.definir_senha("bruno", "novo").hash_senha == "novo"
    assert repos.usuarios_cs.perfil_de("bruno") == "atendente"
    assert repos.usuarios_cs.perfil_de("ninguem") is None


def test_sessao_expira_com_mais_de_30_minutos_sem_atividade(repos) -> None:
    inatividade = timedelta(minutes=30)
    repos.sessoes.criar(SessaoCS("h1", "bruno", "atendente", T0, 0))
    viva = repos.sessoes.renovar("h1", T0 + timedelta(minutes=30), inatividade)
    assert viva is not None and viva.ultima_atividade == T0 + timedelta(minutes=30)
    assert viva.ttl == int((T0 + timedelta(minutes=60)).timestamp())
    # 30 min e 1 s depois da última atividade: vencida e removida.
    assert repos.sessoes.renovar("h1", T0 + timedelta(minutes=60, seconds=1), inatividade) is None
    assert repos.sessoes.obter("h1") is None
    assert repos.sessoes.renovar("inexistente", T0, inatividade) is None


def test_logout_remove_a_sessao(repos) -> None:
    repos.sessoes.criar(SessaoCS("h1", "bruno", "gestor", T0, 0))
    assert repos.sessoes.encerrar("h1") is True
    assert repos.sessoes.encerrar("h1") is False


def test_config_copia_valores_mutaveis(repos) -> None:
    termos = ["fumaca", "choque"]
    repos.config.definir("termos_risco", termos)
    termos.append("x")
    lido = repos.config.obter("termos_risco")
    assert lido == ["fumaca", "choque"]
    lido.append("y")
    assert repos.config.obter("termos_risco") == ["fumaca", "choque"]
    repos.config.definir("limite_msgs_modelo", 10)
    assert repos.config.listar() == {"termos_risco": ["fumaca", "choque"], "limite_msgs_modelo": 10}
    assert repos.config.obter("nao_existe") is None
