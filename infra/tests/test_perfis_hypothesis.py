"""Garante os perfis do Hypothesis: 100 exemplos por padrão e 200 no perfil `ci`."""

import os

from hypothesis import settings


def test_perfil_default_tem_100_exemplos() -> None:
    perfil = os.getenv("HYPOTHESIS_PROFILE", "default")
    esperado = {"default": 100, "ci": 200}[perfil]
    assert settings().max_examples == esperado


def test_perfis_registrados() -> None:
    assert settings.get_profile("default").max_examples == 100
    assert settings.get_profile("ci").max_examples == 200
