"""Persistência da demo local: Serializador (estado <-> JSON) e gravação atômica do snapshot.

SOMENTE PARA DEMO/DESENVOLVIMENTO. O módulo só toca os repositórios em memória, nunca a API de
produção. Este arquivo concentra:

- erros (`ErroSerializacao`, `ErroSnapshot`);
- `EstadoPersistido` e a classificação dos repositórios (`PERSISTIDOS` / `EXCLUIDOS`);
- o codec (`codificar` / `decodificar`), dirigido por `dataclasses.fields` e `get_type_hints`;
- o texto do snapshot (`serializar_estado` / `ler_estado`);
- a captura e a restauração nos repositórios em memória (`capturar_estado` / `aplicar_estado`);
- a `Persistencia`: gravação atômica (tmp + fsync + os.replace), leitura e remoção do snapshot.

O snapshot nunca inclui usuários do Painel_CS, hashes de senha, sessões nem o catálogo.
"""

from __future__ import annotations

import copy
import json
import math
import os
import sys
import threading
import types
import typing
from collections.abc import Callable
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any, Literal, get_args, get_origin, get_type_hints

_RAIZ = Path(__file__).resolve().parent.parent
for _caminho in (_RAIZ / "services" / "api", _RAIZ / "packages" / "dominio" / "src"):
    if str(_caminho) not in sys.path:
        sys.path.insert(0, str(_caminho))

from repositorios.interfaces import Repositorios  # noqa: E402
from repositorios.modelos import (  # noqa: E402
    AcessoPII,
    AgregadoDia,
    Avaliacao,
    Chamado,
    DadosPessoaisRegistro,
    Evento,
    Jornada,
    MensagemChamado,
    OrdemServico,
    RegistroCache,
    os_id_de,
)

VERSAO_FORMATO = 1
NOME_SNAPSHOT = "estado.json"
NOME_TEMPORARIO = "estado.json.tmp"


class ErroSerializacao(ValueError):
    """Valor de tipo desconhecido ao gravar. `campo` é o caminho (ex.: 'eventos[3].dados.x')."""

    def __init__(self, campo: str, tipo: str) -> None:
        self.campo, self.tipo = campo, tipo
        super().__init__(f"campo {campo!r}: tipo não suportado {tipo!r}")


class ErroSnapshot(ValueError):
    """JSON inválido, versão diferente ou estrutura que o Serializador não reconhece."""

    def __init__(self, caminho: Path, motivo: str) -> None:
        self.caminho, self.motivo = caminho, motivo
        super().__init__(f"{caminho}: {motivo}")


class _ErroLeitura(ValueError):
    """Falha interna de `decodificar`; `ler_estado` a converte em `ErroSnapshot`."""

    def __init__(self, campo: str, motivo: str) -> None:
        self.campo, self.motivo = campo, motivo
        super().__init__(f"campo {campo!r}: {motivo}")


# ----------------------------------------------------------------------------- estado


@dataclass
class EstadoPersistido:
    """Uma lista por repositório incluído no snapshot.

    A igualdade padrão de dataclass compara listas e registros (propriedade de ida e volta).
    """

    jornadas: list[Jornada] = field(default_factory=list)
    eventos: list[Evento] = field(default_factory=list)
    chamados: list[Chamado] = field(default_factory=list)
    # Mensagens achatadas; `aplicar_estado` as agrupa por `numero`.
    mensagens: list[MensagemChamado] = field(default_factory=list)
    dados_pessoais: list[DadosPessoaisRegistro] = field(default_factory=list)
    acessos_pii: list[AcessoPII] = field(default_factory=list)
    ordens_servico: list[OrdemServico] = field(default_factory=list)
    cache: list[RegistroCache] = field(default_factory=list)
    avaliacoes: list[Avaliacao] = field(default_factory=list)
    agregados: list[AgregadoDia] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


# Repositórios dentro e fora do snapshot (Req 4.7, 4.8). Um teste confere que a união
# bate com os campos de `Repositorios`, para um repositório novo não passar sem classificação.
PERSISTIDOS = frozenset(
    {
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
    }
)
EXCLUIDOS = frozenset({"usuarios_cs", "sessoes", "catalogo"})


# ----------------------------------------------------------------------------- codificar


