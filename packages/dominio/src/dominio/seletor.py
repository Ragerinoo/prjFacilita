"""Seletor_Visual puro (Req 4).

O mapa por modelo (`seed/seletor/<modelo_id>.json`) tem áreas em porcentagem da
imagem, estados aplicáveis por área e regras `(area, estado) -> [problema_id]`.
Funções puras, sem I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from numbers import Real
from typing import Any, Literal

from dominio.pacote import ErroCampo

MIN_ESTADOS = 2  # Req 4.2
MAX_ESTADOS = 5  # Req 4.2
MAX_OPCOES = 5  # Req 4.6
# 16% x 12% garante 44x44 px CSS a partir de 320 px de largura (Req 4.5, seed/README.md).
LARGURA_MIN_PCT = 16
ALTURA_MIN_PCT = 12

TipoResolucao = Literal["unico", "multiplos", "nenhum"]


@dataclass(frozen=True, slots=True)
class ResolucaoSeletor:
    """Resultado de `resolver_seletor`.

    `unico`: abre a instrução do único problema (Req 4.3).
    `multiplos`: lista até 5 problemas para o Consumidor escolher (Req 4.6).
    `nenhum`: vai ao Assistente_IA com área e estado registrados (Req 4.4).
    """

    tipo: TipoResolucao
    area: str
    estado: str
    problemas: tuple[int | str, ...] = ()


def resolver_seletor(mapa: Mapping[str, Any], area: str, estado: str) -> ResolucaoSeletor:
    """Resolve `(area, estado)` nas regras do mapa. Determinística e sem exceções.

    Regras repetidas para o mesmo par somam seus problemas (sem repetir, na ordem
    em que aparecem). Mais de 5 problemas são cortados nos 5 primeiros.
    """
    problemas: list[int | str] = []
    regras = mapa.get("regras") if isinstance(mapa, Mapping) else None
    if isinstance(regras, (list, tuple)):
        for regra in regras:
            if not isinstance(regra, Mapping):
                continue
            if regra.get("area") != area or regra.get("estado") != estado:
                continue
            ids = regra.get("problemas")
            if not isinstance(ids, (list, tuple)):
                continue
            for pid in ids:
                if pid not in problemas:
                    problemas.append(pid)
    problemas = problemas[:MAX_OPCOES]
    if not problemas:
        return ResolucaoSeletor("nenhum", area, estado)
    tipo: TipoResolucao = "unico" if len(problemas) == 1 else "multiplos"
    return ResolucaoSeletor(tipo, area, estado, tuple(problemas))


# --------------------------------------------------------------------------- #
# Validação do mapa
# --------------------------------------------------------------------------- #


def _eh_numero(v: Any) -> bool:
    return isinstance(v, Real) and not isinstance(v, bool)


def _retangulo(forma: Any) -> tuple[Real, Real, Real, Real] | None:
    """(x, y, largura, altura) de uma forma retangular válida, ou `None`."""
    if not isinstance(forma, Mapping) or forma.get("tipo") != "retangulo":
        return None
    x, y, w, h = (forma.get(k) for k in ("x", "y", "largura", "altura"))
    if not all(_eh_numero(v) for v in (x, y, w, h)):
        return None
    return x, y, w, h  # type: ignore[return-value]


def _sobrepoem(a: tuple, b: tuple) -> bool:
    """Interiores se cruzam. Bordas que apenas se tocam não contam como sobreposição."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def validar_mapa(mapa: Any) -> list[ErroCampo]:
    """Valida o mapa do Seletor_Visual; lista vazia significa válido.

    Verifica: áreas com formas retangulares dentro da imagem (0 a 100%) e sem
    sobreposição entre si (Req 4.1); de 2 a 5 estados por área, sem repetição
    (Req 4.2); e regras que apontam para área e estado existentes, com 1 a 5
    problemas cada (Req 4.6). Só a forma `retangulo` é suportada no MVP.
    Nunca lança exceção. O tamanho mínimo tocável fica em `validar_tamanho_areas`.
    """
    if not isinstance(mapa, Mapping):
        return [ErroCampo("mapa", "deve ser um objeto")]
    areas = mapa.get("areas")
    if not isinstance(areas, (list, tuple)) or not areas:
        return [ErroCampo("areas", "deve ser uma lista com ao menos uma área")]

    erros: list[ErroCampo] = []
    retangulos: list[tuple[str, tuple]] = []
    estados_por_area: dict[str, set[Any]] = {}

    for i, area in enumerate(areas):
        base = f"areas[{i}]"
        if not isinstance(area, Mapping):
            erros.append(ErroCampo(base, "deve ser um objeto"))
            continue
        nome = area.get("area")
        if not isinstance(nome, str) or not nome.strip():
            erros.append(ErroCampo(f"{base}.area", "identificador obrigatório"))
            nome = f"#{i}"
        elif nome in estados_por_area:
            erros.append(ErroCampo(f"{base}.area", f"identificador repetido: {nome}"))

        rotulo = area.get("rotulo")
        if not isinstance(rotulo, str) or not rotulo.strip():
            erros.append(ErroCampo(f"{base}.rotulo", "rótulo acessível obrigatório (Req 4.5)"))

        ret = _retangulo(area.get("forma"))
        if ret is None:
            erros.append(ErroCampo(f"{base}.forma", "esperado retangulo com x, y, largura, altura"))
        else:
            x, y, w, h = ret
            if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > 100 or y + h > 100:
                erros.append(ErroCampo(f"{base}.forma", "deve estar dentro da imagem (0 a 100%)"))
            else:
                retangulos.append((nome, ret))

        estados = area.get("estados")
        ids: list[Any] = []
        if isinstance(estados, (list, tuple)):
            for e in estados:
                ids.append(e.get("estado") if isinstance(e, Mapping) else None)
        else:
            estados = None
        if estados is None or not MIN_ESTADOS <= len(estados) <= MAX_ESTADOS:
            qtd = len(estados) if estados is not None else 0
            erros.append(
                ErroCampo(
                    f"{base}.estados",
                    f"deve ter de {MIN_ESTADOS} a {MAX_ESTADOS} estados (tem {qtd})",
                )
            )
        if any(not isinstance(e, str) or not e.strip() for e in ids):
            erros.append(ErroCampo(f"{base}.estados", "cada estado precisa de identificador"))
        if len(set(map(str, ids))) != len(ids):
            erros.append(ErroCampo(f"{base}.estados", "estados repetidos"))
        estados_por_area.setdefault(nome, set()).update(e for e in ids if isinstance(e, str))

    for i, (nome_a, ret_a) in enumerate(retangulos):
        for nome_b, ret_b in retangulos[i + 1 :]:
            if _sobrepoem(ret_a, ret_b):
                erros.append(ErroCampo("areas", f"as áreas {nome_a} e {nome_b} se sobrepõem"))

    regras = mapa.get("regras", [])
    if not isinstance(regras, (list, tuple)):
        erros.append(ErroCampo("regras", "deve ser uma lista"))
        return erros
    for i, regra in enumerate(regras):
        base = f"regras[{i}]"
        if not isinstance(regra, Mapping):
            erros.append(ErroCampo(base, "deve ser um objeto"))
            continue
        a, e = regra.get("area"), regra.get("estado")
        if a not in estados_por_area:
            erros.append(ErroCampo(f"{base}.area", "área inexistente no mapa"))
        elif e not in estados_por_area[a]:
            erros.append(ErroCampo(f"{base}.estado", f"estado inexistente na área {a}"))
        ids_p = regra.get("problemas")
        if not isinstance(ids_p, (list, tuple)) or not 1 <= len(ids_p) <= MAX_OPCOES:
            erros.append(ErroCampo(f"{base}.problemas", f"deve ter de 1 a {MAX_OPCOES} problemas"))
        elif len(set(map(str, ids_p))) != len(ids_p):
            erros.append(ErroCampo(f"{base}.problemas", "problemas repetidos"))
    return erros


def validar_tamanho_areas(mapa: Any) -> list[ErroCampo]:
    """Cada área retangular deve medir ao menos 16% x 12% da imagem (Req 4.5: 44x44 px)."""
    erros: list[ErroCampo] = []
    areas = mapa.get("areas") if isinstance(mapa, Mapping) else None
    if not isinstance(areas, (list, tuple)):
        return erros
    for i, area in enumerate(areas):
        ret = _retangulo(area.get("forma")) if isinstance(area, Mapping) else None
        if ret is not None and (ret[2] < LARGURA_MIN_PCT or ret[3] < ALTURA_MIN_PCT):
            erros.append(
                ErroCampo(
                    f"areas[{i}].forma",
                    f"tamanho mínimo {LARGURA_MIN_PCT}% x {ALTURA_MIN_PCT}% da imagem",
                )
            )
    return erros


def mapa_valido(mapa: Any) -> bool:
    """Atalho booleano de `validar_mapa`."""
    return not validar_mapa(mapa)
