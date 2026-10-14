"""Exceções do domínio."""

from __future__ import annotations


class ErroDominio(Exception):
    """Base das exceções do pacote `dominio`."""


class ErroMascaramento(ErroDominio):
    """Falha interna em `mascarar_pii`.

    Quando levantada, nada pode ser enviado ao modelo nem persistido (Req 18.3, 18.8).
    """