def _chave(chave: Any, campo: str) -> str:
    if not isinstance(chave, str):
        raise ErroSerializacao(f"{campo}.{chave}", f"chave {type(chave).__name__}")
    return chave


def codificar(valor: Any, campo: str = "$") -> Any:
    """Valor Python -> estrutura JSON. Levanta `ErroSerializacao(campo, tipo)`."""
    if isinstance(valor, Enum):
        return codificar(valor.value, campo)
    if valor is None or isinstance(valor, bool | int | str):
        return valor
    if isinstance(valor, float):
        if not math.isfinite(valor):
            raise ErroSerializacao(campo, "float não finito")
        return valor
    if isinstance(valor, Decimal):
        if not valor.is_finite():
            raise ErroSerializacao(campo, "Decimal não finito")
        return str(valor)  # texto, sem passar por float (Req 4.2)
    if isinstance(valor, datetime):
        if valor.utcoffset() is None:
            raise ErroSerializacao(campo, "datetime sem fuso")
        return valor.isoformat()  # preserva fuso e microssegundos (Req 4.1)
    if isinstance(valor, list | tuple):
        return [codificar(v, f"{campo}[{i}]") for i, v in enumerate(valor)]
    if isinstance(valor, dict):
        return {
            _chave(k, campo): codificar(v, f"{campo}.{k}") for k, v in valor.items()
        }
    if is_dataclass(valor) and not isinstance(valor, type):
        return {
            f.name: codificar(getattr(valor, f.name), f"{campo}.{f.name}") for f in fields(valor)
        }
    raise ErroSerializacao(campo, type(valor).__name__)  # Req 4.9


# ----------------------------------------------------------------------------- decodificar

_DICAS: dict[type, dict[str, Any]] = {}


def _dicas(cls: type) -> dict[str, Any]:
    """`get_type_hints` com cache por classe."""
    dicas = _DICAS.get(cls)
    if dicas is None:
        dicas = get_type_hints(cls)
        _DICAS[cls] = dicas
    return dicas


def _tipo_json(valor: Any) -> str:
    return type(valor).__name__


def _json_nativo(bruto: Any, campo: str) -> Any:
    """`Any`: só o que o JSON representa (listas e objetos recursivos)."""
    if bruto is None or isinstance(bruto, bool | int | str):
        return bruto
    if isinstance(bruto, float):
        if not math.isfinite(bruto):
            raise _ErroLeitura(campo, "número não finito")
        return bruto
    if isinstance(bruto, list):
        return [_json_nativo(v, f"{campo}[{i}]") for i, v in enumerate(bruto)]
    if isinstance(bruto, dict):
        return {k: _json_nativo(v, f"{campo}.{k}") for k, v in bruto.items()}
    raise _ErroLeitura(campo, f"tipo {_tipo_json(bruto)} não suportado")


def _decodificar_dataclass(
    cls: type, bruto: Any, campo: str, *, exigir_todos: bool = False
) -> Any:
    if not isinstance(bruto, dict):
        raise _ErroLeitura(campo, f"esperado objeto, veio {_tipo_json(bruto)}")
    dicas = _dicas(cls)
    campos = {f.name: f for f in fields(cls)}
    for chave in bruto:
        if chave not in campos:
            raise _ErroLeitura(f"{campo}.{chave}", "campo desconhecido")
    kwargs: dict[str, Any] = {}
    for nome, f in campos.items():
        if nome in bruto:
            kwargs[nome] = decodificar(dicas[nome], bruto[nome], f"{campo}.{nome}")
        elif exigir_todos or (f.default is MISSING and f.default_factory is MISSING):
            raise _ErroLeitura(f"{campo}.{nome}", "campo ausente")
    try:
        return cls(**kwargs)
    except (ValueError, TypeError) as erro:
        raise _ErroLeitura(campo, f"registro inválido: {erro}") from erro


