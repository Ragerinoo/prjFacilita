"""Ajudantes de validação de JSON no estilo `dominio.ErroCampo` (campo + motivo).

`Validador` acumula TODOS os campos inválidos (não para no primeiro) e devolve um 422 com a
lista no envelope padrão. As regras de negócio (telefone, CEP, nota...) continuam em
`dominio.validadores`; use `levantar_se_invalido` para converter o resultado delas.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from core.erros import json_invalido, validacao
from dominio import ErroCampo

_AUSENTE = object()


def exigir_objeto(corpo: Any) -> Mapping[str, Any]:
    """O corpo precisa ser um objeto JSON (`{...}`)."""
    if not isinstance(corpo, Mapping):
        raise json_invalido("O corpo da requisição deve ser um objeto JSON.")
    return corpo


def levantar_se_invalido(erros: Iterable[ErroCampo]) -> None:
    """Converte uma lista de `ErroCampo` (por exemplo de `dominio`) em 422, se não vazia."""
    lista = list(erros)
    if lista:
        raise validacao(lista)


class Validador:
    """Lê campos tipados de um objeto JSON, acumulando erros.

    Cada leitor devolve o valor válido ou `padrao` (campo opcional ausente / inválido).
    Chame `levantar_se_erros()` no fim para responder 422 com todos os erros de uma vez.
    """

    def __init__(self, dados: Mapping[str, Any]) -> None:
        self._dados = dados
        self.erros: list[ErroCampo] = []

    # -- leitores ---------------------------------------------------------------------------
    def texto(
        self,
        nome: str,
        *,
        obrigatorio: bool = True,
        minimo: int = 1,
        maximo: int | None = None,
        padrao: str | None = None,
        aceita_so_espacos: bool = False,
    ) -> str | None:
        valor = self._dados.get(nome, _AUSENTE)
        if valor is _AUSENTE or valor is None:
            if obrigatorio:
                self._erro(nome, "é obrigatório")
            return padrao
        if not isinstance(valor, str):
            self._erro(nome, "deve ser um texto")
            return padrao
        if not aceita_so_espacos and minimo > 0 and not valor.strip():
            self._erro(nome, "não pode ficar vazio")
            return padrao
        if len(valor) < minimo:
            self._erro(nome, f"deve ter no mínimo {minimo} caractere(s)")
            return padrao
        if maximo is not None and len(valor) > maximo:
            self._erro(nome, f"deve ter no máximo {maximo} caracteres")
            return padrao
        return valor

    def inteiro(
        self,
        nome: str,
        *,
        obrigatorio: bool = True,
        minimo: int | None = None,
        maximo: int | None = None,
        padrao: int | None = None,
    ) -> int | None:
        valor = self._dados.get(nome, _AUSENTE)
        if valor is _AUSENTE or valor is None:
            if obrigatorio:
                self._erro(nome, "é obrigatório")
            return padrao
        if isinstance(valor, bool) or not isinstance(valor, int):
            self._erro(nome, "deve ser um número inteiro")
            return padrao
        if minimo is not None and valor < minimo:
            self._erro(nome, f"deve ser no mínimo {minimo}")
            return padrao
        if maximo is not None and valor > maximo:
            self._erro(nome, f"deve ser no máximo {maximo}")
            return padrao
        return valor

    def booleano(
        self, nome: str, *, obrigatorio: bool = True, padrao: bool | None = None
    ) -> bool | None:
        valor = self._dados.get(nome, _AUSENTE)
        if valor is _AUSENTE or valor is None:
            if obrigatorio:
                self._erro(nome, "é obrigatório")
            return padrao
        if not isinstance(valor, bool):
            self._erro(nome, "deve ser verdadeiro ou falso")
            return padrao
        return valor

    def escolha(
        self,
        nome: str,
        opcoes: Sequence[str],
        *,
        obrigatorio: bool = True,
        padrao: str | None = None,
    ) -> str | None:
        valor = self._dados.get(nome, _AUSENTE)
        if valor is _AUSENTE or valor is None:
            if obrigatorio:
                self._erro(nome, "é obrigatório")
            return padrao
        if not isinstance(valor, str) or valor not in opcoes:
            self._erro(nome, f"deve ser um de: {', '.join(opcoes)}")
            return padrao
        return valor

    # -- erros ------------------------------------------------------------------------------
    def _erro(self, campo: str, motivo: str) -> None:
        self.erros.append(ErroCampo(campo, motivo))

    def adicionar(self, erros: Iterable[ErroCampo]) -> None:
        """Junta erros vindos de validadores de `dominio`."""
        self.erros.extend(erros)

    @property
    def valido(self) -> bool:
        return not self.erros

    def levantar_se_erros(self) -> None:
        if self.erros:
            raise validacao(self.erros)
