#!/usr/bin/env python3
"""Servidor LOCAL de demonstração: roda a Lambda `api` sem AWS (repositórios em memória).

Converte cada requisição HTTP em um evento do API Gateway HTTP API (payload v2), chama
`core.processar` e devolve a resposta. Também serve `seed/midia` em `/midia/*`.

Uso (a partir da raiz do repositório):

    .venv-demo/bin/python scripts/dev_local.py [--porta 8000] [--host 127.0.0.1] \
        [--inseguro-local] [--sem-demo] [--resetar]

SOMENTE PARA DEMO/DESENVOLVIMENTO: os repositórios ficam em memória, mas o estado é salvo em
``.dados-demo/estado.json`` (snapshot JSON gravado após cada requisição que não seja GET/HEAD) e
recarregado ao subir; ``--resetar`` apaga esse estado e recomeça do zero. Usuários e sessões do
Painel_CS não vão para o snapshot: depois de reiniciar é preciso entrar de novo. Senha de
demonstração conhecida e, com ``--inseguro-local`` (ligado por padrão aqui), o atributo ``Secure``
do cookie de sessão é removido para funcionar em http://localhost. Nunca use isto fora da sua
máquina. O snapshot pode conter telefone e CEP digitados na demo.
Ao executar o script (``__main__``), a primeira subida (ou ``--resetar``) cria, além dos 3
Chamados de exemplo, a semente de demonstração (Jornadas, Chamados e Avaliações FICTÍCIOS para o painel de
insights do Gestor); ``--sem-demo`` desliga as duas coisas. Subidas seguintes, com snapshot, nunca
recriam a semente.
Variáveis lidas (só nomes): ``CS_SENHA_INICIAL``, ``PORT``.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

_RAIZ = Path(__file__).resolve().parent.parent
for _caminho in (
    _RAIZ / "services" / "api",
    _RAIZ / "packages" / "dominio" / "src",
    _RAIZ / "scripts",
):
    if str(_caminho) not in sys.path:
        sys.path.insert(0, str(_caminho))

from core import criar_app, criar_roteador, processar  # noqa: E402
from estado_demo import ErroSnapshot, Persistencia, aplicar_estado  # noqa: E402
from repositorios.catalogo import CatalogoMemoria  # noqa: E402
from repositorios.modelos import Jornada, UsuarioCS  # noqa: E402
from semente_demo import criar_semente  # noqa: E402
from servicos import senhas  # noqa: E402

SEED = _RAIZ / "seed"
MIDIA = SEED / "midia"
DIR_DADOS_DEMO = _RAIZ / ".dados-demo"
METODOS_LEITURA = frozenset({"GET", "HEAD"})
SENHA_PADRAO = "demo-tres-2025"
LIMITE_CORPO = 1024 * 1024


# --------------------------------------------------------------------------- seed / demo


def _sem_comentarios(valor):
    if isinstance(valor, dict):
        return {k: _sem_comentarios(v) for k, v in valor.items() if not k.startswith("_")}
    if isinstance(valor, list):
        return [_sem_comentarios(v) for v in valor]
    return valor


def _json(*partes: str):
    return _sem_comentarios(json.loads(SEED.joinpath(*partes).read_text(encoding="utf-8")))


def itens_do_seed() -> tuple[list[dict], list[dict], list[dict]]:
    """Modelos (com o seletor embutido), problemas e instruções, como o seed grava."""
    modelos = _json("catalogo.json")["modelos"]
    for modelo in modelos:
        arquivo = SEED / "seletor" / f"{modelo['modelo_id']}.json"
        if arquivo.exists():
            modelo["seletor"] = _json("seletor", arquivo.name)
    instrucoes: list[dict] = []
    for arquivo in sorted((SEED / "instrucoes").glob("*.json")):
        instrucoes.extend(_json("instrucoes", arquivo.name)["instrucoes"])
    return modelos, _json("problemas.json")["problemas"], instrucoes


def popular(app, senha: str, com_demo: bool) -> None:
    repos = app.repos
    modelos, problemas, instrucoes = itens_do_seed()
    object.__setattr__(repos, "catalogo", CatalogoMemoria.de_itens(modelos, problemas, instrucoes))

    for usuario in ("atendente", "gestor"):
        repos.usuarios_cs.criar(
            UsuarioCS(
                usuario=usuario,
                hash_senha=senhas.gerar_hash(senha),
                perfil=usuario,  # type: ignore[arg-type]
                deve_trocar_senha=False,
            )
        )
    if com_demo:
        _chamados_de_exemplo(app)


def _chamados_de_exemplo(app) -> None:
    """Chamados FICTÍCIOS (dados de demonstração) para o Painel não abrir vazio."""
    agora = datetime.now(UTC)
    exemplos = (
        ("01JDEMO0000000000000000P1", "tres-passione", "risco_seguranca"),
        ("01JDEMO0000000000000000P2", "tres-circo", "pedido_humano"),
        ("01JDEMO0000000000000000P3", "tres-mimo", "sem_embasamento"),
    )
    for jid, modelo, gatilho in exemplos:
        app.repos.jornadas.criar(
            Jornada(
                jornada_id=jid,
                criada_em=agora,
                ultima_interacao=agora,
                origem="qr",
                origem_inicial="qr",
                modelo_id=modelo,
            )
        )
        try:
            resultado = app.escalada.escalar(jid, gatilho)  # type: ignore[arg-type]
            print(f"  [demo] Chamado de exemplo {resultado.numero} ({gatilho})")
        except Exception as erro:  # noqa: BLE001 - dados de exemplo são opcionais
            print(f"  [demo] não foi possível criar o chamado de exemplo ({gatilho}): {erro!r}")


# --------------------------------------------------------------------------- HTTP <-> evento v2

_SECURE = re.compile(r";\s*Secure\b", re.IGNORECASE)


def construir_handler(
    app, roteador, *, inseguro_local: bool, persistencia: Persistencia | None = None
):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "TresDevLocal"

        def log_message(self, formato, *args):  # noqa: A003
            print(f"{self.address_string()} {formato % args}")

        def _responder(self, status: int, cabecalhos: list[tuple[str, str]], corpo: bytes):
            self.send_response(status)
            for nome, valor in cabecalhos:
                self.send_header(nome, valor)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(corpo)

        def _api(self):
            partes = urlsplit(self.path)
            tamanho = int(self.headers.get("Content-Length") or 0)
            if tamanho > LIMITE_CORPO:
                return 413, [("Content-Type", "text/plain")], b"corpo grande"
            corpo = self.rfile.read(tamanho).decode("utf-8", errors="replace") if tamanho else ""
            cabecalhos = {k.lower(): v for k, v in self.headers.items()}
            evento = {
                "version": "2.0",
                "rawPath": partes.path,
                "rawQueryString": partes.query,
                "headers": cabecalhos,
                "queryStringParameters": dict(parse_qsl(partes.query)) or None,
                "requestContext": {
                    "requestId": f"local-{os.urandom(4).hex()}",
                    "http": {"method": self.command, "path": partes.path},
                },
                "body": corpo or None,
                "isBase64Encoded": False,
            }
            resposta = processar(app, roteador, evento)
            saida = [(k, str(v)) for k, v in (resposta.get("headers") or {}).items()]
            for cookie in resposta.get("cookies") or ():
                if inseguro_local:
                    cookie = _SECURE.sub("", cookie)
                saida.append(("Set-Cookie", cookie))
            return (
                int(resposta["statusCode"]),
                saida,
                (resposta.get("body") or "").encode("utf-8"),
            )

        def _estatico(self):
            relativo = unquote(urlsplit(self.path).path)[len("/midia/") :]
            arquivo = (MIDIA / relativo).resolve()
            if MIDIA.resolve() not in arquivo.parents or not arquivo.is_file():
                return self._responder(404, [("Content-Type", "text/plain")], b"nao encontrado")
            tipo = mimetypes.guess_type(arquivo.name)[0] or "application/octet-stream"
            self._responder(
                200,
                [("Content-Type", tipo), ("Cache-Control", "public, max-age=60")],
                arquivo.read_bytes(),
            )

        def _tratar(self):
            caminho = urlsplit(self.path).path
            try:
                if caminho.startswith("/api/") or caminho == "/api":
                    status, cabecalhos, corpo = self._api()
                    if persistencia is not None and self.command not in METODOS_LEITURA:
                        persistencia.gravar(app.repos)  # nunca levanta
                    return self._responder(status, cabecalhos, corpo)
                if caminho.startswith("/midia/") and self.command in METODOS_LEITURA:
                    return self._estatico()
                self._responder(404, [("Content-Type", "text/plain")], b"nao encontrado")
            except Exception as erro:  # noqa: BLE001
                print(f"ERRO interno: {erro!r}")
                self._responder(500, [("Content-Type", "text/plain")], b"erro interno")

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _tratar  # noqa: N815

    return Handler


def iniciar_estado(
    app,
    senha: str,
    persistencia: Persistencia,
    *,
    resetar: bool,
    com_demo: bool,
    com_semente: bool = False,
    agora_semente: datetime | None = None,
    log=print,
) -> str:
    """Prepara os repositórios. Devolve ``'carregado'``, ``'novo'`` ou ``'resetado'``.

    Só no ramo sem snapshot (``'novo'``/``'resetado'``), com ``com_demo`` e ``com_semente``, cria
    a semente de demonstração (``agora_semente`` ou ``datetime.now(UTC)``) antes de gravar o
    snapshot inicial; falha na semente é registrada em ``log`` e não interrompe a subida.

    Levanta ``ErroSnapshot`` (snapshot ilegível) sem alterar arquivo algum nem a aplicação:
    a leitura e a validação acontecem antes de ``popular()``.
    """
    if resetar:
        persistencia.apagar()
    if persistencia.caminho.exists():
        estado = persistencia.carregar()
        popular(app, senha, com_demo=False)  # usuários (senha vigente) + catálogo do seed
        aplicar_estado(app.repos, estado)
        return "carregado"
    popular(app, senha, com_demo=com_demo)
    if com_demo and com_semente:
        try:
            criar_semente(app.repos, agora=agora_semente or datetime.now(UTC), log=log)
        except Exception as erro:  # noqa: BLE001 - a semente é opcional
            log(f"[demo] não foi possível criar a semente: {erro}")
    persistencia.gravar(app.repos)  # snapshot inicial; nunca levanta
    return "resetado" if resetar else "novo"


def main(
    argv: list[str] | None = None,
    *,
    dir_dados: Path = DIR_DADOS_DEMO,
    com_semente: bool = False,
) -> int:
    persistencia = Persistencia(dir_dados)
    caminho_ajuda = str(persistencia.caminho).replace("%", "%%")
    p = argparse.ArgumentParser(
        description=(
            "API local de demonstração (sem AWS). "
            f"O estado é salvo em {caminho_ajuda} e recarregado ao subir."
        )
    )
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--porta", type=int, default=int(os.environ.get("PORT", "8000")))
    p.add_argument(
        "--inseguro-local",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="remove 'Secure' do cookie de sessão (padrão: ligado; use --no-inseguro-local)",
    )
    p.add_argument(
        "--sem-demo",
        action="store_true",
        help=(
            "não cria Chamados de exemplo nem a semente de demonstração "
            "(na primeira subida ou com --resetar)"
        ),
    )
    p.add_argument(
        "--resetar",
        action="store_true",
        help=f"APAGA o estado salvo em {caminho_ajuda} e recomeça do zero",
    )
    args = p.parse_args(argv)

    senha = os.environ.get("CS_SENHA_INICIAL") or SENHA_PADRAO
    app = criar_app({}, modo="local")
    try:
        situacao = iniciar_estado(
            app,
            senha,
            persistencia,
            resetar=args.resetar,
            com_demo=not args.sem_demo,
            com_semente=com_semente and not args.sem_demo,
        )
    except ErroSnapshot as erro:
        print(
            f"ERRO: não foi possível ler o estado salvo em {persistencia.caminho}: {erro.motivo}\n"
            "O arquivo não foi alterado. Para recomeçar do zero (APAGA o estado salvo), "
            "suba o servidor com --resetar.",
            file=sys.stderr,
        )
        return 2
    handler = construir_handler(
        app, criar_roteador(), inseguro_local=args.inseguro_local, persistencia=persistencia
    )

    servidor = ThreadingHTTPServer((args.host, args.porta), handler)
    descricao = {
        "carregado": "estado carregado do arquivo",
        "novo": "primeira subida, estado criado",
        "resetado": "estado apagado e recriado",
    }[situacao]
    print(
        f"API local em http://{args.host}:{args.porta}  "
        f"(estado salvo em {persistencia.caminho}; {descricao})"
    )
    print(f"Login do Painel_CS: atendente / gestor  |  senha: {senha}  (SOMENTE DEMO)")
    if args.inseguro_local:
        print("Cookie de sessão SEM 'Secure' (modo inseguro-local).")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(com_semente=True))
