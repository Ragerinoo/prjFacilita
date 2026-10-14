"""Prazo máximo para uma chamada bloqueante (por exemplo, a consulta ao Catalogo_Maquinas).

O cliente boto3 já tem timeouts curtos, mas o pior caso dele (várias tentativas) passa de 5 s.
`com_prazo` garante o teto: se a chamada não termina no prazo, levanta `TimeoutError` (que o
processamento converte em 504 ``tempo_esgotado``) e a rota segue sem esperar. A thread da
chamada atrasada termina sozinha; o resultado dela é descartado.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as PrazoEsgotado


def com_prazo[T](funcao: Callable[[], T], segundos: float) -> T:
    """Executa `funcao()` e devolve o resultado, ou levanta `TimeoutError` após `segundos`.

    Exceções da própria função sobem como estão.
    """
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="prazo")
    futuro = executor.submit(funcao)
    try:
        return futuro.result(timeout=segundos)
    except PrazoEsgotado:
        raise TimeoutError(f"sem resposta em {segundos} s") from None
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


__all__ = ["com_prazo"]
