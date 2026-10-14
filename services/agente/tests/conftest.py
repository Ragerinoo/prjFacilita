"""Perfis do Hypothesis: `default` com 100 exemplos e `ci` com 200.

Selecione com a variável de ambiente HYPOTHESIS_PROFILE (ex.: HYPOTHESIS_PROFILE=ci).
"""

import os

from hypothesis import HealthCheck, settings

settings.register_profile(
    "default",
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile(
    "ci",
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "default"))
