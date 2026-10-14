"""Testes do Serializador da demo local (scripts/estado_demo.py), sem AWS e sem servidor.

Este módulo guarda as estratégias (Hypothesis) e os helpers reutilizados pelas próximas
propriedades do mesmo arquivo: `estados()` gera um `EstadoPersistido` válido com todos os
registros reais (com seus `__post_init__`), e `assinatura()` compara valores de forma mais
estrita que `==` (tipos, `tuple` x `list`, casas do `Decimal` e texto ISO do `datetime`).
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator
from dataclasses import MISSING, fields, is_dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, get_args, get_origin, get_type_hints

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from estado_demo import (  # isort: skip (também prepara o sys.path de services/api e dominio)
    EXCLUIDOS,
    NOME_SNAPSHOT,
    PERSISTIDOS,
    ErroSerializacao,
    ErroSnapshot,
    EstadoPersistido,
    Persistencia,
    aplicar_estado,
    capturar_estado,
    ler_estado,
    serializar_estado,
)
from dominio import ItemJaTentado, JornadaEncerrada, PacoteRepasse  # noqa: E402
from repositorios.catalogo import CatalogoMemoria, ModeloCatalogo, ProblemaCatalogo  # noqa: E402
from repositorios.interfaces import Repositorios  # noqa: E402
from repositorios.memoria import criar_repositorios_memoria  # noqa: E402
from dominio.pacote import Anexo  # noqa: E402
from repositorios.modelos import (  # noqa: E402
    AcessoPII,
    AgregadoDia,
    AnexoChamado,
    Avaliacao,
    Chamado,
    Consentimento,
    DadosPessoaisRegistro,
    DecisaoRegistrada,
    EncerramentoChamado,
    EscaladaJornada,
    Evento,
    GatilhoRegistrado,
    Jornada,
    MensagemChamado,
    OrdemServico,
    RegistroCache,
    Responsavel,
    RiscoMarcado,
    SessaoCS,
    UsuarioCS,
)
from servicos import senhas  # noqa: E402

CAMINHO_FICTICIO = Path("estado.json")

PERFIL = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)

# ----------------------------------------------------------------------------- helpers


def assinatura(valor: Any) -> Any:
    """Estrutura comparável que distingue o que `==` esconde (Decimal('1.0') x Decimal('1'),
    tuple x list, int x float x bool, fusos diferentes com o mesmo instante)."""
    if is_dataclass(valor) and not isinstance(valor, type):
        return (
            type(valor).__name__,
            tuple((f.name, assinatura(getattr(valor, f.name))) for f in fields(valor)),
        )
    if isinstance(valor, Decimal):
        return ("Decimal", valor.as_tuple())
    if isinstance(valor, datetime):
        return ("datetime", valor.isoformat())
    if isinstance(valor, list | tuple):
        return (type(valor).__name__, [assinatura(v) for v in valor])
    if isinstance(valor, dict):
        return ("dict", [(k, assinatura(v)) for k, v in valor.items()])
    if isinstance(valor, float):
        return ("float", repr(valor))
    return (type(valor).__name__, valor)


def ida_e_volta(estado: EstadoPersistido) -> EstadoPersistido:
    """`EstadoPersistido` -> texto do snapshot -> `EstadoPersistido`."""
    return ler_estado(serializar_estado(estado), CAMINHO_FICTICIO)


# ----------------------------------------------------------------------------- estratégias

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

textos = st.text(max_size=12)
textos_nao_vazios = st.text(min_size=1, max_size=12)
inteiros = st.integers(min_value=0, max_value=10**6)


def ulids() -> st.SearchStrategy[str]:
    """ULID válido para `eh_ulid`: primeiro caractere de 0 a 7 e 25 do alfabeto Crockford."""
    return st.builds(
        lambda cabeca, cauda: cabeca + cauda,
        st.sampled_from("01234567"),
        st.text(alphabet=_CROCKFORD, min_size=25, max_size=25),
    )


def numeros_chamado() -> st.SearchStrategy[str]:
    return st.text(alphabet=_CROCKFORD, min_size=10, max_size=10).map(lambda s: f"TRES-{s}")


def fusos() -> st.SearchStrategy[timezone]:
    """UTC e deslocamentos fixos em minutos inteiros (de -23:59 a +23:59).

    Fusos fixos de propósito: com `zoneinfo`, horários repetidos pelo horário de verão
    comparam como diferentes entre fusos distintos, o que não é problema do Serializador.
    """
    deslocamentos = st.integers(min_value=-(23 * 60 + 59), max_value=23 * 60 + 59).map(
        lambda m: timezone(timedelta(minutes=m))
    )
    return st.one_of(st.just(timezone.utc), deslocamentos)


def datas() -> st.SearchStrategy[datetime]:
    """`datetime` com fuso e microssegundos arbitrários."""
    return st.datetimes(
        min_value=datetime(2000, 1, 1),
        max_value=datetime(2100, 1, 1),
        timezones=fusos(),
    )


def decimais() -> st.SearchStrategy[Decimal]:
    """`Decimal` finitos com sinal, dígitos e expoente livres (inclui zeros à direita)."""
    return st.builds(
        lambda sinal, digitos, expoente: Decimal((sinal, digitos, expoente)),
        st.integers(min_value=0, max_value=1),
        st.lists(st.integers(min_value=0, max_value=9), min_size=1, max_size=20).map(tuple),
        st.integers(min_value=-12, max_value=12),
    )


def json_nativos() -> st.SearchStrategy[Any]:
    """Valores de campos `Any`: só o que o JSON representa (sem tuple, sem NaN)."""
    folhas = st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-(10**12), max_value=10**12),
        st.floats(allow_nan=False, allow_infinity=False),
        textos,
    )
    return st.recursive(
        folhas,
        lambda filhos: st.one_of(
            st.lists(filhos, max_size=3),
            st.dictionaries(textos, filhos, max_size=3),
        ),
        max_leaves=8,
    )


def dicts_json() -> st.SearchStrategy[dict[str, Any]]:
    return st.dictionaries(textos, json_nativos(), max_size=3)


def opcional[T](estrategia: st.SearchStrategy[T]) -> st.SearchStrategy[T | None]:
    return st.one_of(st.none(), estrategia)


def tuplas[T](
    estrategia: st.SearchStrategy[T], max_size: int = 3
) -> st.SearchStrategy[tuple[T, ...]]:
    return st.lists(estrategia, max_size=max_size).map(tuple)


prioridades = st.sampled_from(["P1", "P2", "P3"])
classificacoes = st.sampled_from(["provável defeito", "provável uso"])
gatilhos = st.sampled_from(
    [
        "risco_seguranca",
        "duas_negativas_ia",
        "pedido_humano",
        "sem_embasamento",
        "frustracao_alta",
        "limite_mensagens",
        "instrucao_sem_solucao",
    ]
)
origens = st.sampled_from(["qr", "busca"])
camadas = st.sampled_from(["guia", "ia", "humano", "abandonada"])
mimes = st.sampled_from(["image/jpeg", "image/png"])


def itens_ja_tentados() -> st.SearchStrategy[ItemJaTentado]:
    return st.builds(
        ItemJaTentado,
        passo=textos,
        camada=st.sampled_from(["guia", "ia"]),
        resultado=st.sampled_from(["sim", "não", "sem resposta"]),
    )


def pacotes() -> st.SearchStrategy[PacoteRepasse]:
    return st.builds(
        PacoteRepasse,
        numero_chamado=numeros_chamado(),
        modelo=textos,
        numero_serie=textos,
        origem=origens,
        categoria=textos,
        resumo=textos,
        ja_tentado=tuplas(itens_ja_tentados()),
        classificacao=classificacoes,
        prioridade=prioridades,
        canal_recomendado=textos,
        sentimento=st.sampled_from(["neutro", "frustração moderada", "frustração alta"]),
        anexos=tuplas(st.builds(Anexo, chave=textos, mime=mimes)),
        proxima_acao=textos,
    )


def jornadas_encerradas() -> st.SearchStrategy[JornadaEncerrada]:
    return st.builds(
        JornadaEncerrada,
        jornada_id=ulids(),
        camada=camadas,
        encerrada_em=datas(),
        tempo_s=inteiros,
        custo_brl=decimais(),
        problema_id=opcional(inteiros),
        desfecho=opcional(textos),
    )


def escaladas() -> st.SearchStrategy[EscaladaJornada]:
    gatilho = st.builds(GatilhoRegistrado, tipo=gatilhos, em=datas(), registrado=st.booleans())
    decisao = st.builds(
        DecisaoRegistrada,
        prioridade=prioridades,
        classificacao=classificacoes,
        canal=textos,
        criterio=st.sampled_from([1, 2, 3]),
        em=datas(),
    )
    return st.builds(
        EscaladaJornada,
        chamado_numero=numeros_chamado(),
        em=datas(),
        gatilhos=tuplas(gatilho),
        decisao=decisao,
    )


def jornadas() -> st.SearchStrategy[Jornada]:
    return st.builds(
        Jornada,
        jornada_id=ulids(),
        criada_em=datas(),
        ultima_interacao=datas(),
        origem=origens,
        origem_inicial=origens,
        estado=st.sampled_from(["ativa", "escalada", "encerrada"]),
        modelo_id=opcional(textos),
        numero_serie=opcional(textos),
        problema_id=opcional(inteiros),
        problemas_selecionados=tuplas(inteiros),
        seletor_area=opcional(textos),
        seletor_estado=opcional(textos),
        risco=opcional(
            st.builds(RiscoMarcado, origem=st.sampled_from(["lista", "ia", "guia"]), em=datas())
        ),
        guia_respondeu_nao=st.booleans(),
        msgs_modelo=inteiros,
        ia_nao=inteiros,
        frustracao_alta_seq=inteiros,
        custo_ia_brl=decimais(),
        escalada=opcional(escaladas()),
        encerramento=opcional(jornadas_encerradas()),
    )


def eventos() -> st.SearchStrategy[Evento]:
    return st.builds(
        Evento,
        jornada_id=ulids(),
        evento_id=ulids(),
        tipo=textos,
        em=datas(),
        dados=dicts_json(),
    )


def chamados() -> st.SearchStrategy[Chamado]:
    responsavel = st.builds(Responsavel, usuario=textos, nome=textos, inicio=datas())
    anexo = st.builds(AnexoChamado, chave=textos, mime=mimes, bytes=inteiros)
    encerramento = st.builds(
        EncerramentoChamado,
        desfecho=st.sampled_from(["falso_defeito", "defeito_real"]),
        solucao_tipo=st.sampled_from(["instrução do manual", "outra"]),
        solucao=textos,
        em=datas(),
        por=textos,
    )
    return st.builds(
        Chamado,
        numero=numeros_chamado(),
        jornada_id=ulids(),
        criado_em=datas(),
        prioridade=prioridades,
        classificacao=classificacoes,
        canal=textos,
        decisao_criterio=st.sampled_from([1, 2, 3]),
        pacote=pacotes(),
        status=st.sampled_from(["aberto", "em_atendimento", "encerrado"]),
        pacote_ia_status=st.sampled_from(["pendente", "ok", "fallback"]),
        gatilho_nao_registrado=st.booleans(),
        responsavel=opcional(responsavel),
        alerta_p1_visto=st.booleans(),
        resposta_nao_lida=st.booleans(),
        os_status=st.sampled_from(["ok", "falha", "nao_aplicavel"]),
        agendamento=opcional(datas()),
        anexos=tuplas(anexo),
        encerramento=opcional(encerramento),
    )


def mensagens() -> st.SearchStrategy[MensagemChamado]:
    return st.builds(
        MensagemChamado,
        numero=numeros_chamado(),
        ts_ulid=ulids(),
        autor=st.sampled_from(["atendente", "consumidor"]),
        texto=textos,
        em=datas(),
        lida=st.booleans(),
    )


def dados_pessoais() -> st.SearchStrategy[DadosPessoaisRegistro]:
    return st.builds(
        DadosPessoaisRegistro,
        numero=numeros_chamado(),
        consentimento=st.builds(Consentimento, em=datas(), versao_finalidade=textos),
        telefone=opcional(textos),
        cep=opcional(textos),
    )


def acessos_pii() -> st.SearchStrategy[AcessoPII]:
    return st.builds(
        AcessoPII, numero=numeros_chamado(), ts_ulid=ulids(), atendente_id=textos, em=datas()
    )


def ordens_servico() -> st.SearchStrategy[OrdemServico]:
    return st.builds(
        OrdemServico,
        numero=numeros_chamado(),
        modelo=textos,
        numero_serie=textos,
        categoria=textos,
        ja_tentado=tuplas(itens_ja_tentados()),
        status=st.sampled_from(["rascunho", "aberta"]),
    )


def registros_cache() -> st.SearchStrategy[RegistroCache]:
    return st.builds(
        RegistroCache,
        chave=textos,
        modelo_id=textos,
        pergunta_normalizada=textos,
        pergunta=textos,
        resposta=textos,
        aprovador_id=textos,
        aprovado_em=opcional(datas()),
        fontes=tuplas(dicts_json()),
        hits=inteiros,
    )


def avaliacoes() -> st.SearchStrategy[Avaliacao]:
    return st.builds(
        Avaliacao,
        jornada_id=ulids(),
        nota=st.integers(min_value=1, max_value=5),
        camada=st.sampled_from(["guia", "ia", "humano"]),
        em=datas(),
        comentario=st.text(max_size=40),
    )


def agregados() -> st.SearchStrategy[AgregadoDia]:
    return st.builds(
        AgregadoDia,
        dia=st.dates().map(lambda d: d.isoformat()),
        metrica=textos,
        valor=inteiros,
    )


def estados() -> st.SearchStrategy[EstadoPersistido]:
    """`EstadoPersistido` válido, com todas as coleções (inclusive vazias)."""

    def lista(estrategia: st.SearchStrategy[Any]) -> st.SearchStrategy[list[Any]]:
        return st.lists(estrategia, max_size=3)

    return st.builds(
        EstadoPersistido,
        jornadas=lista(jornadas()),
        eventos=lista(eventos()),
        chamados=lista(chamados()),
        mensagens=lista(mensagens()),
        dados_pessoais=lista(dados_pessoais()),
        acessos_pii=lista(acessos_pii()),
        ordens_servico=lista(ordens_servico()),
        cache=lista(registros_cache()),
        avaliacoes=lista(avaliacoes()),
        agregados=lista(agregados()),
        config=dicts_json(),
    )


# ----------------------------------------------------------------------------- Property 1


@PERFIL
@given(estado=estados())
def test_propriedade_ida_e_volta_do_estado_persistido(estado: EstadoPersistido) -> None:
    """Feature: persistencia-local-demo, Property 1: Ida e volta do Estado_Persistido

    **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6**
    """
    texto = serializar_estado(estado)
    lido = ler_estado(texto, CAMINHO_FICTICIO)

    assert lido == estado
    # Mais estrito que `==`: mesmos tipos (tuple x list), casas do Decimal e fusos.
    assert assinatura(lido) == assinatura(estado)
    # O texto é estável: serializar o que foi lido reproduz exatamente o mesmo snapshot.
    assert serializar_estado(lido) == texto


# ----------------------------------------------------------------------------- Property 2

SENHA_DEMO = "demo-tres-2025"
_HASH_SENHA_DEMO = senhas.gerar_hash(SENHA_DEMO)  # calculado uma vez (Argon2id/scrypt é lento)

# Marcadores longos e improváveis: nenhum texto gerado pelas estratégias de estado os produz,
# então a presença de um deles no snapshot só pode vir de um vazamento real.
_ALFABETO = "abcdefghijklmnopqrstuvwxyz0123456789"
_sufixos = st.text(alphabet=_ALFABETO, min_size=4, max_size=10)

CAMPOS_EXCLUIDOS = frozenset({"hash_senha", "token_hash", "usuarios_cs", "sessoes", "catalogo"})


def _chaves_de_objetos(valor: Any) -> Iterator[str]:
    """Todos os nomes de campo (chaves de objeto JSON) em qualquer profundidade."""
    if isinstance(valor, dict):
        for chave, filho in valor.items():
            yield chave
            yield from _chaves_de_objetos(filho)
    elif isinstance(valor, list):
        for filho in valor:
            yield from _chaves_de_objetos(filho)


@st.composite
def repositorios_com_segredos(draw: st.DrawFn) -> tuple[Repositorios, dict[str, list[str]]]:
    """Repositórios em memória com estado gerado + usuários, hashes, sessões e catálogo.

    Devolve também os textos sensíveis (por categoria) que nunca podem ir ao snapshot.
    """
    repos = criar_repositorios_memoria()
    aplicar_estado(repos, draw(estados()))

    sensiveis: dict[str, list[str]] = {
        "usuario": [],
        "hash_senha": [],
        "token_hash": [],
        "sessao_usuario": [],
        "catalogo": [],
    }

    nomes = draw(st.lists(_sufixos, min_size=1, max_size=4, unique=True))
    for i, sufixo in enumerate(nomes):
        usuario = f"zqxusuario-{sufixo}"
        # O primeiro usuário usa o hash real da Senha_Demo; os demais, hashes sintéticos.
        hash_senha = (
            _HASH_SENHA_DEMO if i == 0 else f"$argon2id$v=19$zqxhash-{sufixo}$zqxsal-{sufixo}"
        )
        repos.usuarios_cs.criar(
            UsuarioCS(
                usuario=usuario,
                hash_senha=hash_senha,
                perfil=draw(st.sampled_from(["atendente", "gestor"])),
                falhas=draw(tuplas(datas(), max_size=2)),
                bloqueado_ate=draw(opcional(datas())),
                deve_trocar_senha=draw(st.booleans()),
            )
        )
        sensiveis["usuario"].append(usuario)
        sensiveis["hash_senha"].append(hash_senha)

    for sufixo in draw(st.lists(_sufixos, max_size=3, unique=True)):
        token_hash = f"zqxtoken-{sufixo}-" + "ab" * 16
        usuario = draw(st.sampled_from(nomes))
        repos.sessoes.criar(
            SessaoCS(
                token_hash=token_hash,
                usuario=f"zqxusuario-{usuario}",
                perfil="gestor",
                ultima_atividade=draw(datas()),
                ttl=draw(inteiros),
            )
        )
        sensiveis["token_hash"].append(token_hash)

    titulos = [f"zqxtitulo-{s}" for s in draw(st.lists(_sufixos, min_size=1, max_size=4, unique=True))]
    nomes_modelo = [f"zqxmodelo-{s}" for s in draw(st.lists(_sufixos, max_size=3, unique=True))]
    problemas = [
        ProblemaCatalogo(problema_id=i + 1, ordem=i + 1, titulo=t, icone="i", icone_alt="a")
        for i, t in enumerate(titulos)
    ]
    modelos = [
        ModeloCatalogo(modelo_id=f"zqxid-{i}", nome=n, nome_normalizado=n)
        for i, n in enumerate(nomes_modelo)
    ]
    object.__setattr__(repos, "catalogo", CatalogoMemoria(modelos, problemas))
    sensiveis["catalogo"] = titulos + nomes_modelo + [m.modelo_id for m in modelos]
    return repos, sensiveis


@PERFIL
@given(dados=repositorios_com_segredos())
def test_propriedade_segredos_e_catalogo_ficam_fora_do_snapshot(
    dados: tuple[Repositorios, dict[str, list[str]]],
) -> None:
    """Feature: persistencia-local-demo, Property 2: Usuários, hashes, sessões e catálogo ficam fora do snapshot

    **Validates: Requirements 4.7, 4.8, 5.4**
    """
    repos, sensiveis = dados

    # Os segredos realmente estão nos repositórios (a propriedade não é vazia).
    assert repos.usuarios_cs.obter(sensiveis["usuario"][0]) is not None
    assert repos.catalogo.listar_problemas()

    texto = serializar_estado(capturar_estado(repos))

    for categoria, valores in sensiveis.items():
        for valor in valores:
            assert valor not in texto, f"{categoria} vazou no snapshot: {valor!r}"
    assert SENHA_DEMO not in texto
    assert _HASH_SENHA_DEMO not in texto
    # Nomes dos campos dos registros excluídos também não aparecem como chave de objeto.
    # Só as CHAVES contam: um texto igual a "usuarios_cs" pode ser um valor legítimo
    # gerado pelo Hypothesis (ex.: proxima_acao="usuarios_cs").
    assert not CAMPOS_EXCLUIDOS & set(_chaves_de_objetos(json.loads(texto)))

    # As chaves do estado gravado são exatamente os repositórios classificados como persistidos.
    assert set(json.loads(texto)["estado"]) == PERSISTIDOS


def test_classificacao_cobre_todos_os_repositorios() -> None:
    """Todo campo de `Repositorios` é persistido ou excluído, e nunca os dois."""
    nomes = {f.name for f in fields(Repositorios)}

    assert nomes == PERSISTIDOS | EXCLUIDOS
    assert not PERSISTIDOS & EXCLUIDOS
    assert EXCLUIDOS == {"usuarios_cs", "sessoes", "catalogo"}


# ----------------------------------------------------------------------------- exemplos


def _jornada_minima(**campos: Any) -> Jornada:
    momento = datetime(2025, 3, 10, 12, 0, 0, 123456, tzinfo=timezone(timedelta(hours=-3)))
    base: dict[str, Any] = {
        "jornada_id": "01JDEMO0000000000000000P10",
        "criada_em": momento,
        "ultima_interacao": momento,
        "origem": "qr",
        "origem_inicial": "qr",
    }
    return Jornada(**{**base, **campos})


def test_tuple_volta_como_tuple_e_nao_como_list() -> None:
    estado = EstadoPersistido(jornadas=[_jornada_minima(problemas_selecionados=(6, 2, 9))])

    lido = ida_e_volta(estado)

    assert lido.jornadas[0].problemas_selecionados == (6, 2, 9)
    assert type(lido.jornadas[0].problemas_selecionados) is tuple


def test_decimal_preserva_todas_as_casas() -> None:
    estado = EstadoPersistido(jornadas=[_jornada_minima(custo_ia_brl=Decimal("0.045000"))])

    texto = serializar_estado(estado)
    lido = ida_e_volta(estado)

    assert '"custo_ia_brl": "0.045000"' in texto  # texto, sem passar por float
    assert str(lido.jornadas[0].custo_ia_brl) == "0.045000"
    assert lido.jornadas[0].custo_ia_brl.as_tuple() == Decimal("0.045000").as_tuple()


def test_datetime_preserva_fuso_e_microssegundos() -> None:
    estado = EstadoPersistido(jornadas=[_jornada_minima()])

    texto = serializar_estado(estado)
    criada_em = ida_e_volta(estado).jornadas[0].criada_em

    assert "2025-03-10T12:00:00.123456-03:00" in texto
    assert criada_em.microsecond == 123456
    assert criada_em.utcoffset() == timedelta(hours=-3)


# ----------------------------------------------------------------------------- Property 3

MARCADOR_INVALIDO = "zqx_invalido"


def valores_invalidos() -> st.SearchStrategy[tuple[Any, str, str]]:
    """(valor de tipo desconhecido, tipo esperado no erro, sufixo esperado no caminho)."""
    chaves_nao_string = st.one_of(
        st.integers(),
        st.floats(allow_nan=False),
        st.none(),
        st.booleans(),
        st.binary(max_size=4),
        st.tuples(st.integers(), st.integers()),
    )
    return st.one_of(
        st.just((object(), "object", "")),
        st.sets(st.integers(), max_size=3).map(lambda v: (v, "set", "")),
        st.binary(max_size=6).map(lambda v: (v, "bytes", "")),
        st.datetimes().map(lambda v: (v, "datetime sem fuso", "")),
        st.sampled_from([Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")]).map(
            lambda v: (v, "Decimal não finito", "")
        ),
        st.sampled_from([float("inf"), float("-inf"), float("nan")]).map(
            lambda v: (v, "float não finito", "")
        ),
        chaves_nao_string.map(lambda k: ({k: 1}, f"chave {type(k).__name__}", f".{k}")),
    )


@st.composite
def estados_com_valor_invalido(draw: st.DrawFn) -> tuple[EstadoPersistido, str, str, str]:
    """Estado válido com UM valor de tipo desconhecido num campo de tipo livre.

    Devolve (estado, alvo, tipo esperado, sufixo esperado do caminho).
    """
    estado = draw(estados())
    valor, tipo, sufixo = draw(valores_invalidos())
    alvo = draw(st.sampled_from(["evento", "config", "cache"]))

    if alvo == "evento":
        base = draw(eventos())
        ruim = replace(base, dados={**base.dados, MARCADOR_INVALIDO: valor})
        estado = replace(estado, eventos=[*estado.eventos, ruim])
    elif alvo == "cache":
        base = draw(registros_cache())
        ruim = replace(base, fontes=(*base.fontes, {MARCADOR_INVALIDO: valor}))
        estado = replace(estado, cache=[*estado.cache, ruim])
    else:
        estado = replace(estado, config={**estado.config, MARCADOR_INVALIDO: valor})
    return estado, alvo, tipo, sufixo


def _caminho_esperado(capturado: EstadoPersistido, alvo: str, sufixo: str) -> str:
    """Caminho do campo inválido no estado capturado (os repositórios deduplicam por chave)."""
    if alvo == "config":
        return f"config.{MARCADOR_INVALIDO}{sufixo}"
    if alvo == "evento":
        i = next(i for i, e in enumerate(capturado.eventos) if MARCADOR_INVALIDO in e.dados)
        return f"eventos[{i}].dados.{MARCADOR_INVALIDO}{sufixo}"
    i, j = next(
        (i, j)
        for i, r in enumerate(capturado.cache)
        for j, f in enumerate(r.fontes)
        if MARCADOR_INVALIDO in f
    )
    return f"cache[{i}].fontes[{j}].{MARCADOR_INVALIDO}{sufixo}"


@PERFIL
@given(anterior=estados(), invalido=estados_com_valor_invalido())
def test_propriedade_valor_desconhecido_nao_corrompe_o_snapshot(
    anterior: EstadoPersistido,
    invalido: tuple[EstadoPersistido, str, str, str],
) -> None:
    """Feature: persistencia-local-demo, Property 3: Valor de tipo desconhecido não corrompe o snapshot

    **Validates: Requirements 4.9**
    """
    estado_ruim, alvo, tipo, sufixo = invalido

    repos = criar_repositorios_memoria()
    aplicar_estado(repos, anterior)

    with tempfile.TemporaryDirectory() as tmp:
        mensagens_log: list[str] = []
        persistencia = Persistencia(Path(tmp) / "dados", log=mensagens_log.append)

        # Snapshot anterior válido já gravado.
        assert persistencia.gravar(repos) is True
        bytes_anteriores = persistencia.caminho.read_bytes()

        # O estado em memória passa a conter o valor desconhecido.
        aplicar_estado(repos, estado_ruim)
        capturado = capturar_estado(repos)
        campo = _caminho_esperado(capturado, alvo, sufixo)

        # O Serializador identifica o campo e o tipo.
        with pytest.raises(ErroSerializacao) as info:
            serializar_estado(capturado)
        assert info.value.campo == campo
        assert info.value.tipo == tipo
        assert repr(campo) in str(info.value)  # a mensagem traz o caminho via repr
        assert tipo in str(info.value)

        # A gravação falha sem levantar, sem tocar o snapshot e sem deixar o temporário.
        assert persistencia.gravar(repos) is False
        assert persistencia.caminho.read_bytes() == bytes_anteriores
        assert not persistencia.temporario.exists()
        assert sorted(p.name for p in persistencia.diretorio.iterdir()) == [NOME_SNAPSHOT]

        # O erro foi registrado com o caminho do arquivo e o campo, sem o conteúdo do estado.
        assert len(mensagens_log) == 1
        assert str(persistencia.caminho) in mensagens_log[0]
        assert repr(campo) in mensagens_log[0]


# ----------------------------------------------------------------------------- Property 4

CAMINHO_SNAPSHOT_FICTICIO = Path("/tmp/zqx-dados-demo/estado.json")

TIPOS_CORRUPCAO = (
    "truncado",
    "malformado",
    "versao_diferente",
    "versao_ausente",
    "campo_removido",
    "campo_desconhecido",
    "tipo_trocado",
    "literal_fora_do_dominio",
    "datetime_sem_fuso",
)

_DICAS_ESTADO = get_type_hints(EstadoPersistido)
_LISTAS = tuple(f.name for f in fields(EstadoPersistido) if f.name != "config")


def _classe_do_registro(lista: str) -> type:
    return get_args(_DICAS_ESTADO[lista])[0]


def _folhas(tipo: Any) -> set[Any]:
    """Tipos-folha de uma anotação (sem `None` nem `...`); `Literal[...]` conta como `Literal`."""
    origem = get_origin(tipo)
    if origem is None:
        return set() if tipo is type(None) else {tipo}
    if origem is Literal:
        return {Literal}
    folhas: set[Any] = set()
    for arg in get_args(tipo):
        if arg is not Ellipsis:
            folhas |= _folhas(arg)
    return folhas


def _campos_de_registro(lista: str) -> list[tuple[str, Any, bool]]:
    """(nome, anotação, obrigatório) dos campos do registro de uma lista do estado."""
    cls = _classe_do_registro(lista)
    dicas = get_type_hints(cls)
    return [
        (f.name, dicas[f.name], f.default is MISSING and f.default_factory is MISSING)
        for f in fields(cls)
    ]


def _valor_de_tipo_errado(anotacao: Any) -> Any:
    """Valor JSON que nenhuma alternativa da anotação aceita (sem `Any`)."""
    folhas = _folhas(anotacao)
    if folhas & {str, datetime, Decimal, Literal}:
        return 12345  # número onde se espera texto, data, decimal ou Literal
    return "zqx"  # texto onde se espera int, bool, lista, objeto ou registro


@st.composite
def snapshots_corrompidos(draw: st.DrawFn) -> tuple[str, str, str | None]:
    """Snapshot válido de `estados()` com UMA corrupção.

    Devolve (texto corrompido, tipo de corrupção, trecho que a mensagem deve conter ou None).
    """
    texto = serializar_estado(draw(estados()))
    corpo = json.loads(texto)
    registros = corpo["estado"]
    tipo = draw(st.sampled_from(TIPOS_CORRUPCAO))

    def indices(lista: str) -> list[int]:
        return list(range(len(registros[lista])))

    # Candidatos (lista, índice, campo, anotação) por tipo de corrupção em nível de registro.
    candidatos: dict[str, list[tuple[str, int, str, Any]]] = {
        "campo_removido": [],
        "tipo_trocado": [],
        "literal_fora_do_dominio": [],
        "datetime_sem_fuso": [],
    }
    for lista in _LISTAS:
        for nome, anotacao, obrigatorio in _campos_de_registro(lista):
            folhas = _folhas(anotacao)
            for i in indices(lista):
                if obrigatorio:
                    candidatos["campo_removido"].append((lista, i, nome, anotacao))
                if Any not in folhas:
                    candidatos["tipo_trocado"].append((lista, i, nome, anotacao))
                if folhas == {Literal}:
                    candidatos["literal_fora_do_dominio"].append((lista, i, nome, anotacao))
                if folhas == {datetime} and get_origin(anotacao) not in (tuple, list, dict):
                    candidatos["datetime_sem_fuso"].append((lista, i, nome, anotacao))

    # Sem registro que sirva (estado quase vazio): cai na remoção de uma lista do estado.
    if tipo in candidatos and not candidatos[tipo]:
        tipo = "campo_removido_no_estado"

    trecho: str | None = None
    if tipo == "truncado":
        corte = draw(st.integers(min_value=0, max_value=len(texto.rstrip()) - 1))
        saida = texto[:corte]
    elif tipo == "malformado":
        saida = draw(
            st.sampled_from(
                [
                    texto + "}",
                    "zqx" + texto,
                    texto.replace('"versao"', "versao", 1),
                    '{"versao": 1, "estado": NaN}',
                    "[1, 2]",
                    "null",
                    "",
                ]
            )
        )
    else:
        if tipo == "versao_diferente":
            corpo["versao"] = draw(
                st.sampled_from([0, 2, -1, 1000, "1", 1.5, True, None, [], {}, "zqx"])
            )
        elif tipo == "versao_ausente":
            del corpo["versao"]
        elif tipo == "campo_removido_no_estado":
            lista = draw(st.sampled_from(sorted(PERSISTIDOS)))
            del registros[lista]
            trecho = f"estado.{lista}"
            tipo = "campo_removido"
        elif tipo == "campo_desconhecido":
            alvo = draw(st.sampled_from(["raiz", "estado", "registro"]))
            if alvo == "registro" and any(registros[lista] for lista in _LISTAS):
                lista = draw(st.sampled_from([x for x in _LISTAS if registros[x]]))
                i = draw(st.sampled_from(indices(lista)))
                registros[lista][i]["zqx_desconhecido"] = draw(json_nativos())
                trecho = f"estado.{lista}[{i}].zqx_desconhecido"
            elif alvo == "estado":
                registros["zqx_desconhecido"] = draw(json_nativos())
                trecho = "estado.zqx_desconhecido"
            else:
                corpo["zqx_desconhecido"] = draw(json_nativos())
                trecho = "zqx_desconhecido"
        else:
            lista, i, nome, anotacao = draw(st.sampled_from(candidatos[tipo]))
            registro = registros[lista][i]
            trecho = f"estado.{lista}[{i}].{nome}"
            if tipo == "campo_removido":
                del registro[nome]
            elif tipo == "tipo_trocado":
                registro[nome] = _valor_de_tipo_errado(anotacao)
            elif tipo == "literal_fora_do_dominio":
                registro[nome] = "zqx_fora_do_dominio"
            else:  # datetime_sem_fuso
                registro[nome] = draw(st.datetimes()).isoformat()
        saida = json.dumps(corpo, ensure_ascii=False, indent=2)
    return saida, tipo, trecho


@PERFIL
@given(corrompido=snapshots_corrompidos())
def test_propriedade_snapshot_invalido_e_rejeitado_sem_alteracao(
    corrompido: tuple[str, str, str | None],
) -> None:
    """Feature: persistencia-local-demo, Property 4: Snapshot inválido é rejeitado sem alteração

    **Validates: Requirements 2.6, 4.11**
    """
    texto, tipo, trecho = corrompido

    # ler_estado: sempre ErroSnapshot (nunca outra exceção), com o caminho na mensagem.
    with pytest.raises(ErroSnapshot) as info:
        ler_estado(texto, CAMINHO_SNAPSHOT_FICTICIO)
    assert info.value.caminho == CAMINHO_SNAPSHOT_FICTICIO
    assert str(CAMINHO_SNAPSHOT_FICTICIO) in str(info.value), tipo
    if trecho is not None:  # corrupção estrutural: a mensagem aponta o campo
        assert trecho in str(info.value), (tipo, str(info.value))

    # Persistencia.carregar sobre o arquivo corrompido: ErroSnapshot e bytes intactos.
    with tempfile.TemporaryDirectory() as tmp:
        persistencia = Persistencia(Path(tmp))
        persistencia.caminho.write_bytes(texto.encode("utf-8"))
        antes = persistencia.caminho.read_bytes()

        with pytest.raises(ErroSnapshot) as info_arquivo:
            persistencia.carregar()
        assert info_arquivo.value.caminho == persistencia.caminho
        assert str(persistencia.caminho) in str(info_arquivo.value)

        assert persistencia.caminho.read_bytes() == antes
        assert sorted(p.name for p in persistencia.diretorio.iterdir()) == [NOME_SNAPSHOT]


# ----------------------------------------------------------------------------- Property 5

FALHAS = ("open", "write", "fsync", "replace")
MARCADOR_CONTEUDO = "zqx-conteudo-secreto"


class _ArquivoComFalhaNaEscrita:
    """Arquivo real cuja escrita grava só metade do texto e levanta `OSError`.

    Deixa um `estado.json.tmp` parcial em disco, para provar que a limpeza acontece.
    """

    def __init__(self, arquivo: Any) -> None:
        self._arquivo = arquivo

    def __enter__(self) -> _ArquivoComFalhaNaEscrita:
        return self

    def __exit__(self, *_: object) -> None:
        self._arquivo.close()

    def write(self, texto: str) -> int:
        self._arquivo.write(texto[: len(texto) // 2])
        self._arquivo.flush()
        raise OSError("falha injetada na escrita")

    def flush(self) -> None:
        self._arquivo.flush()

    def fileno(self) -> int:
        return self._arquivo.fileno()


def _gravar_com_falha(persistencia: Persistencia, repos: Repositorios, falha: str | None) -> bool:
    """Chama `Persistencia.gravar` com a falha injetada no ponto indicado (ou sem falha)."""
    import builtins
    import os
    from unittest import mock

    def erro(mensagem: str) -> Any:
        def levantar(*_: object, **__: object) -> Any:
            raise OSError(mensagem)

        return levantar

    def abrir_com_falha_na_escrita(*args: Any, **kwargs: Any) -> _ArquivoComFalhaNaEscrita:
        return _ArquivoComFalhaNaEscrita(builtins.open(*args, **kwargs))

    if falha is None:
        return persistencia.gravar(repos)
    if falha == "open":
        with mock.patch("estado_demo.open", erro("falha injetada no open"), create=True):
            return persistencia.gravar(repos)
    if falha == "write":
        with mock.patch("estado_demo.open", abrir_com_falha_na_escrita, create=True):
            return persistencia.gravar(repos)
    if falha == "fsync":
        with mock.patch.object(os, "fsync", erro("falha injetada no fsync")):
            return persistencia.gravar(repos)
    with mock.patch.object(os, "replace", erro("falha injetada no os.replace")):
        return persistencia.gravar(repos)


@PERFIL
@given(
    passos=st.lists(
        st.tuples(estados(), st.one_of(st.none(), st.sampled_from(FALHAS))),
        min_size=1,
        max_size=4,
    ),
    snapshot_previo=st.one_of(st.none(), estados()),
)
def test_propriedade_gravacao_atomica(
    passos: list[tuple[EstadoPersistido, str | None]],
    snapshot_previo: EstadoPersistido | None,
) -> None:
    """Feature: persistencia-local-demo, Property 5: Gravação atômica

    **Validates: Requirements 1.3, 1.4, 5.3**
    """
    repos = criar_repositorios_memoria()

    with tempfile.TemporaryDirectory() as tmp:
        mensagens_log: list[str] = []
        persistencia = Persistencia(Path(tmp) / "dados", log=mensagens_log.append)

        # Texto do último snapshot gravado com sucesso (None: o arquivo ainda não existe).
        ultimo_texto: str | None = None
        if snapshot_previo is not None:
            aplicar_estado(repos, snapshot_previo)
            assert persistencia.gravar(repos) is True
            ultimo_texto = serializar_estado(capturar_estado(repos))
            assert persistencia.caminho.read_text(encoding="utf-8") == ultimo_texto

        for estado, falha in passos:
            # O marcador prova que o log nunca traz o conteúdo do estado.
            aplicar_estado(
                repos, replace(estado, config={**estado.config, "zqx": MARCADOR_CONTEUDO})
            )
            capturado = capturar_estado(repos)
            texto = serializar_estado(capturado)
            bytes_antes = persistencia.caminho.read_bytes() if persistencia.caminho.exists() else None
            logs_antes = len(mensagens_log)

            resultado = _gravar_com_falha(persistencia, repos, falha)  # nunca levanta

            if falha is None:
                assert resultado is True
                assert persistencia.caminho.read_text(encoding="utf-8") == texto
                assert persistencia.carregar() == capturado
                ultimo_texto = texto
                assert len(mensagens_log) == logs_antes
            else:
                assert resultado is False
                # Snapshot anterior byte a byte intacto (ou ainda inexistente).
                if bytes_antes is None:
                    assert not persistencia.caminho.exists()
                else:
                    assert persistencia.caminho.read_bytes() == bytes_antes
                # O erro foi registrado com o caminho, sem o conteúdo do estado.
                novos = mensagens_log[logs_antes:]
                assert len(novos) == 1
                assert str(persistencia.caminho) in novos[0]
                assert MARCADOR_CONTEUDO not in novos[0]
                assert texto not in novos[0]

            # Invariantes a cada passo (Req 1.3, 1.4, 5.3).
            assert not persistencia.temporario.exists()
            nomes = {p.name for p in persistencia.diretorio.iterdir()}
            assert nomes <= {NOME_SNAPSHOT}
            if ultimo_texto is None:
                assert nomes == set()
            else:
                assert nomes == {NOME_SNAPSHOT}
                assert persistencia.caminho.read_text(encoding="utf-8") == ultimo_texto


# ----------------------------------------------------------------------------- Persistencia (exemplos)
#
# A classificação de `Repositorios` em PERSISTIDOS | EXCLUIDOS já é conferida por
# `test_classificacao_cobre_todos_os_repositorios` (Req 4.7, 4.8), acima.


def test_gravar_cria_o_diretorio_com_os_pais(tmp_path: Path) -> None:
    """Req 1.7: o diretório de dados e os pais ausentes são criados na primeira gravação."""
    destino = tmp_path / "a" / "b" / "c"
    persistencia = Persistencia(destino)
    assert not (tmp_path / "a").exists()

    assert persistencia.gravar(criar_repositorios_memoria()) is True

    assert destino.is_dir()
    assert persistencia.caminho == destino / NOME_SNAPSHOT
    assert persistencia.caminho.is_file()
    assert not persistencia.temporario.exists()
    assert persistencia.carregar() == EstadoPersistido()


def test_gravar_preserva_acentos_no_arquivo(tmp_path: Path) -> None:
    """`ensure_ascii=False`: acentos ficam legíveis no arquivo, sem escapes `\\uXXXX`."""
    repos = criar_repositorios_memoria()
    repos.config.definir("mensagem", "ação não é opção: açaí, coração, São João")
    persistencia = Persistencia(tmp_path)

    assert persistencia.gravar(repos) is True

    texto = persistencia.caminho.read_bytes().decode("utf-8")
    assert "ação não é opção: açaí, coração, São João" in texto
    assert "\\u" not in texto
    assert persistencia.carregar().config == {"mensagem": "ação não é opção: açaí, coração, São João"}


def test_apagar_sem_arquivos_nao_levanta(tmp_path: Path) -> None:
    persistencia = Persistencia(tmp_path / "ainda-nao-existe")

    persistencia.apagar()  # nem o diretório existe
    persistencia.apagar()  # idempotente

    assert not persistencia.caminho.exists()
    assert not persistencia.temporario.exists()


def test_apagar_remove_snapshot_e_temporario(tmp_path: Path) -> None:
    persistencia = Persistencia(tmp_path)
    assert persistencia.gravar(criar_repositorios_memoria()) is True
    persistencia.temporario.write_text("sobra de uma gravação interrompida", encoding="utf-8")
    assert persistencia.caminho.exists() and persistencia.temporario.exists()

    persistencia.apagar()

    assert not persistencia.caminho.exists()
    assert not persistencia.temporario.exists()
    assert list(tmp_path.iterdir()) == []


def test_gravacao_concorrente_produz_json_valido_igual_ao_estado_final(tmp_path: Path) -> None:
    """Req 1.6: gravações simultâneas são serializadas; o arquivo nunca fica corrompido."""
    import threading

    repos = criar_repositorios_memoria()
    persistencia = Persistencia(tmp_path / "dados", log=lambda _: None)
    n_threads, n_rodadas = 8, 15
    dia = datetime(2025, 3, 10).date()
    resultados: list[bool] = []
    leituras_invalidas: list[Exception] = []
    terminou = threading.Event()
    largada = threading.Barrier(n_threads)

    def escritor(indice: int) -> None:
        largada.wait()
        for _ in range(n_rodadas):
            repos.agregados.incrementar(dia, f"metrica-{indice}")  # o estado muda...
            resultados.append(persistencia.gravar(repos))  # ...e grava em seguida

    def leitor() -> None:
        # Leitura concorrente: o os.replace é atômico, então sempre há um snapshot íntegro.
        while not terminou.is_set():
            if persistencia.caminho.exists():
                try:
                    persistencia.carregar()
                except Exception as erro:  # noqa: BLE001
                    leituras_invalidas.append(erro)

    threads = [threading.Thread(target=escritor, args=(i,)) for i in range(n_threads)]
    observador = threading.Thread(target=leitor)
    observador.start()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    terminou.set()
    observador.join(timeout=60)

    assert not any(t.is_alive() for t in threads)
    assert resultados == [True] * (n_threads * n_rodadas)
    assert leituras_invalidas == []

    # O arquivo final é JSON válido e idêntico ao estado final dos repositórios.
    texto = persistencia.caminho.read_text(encoding="utf-8")
    json.loads(texto)
    final = capturar_estado(repos)
    assert texto == serializar_estado(final)
    assert persistencia.carregar() == final
    assert {(a.metrica, a.valor) for a in final.agregados} == {
        (f"metrica-{i}", n_rodadas) for i in range(n_threads)
    }
    assert sorted(p.name for p in persistencia.diretorio.iterdir()) == [NOME_SNAPSHOT]


def test_carregar_arquivo_ausente_vira_erro_snapshot(tmp_path: Path) -> None:
    persistencia = Persistencia(tmp_path)

    with pytest.raises(ErroSnapshot) as info:
        persistencia.carregar()

    assert info.value.caminho == persistencia.caminho
    assert str(persistencia.caminho) in str(info.value)


def test_carregar_arquivo_ilegivel_vira_erro_snapshot(tmp_path: Path) -> None:
    # Bytes que não são UTF-8 válido.
    persistencia = Persistencia(tmp_path / "bytes")
    persistencia.diretorio.mkdir()
    persistencia.caminho.write_bytes(b'{"versao": 1, "estado": "\xff\xfe"}')
    antes = persistencia.caminho.read_bytes()

    with pytest.raises(ErroSnapshot) as info_bytes:
        persistencia.carregar()
    assert info_bytes.value.caminho == persistencia.caminho
    assert "UTF-8" in str(info_bytes.value)
    assert persistencia.caminho.read_bytes() == antes

    # O caminho do snapshot é um diretório: a leitura levanta OSError.
    persistencia_dir = Persistencia(tmp_path / "dir")
    persistencia_dir.caminho.mkdir(parents=True)

    with pytest.raises(ErroSnapshot) as info_dir:
        persistencia_dir.carregar()
    assert info_dir.value.caminho == persistencia_dir.caminho
    assert str(persistencia_dir.caminho) in str(info_dir.value)