def decodificar(tipo: Any, bruto: Any, campo: str = "$") -> Any:
    """Estrutura JSON -> valor Python do `tipo` anotado. Levanta `_ErroLeitura`."""
    if tipo is Any:
        return _json_nativo(bruto, campo)
    if tipo is None or tipo is type(None):
        if bruto is not None:
            raise _ErroLeitura(campo, f"esperado null, veio {_tipo_json(bruto)}")
        return None

    origem = get_origin(tipo)
    if origem is Literal:
        for permitido in get_args(tipo):
            if type(permitido) is type(bruto) and permitido == bruto:
                return bruto
        raise _ErroLeitura(campo, "valor fora do domínio do Literal")
    if origem is types.UnionType or origem is typing.Union:
        opcoes = get_args(tipo)
        if bruto is None and type(None) in opcoes:
            return None
        ultimo: _ErroLeitura | None = None
        for opcao in opcoes:
            if opcao is type(None):
                continue
            try:
                return decodificar(opcao, bruto, campo)
            except _ErroLeitura as erro:
                ultimo = erro
        raise ultimo or _ErroLeitura(campo, "nenhuma alternativa do tipo serve")
    if origem is tuple:
        args = get_args(tipo)
        if len(args) != 2 or args[1] is not Ellipsis:
            raise _ErroLeitura(campo, f"tipo de tupla não suportado: {tipo!r}")
        if not isinstance(bruto, list):
            raise _ErroLeitura(campo, f"esperado lista, veio {_tipo_json(bruto)}")
        return tuple(decodificar(args[0], v, f"{campo}[{i}]") for i, v in enumerate(bruto))
    if origem is list:
        (item,) = get_args(tipo)
        if not isinstance(bruto, list):
            raise _ErroLeitura(campo, f"esperado lista, veio {_tipo_json(bruto)}")
        return [decodificar(item, v, f"{campo}[{i}]") for i, v in enumerate(bruto)]
    if origem is dict:
        chave_t, valor_t = get_args(tipo)
        if chave_t is not str:
            raise _ErroLeitura(campo, f"chave de dict não suportada: {chave_t!r}")
        if not isinstance(bruto, dict):
            raise _ErroLeitura(campo, f"esperado objeto, veio {_tipo_json(bruto)}")
        return {k: decodificar(valor_t, v, f"{campo}.{k}") for k, v in bruto.items()}

    if tipo is bool:
        if not isinstance(bruto, bool):
            raise _ErroLeitura(campo, f"esperado bool, veio {_tipo_json(bruto)}")
        return bruto
    if tipo is int:
        if isinstance(bruto, bool) or not isinstance(bruto, int):
            raise _ErroLeitura(campo, f"esperado int, veio {_tipo_json(bruto)}")
        return bruto
    if tipo is float:
        if isinstance(bruto, bool) or not isinstance(bruto, int | float):
            raise _ErroLeitura(campo, f"esperado número, veio {_tipo_json(bruto)}")
        if not math.isfinite(bruto):
            raise _ErroLeitura(campo, "número não finito")
        return float(bruto)
    if tipo is str:
        if not isinstance(bruto, str):
            raise _ErroLeitura(campo, f"esperado texto, veio {_tipo_json(bruto)}")
        return bruto
    if tipo is Decimal:
        if not isinstance(bruto, str):
            raise _ErroLeitura(campo, f"esperado texto decimal, veio {_tipo_json(bruto)}")
        try:
            numero = Decimal(bruto)
        except InvalidOperation as erro:
            raise _ErroLeitura(campo, "decimal inválido") from erro
        if not numero.is_finite():
            raise _ErroLeitura(campo, "decimal não finito")
        return numero
    if tipo is datetime:
        if not isinstance(bruto, str):
            raise _ErroLeitura(campo, f"esperado texto ISO 8601, veio {_tipo_json(bruto)}")
        try:
            momento = datetime.fromisoformat(bruto)
        except ValueError as erro:
            raise _ErroLeitura(campo, "datetime inválido") from erro
        if momento.utcoffset() is None:
            raise _ErroLeitura(campo, "datetime sem fuso")
        return momento
    if isinstance(tipo, type) and issubclass(tipo, Enum):
        try:
            return tipo(bruto)
        except ValueError as erro:
            raise _ErroLeitura(campo, f"valor fora do enum {tipo.__name__}") from erro
    if isinstance(tipo, type) and is_dataclass(tipo):
        return _decodificar_dataclass(tipo, bruto, campo)
    raise _ErroLeitura(campo, f"tipo não suportado: {tipo!r}")


# ----------------------------------------------------------------------------- texto


