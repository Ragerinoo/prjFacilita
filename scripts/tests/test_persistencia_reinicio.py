"""Reinício da demo local (scripts/dev_local.py + scripts/estado_demo.py), sem AWS e sem HTTP.

O arquivo guarda os helpers reutilizados pelas propriedades de reinício (Property 6 a 9):

- `carregar_dev_local()`: carrega `scripts/dev_local.py` via importlib (como `test_dev_local.py`);
- `AmbienteDemo`: aplicação montada com relógio injetado e `Persistencia` ligada. `chamar()` roda
  `core.processar` e, depois de qualquer método fora de GET/HEAD, grava o snapshot (o mesmo que o
  Handler faz). `reiniciar()` recria a aplicação com `iniciar_estado` no MESMO diretório;
- `operacoes()` / `executar()`: sequências de operações geradas pelo Hypothesis (Jornadas,
  escaladas, assumir, mensagens, contato, agendamento, Ordem_Servico, encerramento, avaliação);
- `observar()`: tudo o que o Painel_CS enxerga (estado capturado, fila, `listar_todos`,
  mensagens por Chamado, métricas e a fila da API).

As estratégias de registros e o `assinatura()` vêm de `test_estado_demo.py`. Tudo roda em diretório
temporário: o `.dados-demo/` do repositório nunca é tocado.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from test_estado_demo import PERFIL, assinatura  # isort: skip (também prepara o sys.path)
from estado_demo import (  # noqa: E402
    EstadoPersistido,
    Persistencia,
    capturar_estado,
)

CAMINHO_DEV_LOCAL = Path(__file__).resolve().parent.parent / "dev_local.py"
T0 = datetime(2025, 3, 10, 12, 0, 0, 123456, tzinfo=UTC)
SENHA = "senha-de-teste-reinicio-1"
USUARIOS = ("atendente", "gestor")
MODELOS = ("tres-passione", "tres-circo", "tres-mimo")
TELEFONES = ("11987654321", "21999998888")
CEPS = ("01310100", "20040020")

_modulo_dev_local: ModuleType | None = None


def carregar_dev_local() -> ModuleType:
    """`scripts/dev_local.py` carregado uma vez por importlib (também prepara o `sys.path`)."""
    global _modulo_dev_local
    if _modulo_dev_local is None:
        spec = importlib.util.spec_from_file_location("dev_local_reinicio", CAMINHO_DEV_LOCAL)
        assert spec is not None and spec.loader is not None
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        _modulo_dev_local = modulo
    return _modulo_dev_local


# ----------------------------------------------------------------------------- ambiente


class Relogio:
    """Relógio injetado: só anda quando o teste manda."""

    def __init__(self, agora: datetime = T0) -> None:
        self.agora = agora

    def __call__(self) -> datetime:
        return self.agora

    def avancar(self, delta: timedelta) -> None:
        self.agora += delta


@dataclass
class Resposta:
    status: int
    corpo: Any
    cookies: list[str] = field(default_factory=list)


@dataclass
class AmbienteDemo:
    """Uma subida da demo: aplicação + Persistencia no `dir_dados`, com relógio injetado."""

    dir_dados: Path
    relogio: Relogio = field(default_factory=Relogio)
    com_demo: bool = False
    resetar: bool = False
    espiar: bool = False
    situacao: str = field(init=False, default="")
    chamadas_espionadas: list[str] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self.modulo = carregar_dev_local()
        # import tardio: `core` precisa ser carregado antes de `servicos.autenticacao`
        from servicos.autenticacao import COOKIE_SESSAO

        self.nome_cookie = COOKIE_SESSAO
        self.persistencia = Persistencia(self.dir_dados, log=lambda _linha: None)
        self.app = self.modulo.criar_app(
            {"TRES_LOG_NIVEL": "CRITICAL"}, modo="local", relogio=self.relogio
        )
        self.roteador = self.modulo.criar_roteador()
        self.cookies: dict[str, str] = {}
        if self.espiar:
            self._espiar_mutadores()
        self.situacao = self.modulo.iniciar_estado(
            self.app,
            SENHA,
            self.persistencia,
            resetar=self.resetar,
            com_demo=self.com_demo,
        )

    # ---- espiões: a carga não pode chamar escalar/assumir/encerrar (Req 7.5) ----------------

    def _espiar_mutadores(self) -> None:
        alvos: list[tuple[Any, str, str]] = [
            (self.app.repos.chamados, "criar_com_escalada", "chamados.criar_com_escalada"),
            (self.app.repos.chamados, "assumir", "chamados.assumir"),
            (self.app.repos.chamados, "encerrar", "chamados.encerrar"),
            (self.app.escalada, "escalar", "escalada.escalar"),
            (self.app.escalada, "marcar_risco", "escalada.marcar_risco"),
        ]
        for objeto, nome, rotulo in alvos:
            original = objeto.__dict__.get(nome) or getattr(objeto, nome)

            def espiao(*args: Any, _o: Callable[..., Any] = original, _r: str = rotulo, **kw: Any):
                self.chamadas_espionadas.append(_r)
                return _o(*args, **kw)

            setattr(objeto, nome, espiao)

    # ---- HTTP sem socket: o mesmo caminho do Handler ----------------------------------------

    def chamar(
        self, metodo: str, caminho: str, corpo: Any = None, *, quem: str | None = None
    ) -> Resposta:
        cabecalhos = {"x-requested-with": "tres"}
        if quem is not None:
            cabecalhos["cookie"] = f"{self.nome_cookie}={self.cookies[quem]}"
        evento: dict[str, Any] = {
            "version": "2.0",
            "rawPath": caminho,
            "rawQueryString": "",
            "headers": cabecalhos,
            "requestContext": {"requestId": "r", "http": {"method": metodo, "path": caminho}},
            "isBase64Encoded": False,
        }
        if corpo is not None:
            evento["body"] = json.dumps(corpo)
        bruto = self.modulo.processar(self.app, self.roteador, evento)
        if metodo not in self.modulo.METODOS_LEITURA:
            self.persistencia.gravar(self.app.repos)  # como o Handler: antes de responder
        texto = bruto.get("body")
        return Resposta(
            int(bruto["statusCode"]),
            json.loads(texto) if texto else None,
            list(bruto.get("cookies") or []),
        )

    def entrar(self, usuario: str) -> None:
        r = self.chamar("POST", "/api/cs/login", {"usuario": usuario, "senha": SENHA})
        assert r.status == 200, r
        self.cookies[usuario] = r.cookies[0].partition("=")[2].split(";")[0]

    def cs(
        self, metodo: str, caminho: str, corpo: Any = None, *, quem: str = "atendente"
    ) -> Resposta:
        """Chamada do Painel_CS; se a sessão expirou com o relógio injetado, entra de novo."""
        if quem not in self.cookies:
            self.entrar(quem)
        r = self.chamar(metodo, caminho, corpo, quem=quem)
        if r.status == 401:
            self.entrar(quem)
            r = self.chamar(metodo, caminho, corpo, quem=quem)
        return r

    # ---- consultas -------------------------------------------------------------------------

    def numeros_chamados(self) -> list[str]:
        return [c.numero for c in self.app.repos.chamados.listar_todos()]

    def ids_jornadas(self) -> list[str]:
        return [j.jornada_id for j in capturar_estado(self.app.repos).jornadas]

    def metricas(self) -> Resposta:
        return self.cs("GET", "/api/cs/metricas", quem="gestor")

    def fila_api(self) -> Resposta:
        return self.cs("GET", "/api/cs/fila", quem="atendente")

    def reiniciar(self, *, com_demo: bool = True, **extras: Any) -> AmbienteDemo:
        """Nova aplicação sobre o MESMO diretório, relógio no mesmo instante (`resetar=False`)."""
        return AmbienteDemo(
            self.dir_dados, Relogio(self.relogio.agora), com_demo=com_demo, **extras
        )


# ----------------------------------------------------------------------------- operações

_indice = st.integers(min_value=0, max_value=50)
_textos = st.text(
    alphabet=st.characters(categories=("L", "N", "Zs"), max_codepoint=0x24F),
    min_size=1,
    max_size=40,
)
_usuario = st.sampled_from(USUARIOS)


def operacoes() -> st.SearchStrategy[tuple[Any, ...]]:
    """Uma operação da API: `(tipo, *argumentos)`. Índices são resolvidos por módulo."""
    encerrar = st.tuples(
        st.just("encerrar"),
        _indice,
        _usuario,
        st.sampled_from(["falso_defeito", "defeito_real"]),
        st.sampled_from(["instrução do manual", "outra"]),
        _textos,
    )
    avaliar = st.tuples(
        st.just("avaliar"), _indice, st.integers(min_value=1, max_value=5), _textos
    )
    return st.one_of(
        st.tuples(st.just("jornada"), st.sampled_from(MODELOS), st.booleans()),
        st.tuples(st.just("problema"), _indice, st.integers(min_value=1, max_value=13)),
        st.tuples(st.just("escalar"), _indice, st.sampled_from(["risco", "pedido_humano"])),
        st.tuples(st.just("assumir"), _indice, _usuario),
        st.tuples(st.just("msg_atendente"), _indice, _usuario, _textos),
        st.tuples(st.just("msg_consumidor"), _indice, _textos),
        encerrar,  # repetidos de propósito: pesam mais no sorteio
        encerrar,
        avaliar,
        avaliar,
        st.tuples(
            st.just("contato"),
            _indice,
            st.one_of(st.none(), st.sampled_from(TELEFONES)),
            st.one_of(st.none(), st.sampled_from(CEPS)),
        ),
        st.tuples(st.just("agendar"), _indice, st.integers(min_value=1, max_value=20)),
        st.tuples(st.just("ordem_servico"), _indice),
    )


_atraso = st.integers(min_value=0, max_value=90_000_000)  # microssegundos de relógio
Passo = tuple[tuple[Any, ...], int]


def _abertura(modelo: str, serie: bool, motivo: str, atraso: int) -> list[Passo]:
    """Cria uma Jornada e a escala em seguida: garante Chamados para as demais operações."""
    return [
        (("jornada", modelo, serie), atraso),
        (("escalar_ultima", motivo), 1),
    ]


def passos(max_size: int = 20, max_aberturas: int = 5) -> st.SearchStrategy[list[Passo]]:
    """Sequência de `(operação, microssegundos de relógio antes dela)`.

    Começa com algumas aberturas (Jornada + escalada), para que assumir, mensagens, contato,
    encerramento e avaliação tenham Chamados reais, e segue com operações livres.
    """
    aberturas = st.lists(
        st.builds(
            _abertura,
            st.sampled_from(MODELOS),
            st.booleans(),
            st.sampled_from(["risco", "pedido_humano"]),
            _atraso,
        ),
        max_size=max_aberturas,
    ).map(lambda grupos: [passo for grupo in grupos for passo in grupo])
    livres = st.lists(st.tuples(operacoes(), _atraso), max_size=max_size)
    return st.builds(lambda a, b: a + b, aberturas, livres)


def _escolher(itens: list[str], indice: int) -> str | None:
    return itens[indice % len(itens)] if itens else None


def aplicar_operacao(amb: AmbienteDemo, operacao: tuple[Any, ...]) -> Resposta | None:
    """Executa UMA operação pela API (`processar`). Falhas de validação (4xx) são legítimas."""
    tipo, *args = operacao
    agora = amb.relogio.agora
    if tipo == "jornada":
        modelo, com_serie = args
        corpo = {"origem": "qr", "modelo_id": modelo}
        if com_serie:
            corpo["numero_serie"] = "DEMO001"
        return amb.chamar("POST", "/api/pub/jornadas", corpo)

    if tipo == "escalar_ultima":
        ids = amb.ids_jornadas()
        if not ids:
            return None
        return amb.chamar("POST", f"/api/pub/jornadas/{ids[-1]}/escalar", {"motivo": args[0]})

    if tipo in {"problema", "escalar"}:
        jid = _escolher(amb.ids_jornadas(), args[0])
        if jid is None:
            return None
        if tipo == "problema":
            corpo = {
                "tipo": "selecionado",
                "problema_id": args[1],
                "ocorrido_em": agora.isoformat(),
            }
            return amb.chamar("POST", f"/api/pub/jornadas/{jid}/eventos", corpo)
        return amb.chamar("POST", f"/api/pub/jornadas/{jid}/escalar", {"motivo": args[1]})

    chamados = amb.app.repos.chamados.listar_todos()
    if tipo == "avaliar":  # só Chamado encerrado aceita avaliação: prefere os encerrados
        chamados = [c for c in chamados if c.status == "encerrado"] or chamados
    numero = _escolher([c.numero for c in chamados], args[0] if args else 0)
    if numero is None:
        return None
    base = f"/api/cs/chamados/{numero}"
    if tipo == "assumir":
        return amb.cs("POST", f"{base}/assumir", quem=args[1])
    if tipo == "msg_atendente":
        corpo = {"texto": args[2], "confirmada": True}
        return amb.cs("POST", f"{base}/mensagens", corpo, quem=args[1])
    if tipo == "msg_consumidor":
        return amb.chamar("POST", f"/api/pub/chamados/{numero}/mensagens", {"texto": args[1]})
    if tipo == "contato":
        telefone, cep = args[1], args[2]
        corpo = {"consentimento": True}
        if telefone:
            corpo["telefone"] = telefone
        if cep:
            corpo["cep"] = cep
        return amb.chamar("POST", f"/api/pub/chamados/{numero}/contato", corpo)
    if tipo == "agendar":
        dia = (agora + timedelta(days=args[1])).date().isoformat()
        corpo = {"data": dia, "hora": "10:00"}
        return amb.cs("POST", f"{base}/agendamento", corpo)
    if tipo == "ordem_servico":
        return amb.cs("POST", f"{base}/ordem-servico")
    if tipo == "encerrar":
        corpo = {"desfecho": args[2], "solucao_tipo": args[3], "solucao": args[4]}
        return amb.cs("POST", f"{base}/encerrar", corpo, quem=args[1])
    if tipo == "avaliar":
        corpo = {"nota": args[1], "comentario": args[2]}
        return amb.chamar("POST", f"/api/pub/chamados/{numero}/avaliacao", corpo)
    raise AssertionError(f"operação desconhecida: {tipo!r}")


def executar(amb: AmbienteDemo, sequencia: list[tuple[tuple[Any, ...], int]]) -> None:
    for operacao, microssegundos in sequencia:
        amb.relogio.avancar(timedelta(microseconds=microssegundos))
        aplicar_operacao(amb, operacao)


# ----------------------------------------------------------------------------- observação


@dataclass
class Observacao:
    """O que o Painel_CS enxerga. Duas observações iguais = mesmo estado visível."""

    estado: EstadoPersistido
    fila: list[Any]
    todos: list[Any]
    mensagens: dict[str, list[Any]]
    metricas: Resposta
    fila_api: Resposta


def observar(amb: AmbienteDemo) -> Observacao:
    repos = amb.app.repos
    todos = repos.chamados.listar_todos()
    return Observacao(
        estado=capturar_estado(repos),
        fila=repos.chamados.listar_fila(),
        todos=todos,
        mensagens={c.numero: repos.mensagens.listar(c.numero) for c in todos},
        metricas=amb.metricas(),
        fila_api=amb.fila_api(),
    )


def chave_fila(chamado: Any) -> str:
    """Ordem da fila: prioridade, horário de criação, número (Req 7.6), como `fila_sk`."""
    return chamado.fila_sk


def exigir_mesmo_estado(antes: Observacao, depois: Observacao) -> None:
    """Afirma que `depois` (após o reinício) é indistinguível de `antes`."""
    assert depois.estado == antes.estado
    assert assinatura(depois.estado) == assinatura(antes.estado)

    # fila: mesmos Chamados, mesma ordem (prioridade, horário, número)
    assert depois.fila == antes.fila
    assert [c.numero for c in depois.fila] == [c.numero for c in antes.fila]
    assert [chave_fila(c) for c in depois.fila] == sorted(chave_fila(c) for c in depois.fila)

    # listar_todos igual, do mais antigo ao mais novo
    assert depois.todos == antes.todos
    assert [(c.criado_em, c.numero) for c in depois.todos] == sorted(
        (c.criado_em, c.numero) for c in depois.todos
    )

    # mensagens por Chamado: mesmas, na mesma ordem cronológica
    assert depois.mensagens == antes.mensagens
    for numero, lista in depois.mensagens.items():
        assert [m.ts_ulid for m in lista] == sorted(m.ts_ulid for m in lista), numero

    # API do Painel_CS: fila e métricas (gestor entrou de novo depois do reinício)
    assert antes.metricas.status == 200 and depois.metricas.status == 200
    assert depois.metricas.corpo == antes.metricas.corpo
    assert depois.fila_api.status == 200 and depois.fila_api.corpo == antes.fila_api.corpo


@pytest.fixture
def dir_dados():
    with tempfile.TemporaryDirectory(prefix="persistencia-reinicio-") as pasta:
        yield Path(pasta) / "dados"


# ----------------------------------------------------------------------------- Property 6


def _reiniciar_e_comparar(amb: AmbienteDemo, *, com_demo_no_reinicio: bool = True) -> None:
    antes = observar(amb)
    exemplos_antes = sum(
        c.jornada_id.startswith("01JDEMO") for c in antes.estado.chamados
    )

    novo = amb.reiniciar(com_demo=com_demo_no_reinicio, espiar=True)

    assert novo.situacao == "carregado"
    # a carga restaura direto nos repositórios: nada de escalar/assumir/encerrar (Req 7.5)
    assert novo.chamadas_espionadas == []
    # nenhum exemplo recriado, mesmo pedindo `com_demo=True` (Req 2.4)
    exemplos_depois = sum(
        c.jornada_id.startswith("01JDEMO") for c in capturar_estado(novo.app.repos).chamados
    )
    assert exemplos_depois == exemplos_antes
    exigir_mesmo_estado(antes, observar(novo))


@PERFIL
@given(com_demo=st.booleans(), sequencia=passos())
def test_propriedade_reiniciar_preserva_o_estado(
    com_demo: bool, sequencia: list[tuple[tuple[Any, ...], int]]
) -> None:
    """Feature: persistencia-local-demo, Property 6: Reiniciar preserva o estado

    **Validates: Requirements 2.1, 2.4, 7.5, 7.6, 7.7, 9.8**
    """
    with tempfile.TemporaryDirectory(prefix="persistencia-reinicio-") as pasta:
        amb = AmbienteDemo(Path(pasta) / "dados", com_demo=com_demo)
        assert amb.situacao == "novo"
        executar(amb, sequencia)

        _reiniciar_e_comparar(amb)


@PERFIL
@given(sequencia=passos(max_size=12), outra=passos(max_size=12))
def test_propriedade_reiniciar_duas_vezes_preserva_o_estado(
    sequencia: list[tuple[tuple[Any, ...], int]], outra: list[tuple[tuple[Any, ...], int]]
) -> None:
    """Feature: persistencia-local-demo, Property 6: Reiniciar preserva o estado

    Operar, reiniciar, continuar operando e reiniciar de novo: o segundo reinício também
    preserva o que foi criado antes e depois do primeiro.

    **Validates: Requirements 2.1, 2.4, 7.5, 7.6, 7.7, 9.8**
    """
    with tempfile.TemporaryDirectory(prefix="persistencia-reinicio-") as pasta:
        amb = AmbienteDemo(Path(pasta) / "dados", com_demo=True)
        executar(amb, sequencia)
        segunda = amb.reiniciar(com_demo=True)
        assert segunda.situacao == "carregado"
        executar(segunda, outra)

        _reiniciar_e_comparar(segunda)


# ----------------------------------------------------------------------------- exemplo fixo


def test_sequencia_completa_gera_estado_nao_trivial_e_sobrevive_ao_reinicio(dir_dados) -> None:
    """Garante que a propriedade não é vazia: a API realmente produz cada tipo de registro."""
    amb = AmbienteDemo(dir_dados, com_demo=True)
    assert amb.situacao == "novo"
    passo = timedelta(seconds=7, microseconds=321)

    def op(*operacao: Any) -> Resposta | None:
        amb.relogio.avancar(passo)
        return aplicar_operacao(amb, operacao)

    assert op("jornada", "tres-passione", True).status == 201  # type: ignore[union-attr]
    assert op("jornada", "tres-circo", False).status == 201  # type: ignore[union-attr]
    n_demo = len(amb.ids_jornadas()) - 2  # Jornadas de exemplo vêm antes das criadas aqui
    assert n_demo == 3
    # as duas Jornadas novas são as últimas da lista (índices n_demo e n_demo + 1)
    assert op("problema", n_demo, 6).status == 201  # type: ignore[union-attr]
    assert op("escalar", n_demo, "pedido_humano").status == 200  # type: ignore[union-attr]
    assert op("escalar", n_demo + 1, "risco").status == 200  # type: ignore[union-attr]

    # Chamados em ordem de criação (criado_em, numero): 3 exemplos + 2 novos
    numeros = amb.numeros_chamados()
    assert len(numeros) == 5
    novo_p3, novo_p1 = numeros[3], numeros[4]
    assert amb.app.repos.chamados.obter(novo_p1).prioridade == "P1"

    assert op("assumir", 3, "atendente").status == 200  # type: ignore[union-attr]
    assert op("msg_atendente", 3, "atendente", "Olá, vamos resolver").status == 201  # type: ignore[union-attr]
    assert op("msg_consumidor", 3, "Obrigado pela ajuda").status == 201  # type: ignore[union-attr]
    assert op("msg_consumidor", 3, "Ainda não funcionou").status == 201  # type: ignore[union-attr]
    assert op("contato", 3, "11987654321", "01310100").status == 200  # type: ignore[union-attr]
    assert op("ordem_servico", 4).status == 200  # type: ignore[union-attr]
    assert op("agendar", 4, 3).status == 200  # type: ignore[union-attr]
    encerrar = op("encerrar", 3, "atendente", "falso_defeito", "instrução do manual", "Ligou")
    assert encerrar.status == 200  # type: ignore[union-attr]
    assert op("avaliar", 3, 5, "ótimo").status == 200  # type: ignore[union-attr]

    estado = capturar_estado(amb.app.repos)
    repos = amb.app.repos
    assert {c.status for c in estado.chamados} == {"aberto", "encerrado"}
    assert repos.chamados.obter(novo_p3).status == "encerrado"
    assert len(repos.mensagens.listar(novo_p3)) == 3
    assert [m.autor for m in repos.mensagens.listar(novo_p3)] == [
        "atendente",
        "consumidor",
        "consumidor",
    ]
    assert len(estado.dados_pessoais) == 1
    assert len(estado.ordens_servico) >= 1
    assert len(estado.avaliacoes) == 1
    assert len(estado.agregados) >= 1
    assert len(repos.chamados.listar_fila()) == 4  # o encerrado saiu da fila

    metricas = amb.metricas()
    assert metricas.status == 200
    assert metricas.corpo["totais"] == {"abertos": 4, "encerrados": 1}
    assert {linha["chave"] for linha in metricas.corpo["por_problema"]} >= {"6", "nao_informado"}

    _reiniciar_e_comparar(amb)


def test_reiniciar_sem_nenhuma_operacao_preserva_so_os_exemplos(dir_dados) -> None:
    amb = AmbienteDemo(dir_dados, com_demo=True)
    assert len(amb.numeros_chamados()) == 3
    _reiniciar_e_comparar(amb)
    sem_demo = AmbienteDemo(dir_dados.parent / "sem-demo", com_demo=False)
    assert sem_demo.numeros_chamados() == []
    _reiniciar_e_comparar(sem_demo)


# ----------------------------------------------------------------------------- Property 7

NOME_SNAPSHOT_ARQ = "estado.json"
NOME_TEMPORARIO_ARQ = "estado.json.tmp"
CAMPOS_ESTADO = (
    "jornadas",
    "eventos",
    "chamados",
    "mensagens",
    "dados_pessoais",
    "acessos_pii",
    "ordens_servico",
    "cache",
    "avaliacoes",
    "agregados",
    "config",
)


@PERFIL
@given(
    com_demo_anterior=st.booleans(),
    com_demo=st.booleans(),
    anterior=st.sampled_from(["nenhum", "valido", "corrompido"]),
    temporario=st.booleans(),
    sequencia=passos(max_size=12),
)
def test_propriedade_resetar_descarta_qualquer_estado_anterior(
    com_demo_anterior: bool,
    com_demo: bool,
    anterior: str,
    temporario: bool,
    sequencia: list[tuple[tuple[Any, ...], int]],
) -> None:
    """Feature: persistencia-local-demo, Property 7: --resetar descarta qualquer estado anterior

    **Validates: Requirements 3.1, 3.2, 3.4**
    """
    with tempfile.TemporaryDirectory(prefix="persistencia-reinicio-") as pasta:
        raiz = Path(pasta)
        dir_dados = raiz / "dados"

        # referência: a primeira subida da demo, em outro diretório, sem nada anterior
        primeira = AmbienteDemo(raiz / "primeira", com_demo=com_demo)
        assert primeira.situacao == "novo"
        referencia = capturar_estado(primeira.app.repos)

        # estado anterior: snapshot válido (com operações), ilegível, ou nenhum
        numeros_anteriores: set[str] = set()
        jornadas_anteriores: set[str] = set()
        if anterior == "valido":
            antigo = AmbienteDemo(dir_dados, com_demo=com_demo_anterior)
            executar(antigo, sequencia)
            numeros_anteriores = set(antigo.numeros_chamados())
            jornadas_anteriores = set(antigo.ids_jornadas())
        elif anterior == "corrompido":
            dir_dados.mkdir(parents=True)
            (dir_dados / NOME_SNAPSHOT_ARQ).write_text('{"versao": 1, "estado": {', "utf-8")
        if temporario:
            dir_dados.mkdir(parents=True, exist_ok=True)
            (dir_dados / NOME_TEMPORARIO_ARQ).write_text("lixo de gravação interrompida", "utf-8")

        # --resetar: sem erro, mesmo resultado da primeira subida
        novo = AmbienteDemo(dir_dados, resetar=True, com_demo=com_demo)
        assert novo.situacao == "resetado"
        estado = capturar_estado(novo.app.repos)

        assert len(estado.chamados) == (3 if com_demo else 0)
        assert [j.jornada_id for j in estado.jornadas] == [
            j.jornada_id for j in referencia.jornadas
        ]
        assert all(j.jornada_id.startswith("01JDEMO") for j in estado.jornadas)
        # os exemplos usam o relógio real (criada_em muda); o resto da Jornada é o mesmo
        assert [(j.jornada_id, j.modelo_id, j.estado, j.origem) for j in estado.jornadas] == [
            (j.jornada_id, j.modelo_id, j.estado, j.origem) for j in referencia.jornadas
        ]
        assert {c.jornada_id for c in estado.chamados} == {
            c.jornada_id for c in referencia.chamados
        }
        for campo in CAMPOS_ESTADO:
            assert len(getattr(estado, campo)) == len(getattr(referencia, campo)), campo

        # nenhum registro anterior sobrevive
        assert not set(novo.numeros_chamados()) & numeros_anteriores
        demo_ids = {j.jornada_id for j in referencia.jornadas}
        assert not (set(novo.ids_jornadas()) & (jornadas_anteriores - demo_ids))

        # o diretório contém só o snapshot inicial, igual ao estado capturado
        assert sorted(p.name for p in dir_dados.iterdir()) == [NOME_SNAPSHOT_ARQ]
        assert novo.persistencia.carregar() == estado
        assert assinatura(novo.persistencia.carregar()) == assinatura(estado)

        # a subida seguinte, sem --resetar, recarrega esse estado
        seguinte = novo.reiniciar(com_demo=True)
        assert seguinte.situacao == "carregado"
        assert capturar_estado(seguinte.app.repos) == estado
        assert sorted(p.name for p in dir_dados.iterdir()) == [NOME_SNAPSHOT_ARQ]


# ----------------------------------------------------------------------------- Property 8


def _verificar_condicionais_no_repositorio(amb: AmbienteDemo) -> int:
    """Req 7.1 a 7.4 direto nos repositórios (e no serviço de escalada) do ambiente recarregado.

    Devolve quantos Chamados foram verificados. Só chama `amb.app.*` (nenhuma rota), então nada
    é gravado em disco.
    """
    from dataclasses import replace

    repos = amb.app.repos
    antes = {c.numero: c for c in repos.chamados.listar_todos()}
    jornadas = {j.jornada_id: j for j in capturar_estado(repos).jornadas}
    em = amb.relogio.agora + timedelta(minutes=5)

    # 7.1: Jornada que já tem Chamado devolve o existente, sem criar um segundo
    for jornada in jornadas.values():
        if jornada.escalada is None:
            continue
        existente = jornada.escalada.chamado_numero
        assert existente in antes
        resultado = amb.app.escalada.escalar(jornada.jornada_id, "pedido_humano")
        assert resultado.criado is False
        assert resultado.chamado.numero == existente
        assert len(repos.chamados.listar_todos()) == len(antes)

        modelo = replace(
            antes[existente],
            numero="9" * 12,
            status="aberto",
            responsavel=None,
            encerramento=None,
        )
        tentativa = repos.chamados.criar_com_escalada(
            modelo, jornada.escalada.gatilhos[0], jornada.escalada.decisao
        )
        assert tentativa.criado is False
        assert tentativa.motivo == "jornada_ja_escalada"
        assert tentativa.numero_existente == existente
        assert repos.chamados.obter("9" * 12) is None
        assert len(repos.chamados.listar_todos()) == len(antes)

    # 7.2, 7.3 e 7.4, Chamado a Chamado (a escalada acima pode elevar a prioridade: só ela)
    for numero, original in antes.items():
        resultado = repos.chamados.assumir(numero, "outro", "Outro Atendente", em)
        atual = repos.chamados.obter(numero)
        assert atual is not None and resultado.registro == atual
        if original.status == "encerrado" or original.responsavel is not None:
            # 7.2: nada muda; o responsável (se houver) é o original
            assert resultado.aplicado is False
            assert atual.responsavel == original.responsavel
            assert atual.status == original.status
            assert atual.encerramento == original.encerramento
        else:
            # 7.3: grava o responsável e passa a em_atendimento
            assert resultado.aplicado is True
            assert atual.responsavel is not None
            assert (atual.responsavel.usuario, atual.responsavel.nome, atual.responsavel.inicio) == (
                "outro",
                "Outro Atendente",
                em,
            )
            assert atual.status == "em_atendimento"
            segunda = repos.chamados.assumir(numero, "terceiro", "Terceiro", em)
            assert segunda.aplicado is False
            assert segunda.registro.responsavel == atual.responsavel

        # 7.4: encerrar de novo um Chamado já encerrado mantém o encerramento original
        if original.status == "encerrado":
            assert original.encerramento is not None
            novo = replace(
                original.encerramento,
                desfecho="defeito_real"
                if original.encerramento.desfecho == "falso_defeito"
                else "falso_defeito",
                solucao="outra solução",
                em=em,
                por="outro",
            )
            tentativa = repos.chamados.encerrar(numero, novo)
            assert tentativa.aplicado is False
            assert tentativa.registro.encerramento == original.encerramento
            assert repos.chamados.obter(numero) == atual
            assert atual.encerramento == original.encerramento
    return len(antes)


def _verificar_condicionais_na_api(amb: AmbienteDemo) -> None:
    """Req 7.1 a 7.4 pelas rotas, sobre outro ambiente recarregado do mesmo snapshot."""
    repos = amb.app.repos
    antes = {c.numero: c for c in repos.chamados.listar_todos()}

    for numero, original in antes.items():
        base = f"/api/cs/chamados/{numero}"
        r = amb.cs("POST", f"{base}/assumir", quem="atendente")
        atual = repos.chamados.obter(numero)
        assert atual is not None
        if original.status == "encerrado" or original.responsavel is not None:
            assert r.status == 409, r
            assert atual == original
        else:
            assert r.status == 200, r
            assert r.corpo["status"] == "em_atendimento"
            assert r.corpo["responsavel"]["usuario"] == "atendente"
            assert atual.status == "em_atendimento"
            assert atual.responsavel is not None and atual.responsavel.usuario == "atendente"

        if original.status == "encerrado":
            corpo = {
                "desfecho": "defeito_real",
                "solucao_tipo": "outra",
                "solucao": "tentativa de encerrar de novo",
            }
            r = amb.cs("POST", f"{base}/encerrar", corpo, quem="gestor")
            assert r.status == 409, r
            assert repos.chamados.obter(numero) == atual
            assert atual.encerramento == original.encerramento

    # 7.1 pela API: escalar Jornada que já tem Chamado devolve o existente
    for jornada in capturar_estado(repos).jornadas:
        if jornada.escalada is None:
            continue
        existente = jornada.escalada.chamado_numero
        r = amb.chamar(
            "POST", f"/api/pub/jornadas/{jornada.jornada_id}/escalar", {"motivo": "pedido_humano"}
        )
        assert r.status == 200, r
        assert r.corpo["numero"] == existente
        assert sorted(amb.numeros_chamados()) == sorted(antes)


@PERFIL
@given(sequencia=passos())
def test_propriedade_operacoes_condicionais_valem_depois_de_recarregar(
    sequencia: list[tuple[tuple[Any, ...], int]],
) -> None:
    """Feature: persistencia-local-demo, Property 8: Operações condicionais continuam valendo depois de recarregar

    **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
    """
    with tempfile.TemporaryDirectory(prefix="persistencia-reinicio-") as pasta:
        amb = AmbienteDemo(Path(pasta) / "dados", com_demo=True)
        executar(amb, sequencia)

        recarregado = amb.reiniciar(com_demo=True)
        assert recarregado.situacao == "carregado"
        _verificar_condicionais_no_repositorio(recarregado)

        # o snapshot não mudou (nenhuma rota foi chamada acima): recarrega de novo para a API
        pela_api = amb.reiniciar(com_demo=True)
        assert pela_api.situacao == "carregado"
        _verificar_condicionais_na_api(pela_api)


def test_condicionais_depois_de_recarregar_cobrem_os_quatro_casos(dir_dados) -> None:
    """Exemplo fixo: há Chamado com responsável, sem responsável e encerrado após o reinício."""
    amb = AmbienteDemo(dir_dados, com_demo=True)
    passo = timedelta(seconds=3)

    def op(*operacao: Any) -> Resposta | None:
        amb.relogio.avancar(passo)
        return aplicar_operacao(amb, operacao)

    assert op("jornada", "tres-passione", True).status == 201  # type: ignore[union-attr]
    assert op("jornada", "tres-circo", False).status == 201  # type: ignore[union-attr]
    assert op("jornada", "tres-mimo", False).status == 201  # type: ignore[union-attr]
    n_demo = len(amb.ids_jornadas()) - 3
    for i in range(3):
        assert op("escalar", n_demo + i, "pedido_humano").status == 200  # type: ignore[union-attr]
    assert op("assumir", 3, "atendente").status == 200  # type: ignore[union-attr]
    assert op("assumir", 4, "gestor").status == 200  # type: ignore[union-attr]
    corpo = ("encerrar", 4, "gestor", "defeito_real", "outra", "Troca de peça")
    assert op(*corpo).status == 200  # type: ignore[union-attr]

    reinicio = amb.reiniciar(com_demo=True)
    chamados = reinicio.app.repos.chamados.listar_todos()
    assert any(c.status == "encerrado" for c in chamados)
    assert any(c.status == "em_atendimento" and c.responsavel for c in chamados)
    assert any(c.status != "encerrado" and c.responsavel is None for c in chamados)

    assert _verificar_condicionais_no_repositorio(reinicio) == len(chamados)
    _verificar_condicionais_na_api(amb.reiniciar(com_demo=True))


# ----------------------------------------------------------------------------- Property 9


class GeradorComColisoes:
    """Gerador de números injetado em `app.escalada`: devolve PRIMEIRO números já em uso.

    Cada escalada consome `colisoes` números carregados (rodando pela lista) e só depois um
    número livre, nunca repetido e fora do conjunto dos carregados. `chamadas` registra tudo o
    que foi devolvido, na ordem, para a conferência do mecanismo `numero_em_uso`.
    """

    def __init__(self, carregados: list[str], livres: list[str]) -> None:
        self.carregados = carregados
        self.livres = iter(livres)
        self.fila: list[str] = []
        self.chamadas: list[str] = []

    def preparar(self, colisoes: int) -> None:
        """Programa a PRÓXIMA escalada: `colisoes` números carregados e depois um livre."""
        self.fila.extend(self.carregados[i % len(self.carregados)] for i in range(colisoes))
        self.fila.append(next(self.livres))

    def __call__(self) -> str:
        numero = self.fila.pop(0)
        self.chamadas.append(numero)
        return numero


def _numeros_livres(quantos: int, sementes: list[int], ocupados: set[str]) -> list[str]:
    """Números no formato real (`TRES-` + 10 Crockford), distintos entre si e dos `ocupados`."""
    from servicos.escalada import gerar_numero_chamado

    livres: list[str] = []
    for i in range(quantos):
        valor = sementes[i % len(sementes)] + i
        while True:
            numero = gerar_numero_chamado(lambda _bits, v=valor: v % (1 << 50))
            if numero not in ocupados and numero not in livres:
                break
            valor += 1
        livres.append(numero)
    return livres


def _nova_jornada(amb: AmbienteDemo, modelo: str) -> str:
    """Cria uma Jornada pela API e devolve o `jornada_id` (a única que não existia antes)."""
    antes = set(amb.ids_jornadas())
    r = amb.chamar("POST", "/api/pub/jornadas", {"origem": "qr", "modelo_id": modelo})
    assert r.status == 201, r
    (novo,) = set(amb.ids_jornadas()) - antes
    return novo


def _escalar_com_colisoes(
    amb: AmbienteDemo, gerador: GeradorComColisoes, jornada_id: str, gatilho: str, colisoes: int
) -> str:
    """Escala UMA Jornada nova e confere as garantias da Property 9. Devolve o número criado."""
    antes = {c.numero: c for c in amb.app.repos.chamados.listar_todos()}
    ja_chamadas = len(gerador.chamadas)
    gerador.preparar(colisoes)

    if gatilho == "risco_seguranca":
        resultado = amb.app.escalada.marcar_risco(jornada_id, "lista").escalada
        assert resultado is not None
    else:
        resultado = amb.app.escalada.escalar(jornada_id, gatilho)  # type: ignore[arg-type]

    assert resultado.criado is True
    # o mecanismo `numero_em_uso`: cada colisão foi recusada e o gerador foi chamado de novo
    devolvidos = gerador.chamadas[ja_chamadas:]
    assert len(devolvidos) == colisoes + 1
    assert all(n in antes for n in devolvidos[:-1])  # colisões: números que já existiam
    assert devolvidos[-1] not in antes  # o último é o livre

    depois = {c.numero: c for c in amb.app.repos.chamados.listar_todos()}
    novo = resultado.chamado.numero
    assert novo == devolvidos[-1]
    assert novo not in antes  # distinto de todos os carregados
    assert len(depois) == len(antes) + 1  # cresce exatamente em 1 por escalada
    assert set(depois) == set(antes) | {novo}
    for numero, registro in antes.items():  # nenhum Chamado anterior foi sobrescrito
        assert depois[numero] == registro, numero
    assert depois[novo].jornada_id == jornada_id
    jornada = amb.app.repos.jornadas.obter(jornada_id)
    assert jornada is not None and jornada.escalada is not None
    assert jornada.escalada.chamado_numero == novo
    return novo


@PERFIL
@given(
    sequencia=passos(max_size=12),
    escaladas=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=4),  # colisões antes do número livre
            st.sampled_from(["pedido_humano", "risco_seguranca"]),
            st.sampled_from(MODELOS),
        ),
        min_size=1,
        max_size=3,
    ),
    sementes=st.lists(st.integers(min_value=0, max_value=(1 << 50) - 1), min_size=1, max_size=3),
)
def test_propriedade_numero_novo_nao_colide_com_os_carregados(
    sequencia: list[tuple[tuple[Any, ...], int]],
    escaladas: list[tuple[int, str, str]],
    sementes: list[int],
) -> None:
    """Feature: persistencia-local-demo, Property 9: Número novo não colide com os carregados

    **Validates: Requirements 2.9**
    """
    with tempfile.TemporaryDirectory(prefix="persistencia-reinicio-") as pasta:
        amb = AmbienteDemo(Path(pasta) / "dados", com_demo=True)
        executar(amb, sequencia)

        recarregado = amb.reiniciar(com_demo=True)
        assert recarregado.situacao == "carregado"
        carregados = recarregado.numeros_chamados()
        assert carregados  # há ao menos os 3 Chamados de exemplo

        livres = _numeros_livres(len(escaladas), sementes, set(carregados))
        gerador = GeradorComColisoes(carregados, livres)
        recarregado.app.escalada._gerar_numero = gerador  # injeção: atributo do ServicoEscalada

        criados: list[str] = []
        for colisoes, gatilho, modelo in escaladas:
            jornada_id = _nova_jornada(recarregado, modelo)
            criados.append(
                _escalar_com_colisoes(recarregado, gerador, jornada_id, gatilho, colisoes)
            )

        assert len(set(criados)) == len(criados)
        assert not set(criados) & set(carregados)
        assert len(recarregado.numeros_chamados()) == len(carregados) + len(escaladas)


def test_colisao_com_numero_carregado_gera_outro_numero_sem_sobrescrever(dir_dados) -> None:
    """Exemplo fixo: o gerador devolve um número carregado e só depois um livre."""
    amb = AmbienteDemo(dir_dados, com_demo=True)
    amb.relogio.avancar(timedelta(seconds=5))
    assert _nova_jornada(amb, "tres-passione")
    reinicio = amb.reiniciar(com_demo=True)
    assert reinicio.situacao == "carregado"
    carregados = reinicio.numeros_chamados()
    assert len(carregados) == 3  # os exemplos

    alvo = carregados[0]
    original = reinicio.app.repos.chamados.obter(alvo)
    livre = _numeros_livres(1, [123456789], set(carregados))[0]
    gerador = GeradorComColisoes([alvo], [livre])
    reinicio.app.escalada._gerar_numero = gerador

    jornada_id = reinicio.ids_jornadas()[-1]  # a Jornada criada, ainda sem Chamado
    assert reinicio.app.repos.jornadas.obter(jornada_id).escalada is None  # type: ignore[union-attr]
    gerador.preparar(1)  # colisão com `alvo`, depois `livre`
    resultado = reinicio.app.escalada.escalar(jornada_id, "pedido_humano")

    assert gerador.chamadas == [alvo, livre]
    assert resultado.criado is True
    assert resultado.chamado.numero == livre
    assert reinicio.app.repos.chamados.obter(alvo) == original  # intacto
    assert sorted(reinicio.numeros_chamados()) == sorted([*carregados, livre])
    # o snapshot seguinte também carrega os dois: o número livre não perdeu nem tomou o de ninguém
    reinicio.persistencia.gravar(reinicio.app.repos)
    de_novo = reinicio.reiniciar(com_demo=True)
    assert sorted(de_novo.numeros_chamados()) == sorted([*carregados, livre])
    assert de_novo.app.repos.chamados.obter(alvo) == original


def test_cinco_colisoes_seguidas_esgotam_as_tentativas_sem_criar_chamado(dir_dados) -> None:
    """Exemplo fixo: 5 números em uso seguidos (o limite) não criam nem alteram Chamado algum."""
    from repositorios.erros import ErroRepositorio
    from servicos.escalada import MAX_TENTATIVAS_NUMERO

    amb = AmbienteDemo(dir_dados, com_demo=True)
    jornada_id = _nova_jornada(amb, "tres-circo")
    reinicio = amb.reiniciar(com_demo=True)
    carregados = reinicio.numeros_chamados()
    antes = {c.numero: c for c in reinicio.app.repos.chamados.listar_todos()}

    gerador = GeradorComColisoes(carregados, [])
    gerador.fila = [carregados[i % len(carregados)] for i in range(MAX_TENTATIVAS_NUMERO)]
    reinicio.app.escalada._gerar_numero = gerador

    with pytest.raises(ErroRepositorio):
        reinicio.app.escalada.escalar(jornada_id, "pedido_humano")

    assert len(gerador.chamadas) == MAX_TENTATIVAS_NUMERO
    depois = {c.numero: c for c in reinicio.app.repos.chamados.listar_todos()}
    assert depois == antes
    jornada = reinicio.app.repos.jornadas.obter(jornada_id)
    assert jornada is not None and jornada.escalada is None


# ----------------------------------------------------------------------------- Property 4 (main)

import contextlib  # noqa: E402
import io  # noqa: E402
import os  # noqa: E402
from unittest import mock  # noqa: E402

from estado_demo import serializar_estado  # noqa: E402
from test_estado_demo import estados, json_nativos, snapshots_corrompidos  # noqa: E402

MTIME_ANTIGO_NS = 1_600_000_000_123_456_789  # fixo e antigo: qualquer reescrita mudaria o mtime


class ServidorNaoDeveSubir:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("o servidor não pode subir com snapshot inválido")


@st.composite
def conteudos_invalidos(draw: st.DrawFn) -> tuple[bytes, str]:
    """Conteúdo de `estado.json` que nunca é um snapshot válido: `(bytes, rótulo)`."""
    tipo = draw(st.sampled_from(["corrompido", "binario", "json_de_outro_tipo", "truncado"]))
    if tipo == "corrompido":  # snapshot válido de `estados()` com UMA corrupção
        texto, _, _ = draw(snapshots_corrompidos())
        return texto.encode("utf-8"), tipo
    if tipo == "binario":  # bytes aleatórios; o prefixo garante UTF-8 inválido
        return b"\xff\xfe" + draw(st.binary(max_size=200)), tipo
    if tipo == "json_de_outro_tipo":  # JSON válido, mas não um objeto de snapshot
        valor = draw(
            st.one_of(
                json_nativos(),
                st.lists(json_nativos(), max_size=4),
                st.dictionaries(
                    st.text(min_size=1, max_size=8).map(lambda s: "zqx_" + s),
                    json_nativos(),
                    max_size=3,
                ),
            )
        )
        return json.dumps(valor, ensure_ascii=False).encode("utf-8"), tipo
    # truncado: corta um snapshot válido antes do último "}" (o corte pode partir um UTF-8)
    bruto = serializar_estado(draw(estados())).rstrip().encode("utf-8")
    corte = draw(st.integers(min_value=0, max_value=len(bruto) - 1))
    return bruto[:corte], tipo


@PERFIL
@given(conteudo=conteudos_invalidos())
def test_propriedade_main_rejeita_snapshot_invalido_sem_alteracao(
    conteudo: tuple[bytes, str],
) -> None:
    """Feature: persistencia-local-demo, Property 4: Snapshot inválido é rejeitado sem alteração

    Parte do `main`: código 2, mensagem com o caminho e `--resetar`, arquivo intacto
    (bytes e mtime), nenhum servidor e nenhum `.tmp`.

    **Validates: Requirements 2.6, 2.7**
    """
    bruto, rotulo = conteudo
    modulo = carregar_dev_local()
    with tempfile.TemporaryDirectory(prefix="persistencia-reinicio-") as pasta:
        dir_dados = Path(pasta) / "dados"
        dir_dados.mkdir()
        arquivo = dir_dados / NOME_SNAPSHOT_ARQ
        arquivo.write_bytes(bruto)
        os.utime(arquivo, ns=(MTIME_ANTIGO_NS, MTIME_ANTIGO_NS))
        antes = (arquivo.read_bytes(), arquivo.stat().st_mtime_ns)

        erro, saida = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(modulo, "ThreadingHTTPServer", ServidorNaoDeveSubir),
            contextlib.redirect_stderr(erro),
            contextlib.redirect_stdout(saida),
        ):
            codigo = modulo.main(["--porta", "0"], dir_dados=dir_dados)

        assert codigo == 2, rotulo
        assert str(arquivo) in erro.getvalue(), rotulo
        assert "--resetar" in erro.getvalue(), rotulo
        assert (arquivo.read_bytes(), arquivo.stat().st_mtime_ns) == antes, rotulo
        assert sorted(p.name for p in dir_dados.iterdir()) == [NOME_SNAPSHOT_ARQ], rotulo
        assert not (dir_dados / NOME_TEMPORARIO_ARQ).exists(), rotulo
