"""Catálogo somente leitura: modelos, os 13 Problemas_Catalogados e as instruções.

As tabelas `modelos`, `problemas` e `instrucoes` são carregadas pelo seed
(`scripts/carregar_seed.py`); a API só lê (o papel da Lambda não tem escrita nelas). Este
módulo traz os registros, o `Protocol` `CatalogoRepo` e o fake em memória. O adaptador
DynamoDB está em `repositorios/dynamodb/catalogo.py`.

Formato dos itens (os mesmos que o seed grava):
  * `modelos` (PK `modelo_id`): `nome`, `nome_normalizado`, `foto_url`, `ativo`, `voltagens`,
    `manuais` e `seletor` (mapa do Seletor_Visual, repassado sem interpretação);
  * `problemas` (PK `problema_id`, número): `ordem`, `slug`, `titulo`, `icone`, `icone_alt`;
  * `instrucoes` (PK `modelo_id`, SK `problema_variante` = `"<problema_id>#<variante>"`).
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

VARIANTE_PADRAO: Final = "padrao"


@dataclass(frozen=True, slots=True)
class ModeloCatalogo:
    """Item da tabela `modelos`."""

    modelo_id: str
    nome: str
    nome_normalizado: str
    foto_url: str | None = None
    ativo: bool = True
    seletor: Mapping[str, Any] | None = None
    voltagens: tuple[str, ...] = ()
    manuais: tuple[str, ...] = ()

    @classmethod
    def de_item(cls, item: Mapping[str, Any]) -> ModeloCatalogo:
        seletor = item.get("seletor")
        return cls(
            modelo_id=str(item["modelo_id"]),
            nome=str(item["nome"]),
            nome_normalizado=str(item.get("nome_normalizado") or item["nome"]).lower(),
            foto_url=item.get("foto_url") or None,
            ativo=item.get("ativo", True) is not False,
            seletor=copy.deepcopy(dict(seletor)) if isinstance(seletor, Mapping) else None,
            voltagens=tuple(item.get("voltagens") or ()),
            manuais=tuple(item.get("manuais") or ()),
        )


@dataclass(frozen=True, slots=True)
class ProblemaCatalogo:
    """Item da tabela `problemas` (um dos 13 Problemas_Catalogados, Req 3.1)."""

    problema_id: int
    ordem: int
    titulo: str
    icone: str
    icone_alt: str
    slug: str = ""

    @classmethod
    def de_item(cls, item: Mapping[str, Any]) -> ProblemaCatalogo:
        problema_id = int(item["problema_id"])
        return cls(
            problema_id=problema_id,
            ordem=int(item.get("ordem", problema_id)),
            titulo=str(item["titulo"]),
            icone=str(item.get("icone") or ""),
            icone_alt=str(item.get("icone_alt") or ""),
            slug=str(item.get("slug") or ""),
        )


@dataclass(frozen=True, slots=True)
class InstrucaoCatalogo:
    """Item da tabela `instrucoes`. `dados` é o item completo, sem interpretação."""

    modelo_id: str
    problema_id: int
    variante: str
    dados: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def de_item(cls, item: Mapping[str, Any]) -> InstrucaoCatalogo:
        return cls(
            modelo_id=str(item["modelo_id"]),
            problema_id=int(item["problema_id"]),
            variante=str(item.get("variante") or VARIANTE_PADRAO),
            dados=copy.deepcopy(dict(item)),
        )


class CatalogoRepo(Protocol):
    """Leitura do Catalogo_Maquinas. Falha de infraestrutura levanta `ErroRepositorio`."""

    def listar_modelos(self) -> list[ModeloCatalogo]:
        """Todos os modelos (ativos e inativos), em ordem alfabética de `nome_normalizado`."""
        ...

    def obter_modelo(self, modelo_id: str) -> ModeloCatalogo | None: ...

    def listar_problemas(self) -> list[ProblemaCatalogo]:
        """Os Problemas_Catalogados na ordem do Req 3.1 (`ordem`, depois `problema_id`)."""
        ...

    def obter_instrucao(
        self, modelo_id: str, problema_id: int, variante: str = VARIANTE_PADRAO
    ) -> InstrucaoCatalogo | None: ...


class CatalogoMemoria:
    """Fake em memória de `CatalogoRepo`. Cópias na saída: o chamador não altera o estado."""

    def __init__(
        self,
        modelos: Iterable[ModeloCatalogo] = (),
        problemas: Iterable[ProblemaCatalogo] = (),
        instrucoes: Iterable[InstrucaoCatalogo] = (),
    ) -> None:
        self._modelos = {m.modelo_id: m for m in modelos}
        self._problemas = {p.problema_id: p for p in problemas}
        self._instrucoes = {(i.modelo_id, i.problema_id, i.variante): i for i in instrucoes}

    @classmethod
    def de_itens(
        cls,
        modelos: Iterable[Mapping[str, Any]] = (),
        problemas: Iterable[Mapping[str, Any]] = (),
        instrucoes: Iterable[Mapping[str, Any]] = (),
    ) -> CatalogoMemoria:
        """Monta o fake a partir de itens no formato do seed (`seed/*.json`)."""
        return cls(
            (ModeloCatalogo.de_item(m) for m in modelos),
            (ProblemaCatalogo.de_item(p) for p in problemas),
            (InstrucaoCatalogo.de_item(i) for i in instrucoes),
        )

    def listar_modelos(self) -> list[ModeloCatalogo]:
        return sorted(self._modelos.values(), key=lambda m: (m.nome_normalizado, m.modelo_id))

    def obter_modelo(self, modelo_id: str) -> ModeloCatalogo | None:
        return self._modelos.get(modelo_id)

    def listar_problemas(self) -> list[ProblemaCatalogo]:
        return sorted(self._problemas.values(), key=lambda p: (p.ordem, p.problema_id))

    def obter_instrucao(
        self, modelo_id: str, problema_id: int, variante: str = VARIANTE_PADRAO
    ) -> InstrucaoCatalogo | None:
        return self._instrucoes.get((modelo_id, problema_id, variante))


__all__ = [
    "VARIANTE_PADRAO",
    "CatalogoMemoria",
    "CatalogoRepo",
    "InstrucaoCatalogo",
    "ModeloCatalogo",
    "ProblemaCatalogo",
]