def serializar_estado(estado: EstadoPersistido) -> str:
    """Texto JSON do snapshot (com `versao`). Levanta `ErroSerializacao`."""
    corpo = {
        "versao": VERSAO_FORMATO,
        "estado": {f.name: codificar(getattr(estado, f.name), f.name) for f in fields(estado)},
    }
    return json.dumps(corpo, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _rejeitar_constante(nome: str) -> Any:
    raise ValueError(f"constante JSON não permitida: {nome}")


def ler_estado(texto: str, caminho: Path) -> EstadoPersistido:
    """Texto JSON -> `EstadoPersistido`.

    Levanta `ErroSnapshot` para JSON inválido, versão ausente ou diferente e estrutura
    que o Serializador não reconhece. `caminho` só identifica o arquivo na mensagem.
    """
    try:
        corpo = json.loads(texto, parse_constant=_rejeitar_constante)
    except (ValueError, RecursionError) as erro:
        raise ErroSnapshot(caminho, f"JSON inválido: {erro}") from erro
    if not isinstance(corpo, dict):
        raise ErroSnapshot(caminho, "estrutura não reconhecida: esperado objeto na raiz")
    if "versao" not in corpo:
        raise ErroSnapshot(caminho, "campo 'versao' ausente")
    versao = corpo["versao"]
    if isinstance(versao, bool) or versao != VERSAO_FORMATO:
        raise ErroSnapshot(
            caminho, f"versão do formato {versao!r} não suportada (esperada {VERSAO_FORMATO})"
        )
    desconhecidas = sorted(set(corpo) - {"versao", "estado"})
    if desconhecidas:
        raise ErroSnapshot(caminho, f"estrutura não reconhecida: campo {desconhecidas[0]!r}")
    if "estado" not in corpo:
        raise ErroSnapshot(caminho, "estrutura não reconhecida: campo 'estado' ausente")
    try:
        return _decodificar_dataclass(
            EstadoPersistido, corpo["estado"], "estado", exigir_todos=True
        )
    except _ErroLeitura as erro:
        raise ErroSnapshot(caminho, f"estrutura não reconhecida: {erro}") from erro


# ----------------------------------------------------------------------------- captura / aplicação
#
# Único ponto de acoplamento aos `_itens` privados dos fakes de `repositorios/memoria.py`.
# Chaves usadas por cada fake:
#   jornadas: jornada_id | eventos: (jornada_id, ts_ulid) | chamados: numero
#   mensagens / acessos_pii: numero -> lista (ordem de inserção) | dados_pessoais: numero
#   ordens_servico: os_id_de(numero) | cache: chave | avaliacoes: jornada_id
#   agregados: (dia, metrica) -> valor | config: chave -> valor


def capturar_estado(repos: Repositorios) -> EstadoPersistido:
    """Cópia rasa e consistente, tirada sob a RLock compartilhada pelos fakes.

    Os registros são imutáveis; `Evento.dados`, `RegistroCache.fontes` e `Config` só são
    trocados, nunca alterados no lugar (a `Config` é copiada fundo por garantia).
    """
    with repos.jornadas._trava:
        return EstadoPersistido(
            jornadas=list(repos.jornadas._itens.values()),
            eventos=list(repos.eventos._itens.values()),
            chamados=list(repos.chamados._itens.values()),
            mensagens=[m for lista in repos.mensagens._itens.values() for m in lista],
            dados_pessoais=list(repos.dados_pessoais._itens.values()),
            acessos_pii=[a for lista in repos.acessos_pii._itens.values() for a in lista],
            ordens_servico=list(repos.ordens_servico._itens.values()),
            cache=list(repos.cache._itens.values()),
            avaliacoes=list(repos.avaliacoes._itens.values()),
            agregados=[AgregadoDia(d, m, v) for (d, m), v in repos.agregados._itens.items()],
            config=copy.deepcopy(repos.config._itens),
        )


def aplicar_estado(repos: Repositorios, estado: EstadoPersistido) -> None:
    """Restaura o estado direto nos `_itens` dos repositórios existentes.

    Não troca a instância de `Repositorios` e não chama `criar`, `assumir` nem `encerrar`
    (Req 7.5). Tudo ou nada: os dicionários novos são montados antes de entrar na trava, e
    só então cada `_itens` recebe `clear()` + `update()`. A ordem do snapshot é a ordem
    restaurada, inclusive nas listas de mensagens e acessos de cada Chamado.
    """
    jornadas = {j.jornada_id: j for j in estado.jornadas}
    eventos = {(e.jornada_id, e.ts_ulid): e for e in estado.eventos}
    chamados = {c.numero: c for c in estado.chamados}
    mensagens: dict[str, list[MensagemChamado]] = {}
    for m in estado.mensagens:
        mensagens.setdefault(m.numero, []).append(m)
    dados_pessoais = {d.numero: d for d in estado.dados_pessoais}
    acessos: dict[str, list[AcessoPII]] = {}
    for a in estado.acessos_pii:
        acessos.setdefault(a.numero, []).append(a)
    ordens = {os_id_de(o.numero): o for o in estado.ordens_servico}
    cache = {r.chave: r for r in estado.cache}
    avaliacoes = {a.jornada_id: a for a in estado.avaliacoes}
    agregados = {(a.dia, a.metrica): a.valor for a in estado.agregados}
    config = copy.deepcopy(estado.config)

    with repos.jornadas._trava:
        for itens, novos in (
            (repos.jornadas._itens, jornadas),
            (repos.eventos._itens, eventos),
            (repos.chamados._itens, chamados),
            (repos.mensagens._itens, mensagens),
            (repos.dados_pessoais._itens, dados_pessoais),
            (repos.acessos_pii._itens, acessos),
            (repos.ordens_servico._itens, ordens),
            (repos.cache._itens, cache),
            (repos.avaliacoes._itens, avaliacoes),
            (repos.agregados._itens, agregados),
            (repos.config._itens, config),
        ):
            itens.clear()
            itens.update(novos)


# ----------------------------------------------------------------------------- persistência


class Persistencia:
    """Gravação atômica, leitura e remoção do snapshot em `diretorio/estado.json`."""

    def __init__(self, diretorio: Path, log: Callable[[str], None] = print) -> None:
        self.diretorio = diretorio
        self.caminho = diretorio / NOME_SNAPSHOT
        self.temporario = diretorio / NOME_TEMPORARIO
        self._log = log
        self._trava = threading.Lock()  # serializa as gravações (Req 1.6)

    def gravar(self, repos: Repositorios) -> bool:
        """Captura + serializa + grava, tudo sob a trava de gravação. Nunca levanta.

        A serialização acontece antes de abrir qualquer arquivo: se ela falhar, o snapshot
        anterior fica intacto (Req 4.9). O log traz só o caminho e o erro, nunca o estado.
        """
        with self._trava:
            try:
                texto = serializar_estado(capturar_estado(repos))
                self._gravar_texto(texto)
                return True
            except Exception as erro:  # noqa: BLE001 - a demo segue sem persistir
                try:
                    self._log(
                        f"ERRO ao gravar o estado em {self.caminho}: "
                        f"{type(erro).__name__}: {erro}"
                    )
                except Exception:  # noqa: BLE001 - o log também não pode derrubar a requisição
                    pass
                return False

    def _gravar_texto(self, texto: str) -> None:
        self.diretorio.mkdir(parents=True, exist_ok=True)  # Req 1.7
        try:
            with open(self.temporario, "w", encoding="utf-8") as arq:
                arq.write(texto)
                arq.flush()
                os.fsync(arq.fileno())
            os.replace(self.temporario, self.caminho)  # Req 1.3
        except BaseException:
            try:
                self.temporario.unlink(missing_ok=True)  # Req 1.4
            except OSError:
                pass  # preserva o erro original da gravação
            raise

    def carregar(self) -> EstadoPersistido:
        """Lê e valida o snapshot. Qualquer falha de leitura ou formato vira `ErroSnapshot`."""
        try:
            texto = self.caminho.read_text(encoding="utf-8")
        except UnicodeDecodeError as erro:
            raise ErroSnapshot(self.caminho, f"arquivo não é UTF-8 válido: {erro}") from erro
        except OSError as erro:
            raise ErroSnapshot(self.caminho, f"não foi possível ler o arquivo: {erro}") from erro
        return ler_estado(texto, self.caminho)

    def apagar(self) -> None:
        """Remove `estado.json` e `estado.json.tmp`. Arquivos ausentes não são erro."""
        for alvo in (self.caminho, self.temporario):
            alvo.unlink(missing_ok=True)
