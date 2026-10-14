"""Teste de fumaça do servidor local de demonstração (scripts/dev_local.py), sem AWS."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

_CAMINHO = Path(__file__).resolve().parent.parent / "dev_local.py"


@pytest.fixture(scope="module")
def servidor():
    spec = importlib.util.spec_from_file_location("dev_local", _CAMINHO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    app = modulo.criar_app({}, modo="local")
    modulo.popular(app, modulo.SENHA_PADRAO, com_demo=False)
    handler = modulo.construir_handler(app, modulo.criar_roteador(), inseguro_local=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", modulo
    httpd.shutdown()
    httpd.server_close()


def _chamar(base, metodo, caminho, corpo=None, cabecalhos=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(base + caminho, data=dados, method=metodo)
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Requested-With", "tres")
    for nome, valor in (cabecalhos or {}).items():
        req.add_header(nome, valor)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers), json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), json.loads(e.read() or b"null")


def test_modelo_da_demo_tem_13_problemas(servidor):
    base, _ = servidor
    status, _, corpo = _chamar(base, "GET", "/api/pub/modelos/tres-passione")
    assert status == 200
    assert len(corpo["problemas"]) == 13


def test_login_do_atendente_com_senha_de_demo(servidor):
    base, modulo = servidor
    status, cab, _ = _chamar(
        base,
        "POST",
        "/api/cs/login",
        {"usuario": "atendente", "senha": modulo.SENHA_PADRAO},
    )
    assert status == 200
    assert "Secure" not in cab.get("Set-Cookie", "")


# ---------------------------------------------------------------------------------------------
# Persistência local (snapshot em dir_dados). Tudo roda em diretório temporário: o
# `.dados-demo/` do repositório nunca é tocado (Req 12.8).
# ---------------------------------------------------------------------------------------------

_JORNADA = {"origem": "qr", "modelo_id": "tres-passione"}


@pytest.fixture(scope="module")
def modulo_dev():
    spec = importlib.util.spec_from_file_location("dev_local_persistencia", _CAMINHO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)  # também deixa `scripts/` no sys.path
    return modulo


@pytest.fixture(scope="module")
def estado(modulo_dev):
    return importlib.import_module("estado_demo")


@pytest.fixture(autouse=True)
def _sem_senha_no_ambiente(monkeypatch):
    monkeypatch.delenv("CS_SENHA_INICIAL", raising=False)


@contextmanager
def _subir(modulo, dir_dados, *argv, monkeypatch):
    """Sobe `main()` de verdade (porta livre) numa thread e para o servidor ao sair."""
    servidores = []
    pronto = threading.Event()

    class ServidorDeTeste(ThreadingHTTPServer):
        def __init__(self, endereco, handler):
            super().__init__(endereco, handler)
            servidores.append(self)

        def serve_forever(self, *args, **kwargs):
            pronto.set()
            super().serve_forever(*args, **kwargs)

    monkeypatch.setattr(modulo, "ThreadingHTTPServer", ServidorDeTeste)
    resultado = {}

    def rodar():
        resultado["codigo"] = modulo.main(["--porta", "0", *argv], dir_dados=dir_dados)

    thread = threading.Thread(target=rodar, daemon=True)
    thread.start()
    while not pronto.wait(0.05):
        assert thread.is_alive(), f"main() terminou antes de subir: {resultado}"
    servidor = servidores[0]
    try:
        yield f"http://127.0.0.1:{servidor.server_address[1]}"
    finally:
        servidor.shutdown()
        thread.join(10)
        servidor.server_close()
    assert resultado.get("codigo") == 0


@contextmanager
def _servidor_manual(modulo, persistencia, *, com_demo=False):
    """Monta app + Handler com a `persistencia` dada (permite injetar falhas e observar)."""
    app = modulo.criar_app({}, modo="local")
    modulo.iniciar_estado(
        app, modulo.SENHA_PADRAO, persistencia, resetar=False, com_demo=com_demo
    )
    handler = modulo.construir_handler(
        app, modulo.criar_roteador(), inseguro_local=True, persistencia=persistencia
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}", app
    finally:
        httpd.shutdown()
        httpd.server_close()


def _snapshot(dir_dados):
    return json.loads((dir_dados / "estado.json").read_text(encoding="utf-8"))["estado"]


def _numeros(dir_dados):
    return sorted(c["numero"] for c in _snapshot(dir_dados)["chamados"])


def _login(base, usuario, senha):
    return _chamar(base, "POST", "/api/cs/login", {"usuario": usuario, "senha": senha})


def _cookie(cabecalhos):
    return cabecalhos["Set-Cookie"].split(";")[0]


# ---- Handler: gravação antes da resposta (Req 1.1, 1.2) -------------------------------------


def test_post_grava_o_snapshot_antes_de_responder(modulo_dev, estado, tmp_path):
    dir_dados = tmp_path / "dados"

    class PersistenciaLenta(estado.Persistencia):
        fim = None

        def gravar(self, repos):
            time.sleep(0.3)  # uma resposta enviada antes da gravação chegaria antes do fim
            resultado = super().gravar(repos)
            self.fim = time.monotonic()
            return resultado

    persistencia = PersistenciaLenta(dir_dados)
    with _servidor_manual(modulo_dev, persistencia) as (base, _app):
        persistencia.fim = None
        status, _, corpo = _chamar(base, "POST", "/api/pub/jornadas", _JORNADA)
        chegada = time.monotonic()
        assert status == 201
        assert persistencia.fim is not None and persistencia.fim <= chegada
        ids = [j["jornada_id"] for j in _snapshot(dir_dados)["jornadas"]]
        assert corpo["jornada_id"] in ids
        assert not (dir_dados / "estado.json.tmp").exists()


def test_get_e_head_nao_alteram_bytes_nem_mtime(modulo_dev, tmp_path, monkeypatch):
    dir_dados = tmp_path / "dados"
    arquivo = dir_dados / "estado.json"
    with _subir(modulo_dev, dir_dados, monkeypatch=monkeypatch) as base:
        _, _, criada = _chamar(base, "POST", "/api/pub/jornadas", _JORNADA)
        antes = (arquivo.read_bytes(), arquivo.stat().st_mtime_ns)
        time.sleep(0.05)  # se alguém regravasse, o mtime mudaria
        jid = criada["jornada_id"]
        status_get, _, _ = _chamar(base, "GET", f"/api/pub/jornadas/{jid}")
        assert status_get == 200
        _chamar(base, "GET", "/api/pub/modelos/tres-passione")
        _chamar(base, "HEAD", f"/api/pub/jornadas/{jid}")
        _chamar(base, "HEAD", "/api/pub/modelos/tres-passione")
        depois = (arquivo.read_bytes(), arquivo.stat().st_mtime_ns)
    assert depois == antes
    assert not (dir_dados / "estado.json.tmp").exists()


# ---- Inicialização: primeira subida, --sem-demo, segunda subida (Req 2.2 a 2.5) --------------


def test_primeira_subida_cria_3_chamados_de_exemplo_e_o_snapshot_inicial(
    modulo_dev, tmp_path, monkeypatch
):
    dir_dados = tmp_path / "dados"  # nem existe ainda: a subida cria (com os pais)
    dir_dados = dir_dados / "aninhado"
    with _subir(modulo_dev, dir_dados, monkeypatch=monkeypatch) as base:
        # o snapshot inicial já existe antes de qualquer requisição
        inicial = _snapshot(dir_dados)
        assert len(inicial["chamados"]) == 3
        assert sorted(c["jornada_id"] for c in inicial["chamados"]) == [
            "01JDEMO0000000000000000P1",
            "01JDEMO0000000000000000P2",
            "01JDEMO0000000000000000P3",
        ]
        assert len(inicial["jornadas"]) == 3
        # os 3 aparecem na fila do Painel_CS
        _, cab, _ = _login(base, "atendente", modulo_dev.SENHA_PADRAO)
        status, _, fila = _chamar(base, "GET", "/api/cs/fila", cabecalhos={"Cookie": _cookie(cab)})
        assert status == 200
        assert len(fila["itens"]) == 3
    # Diretorio_Dados_Demo só tem o Snapshot (Req 5.3)
    assert sorted(p.name for p in dir_dados.iterdir()) == ["estado.json"]


def test_catalogo_nao_vai_para_o_snapshot(modulo_dev, tmp_path, monkeypatch):
    dir_dados = tmp_path / "dados"
    with _subir(modulo_dev, dir_dados, monkeypatch=monkeypatch) as base:
        status, _, corpo = _chamar(base, "GET", "/api/pub/modelos/tres-passione")
        assert status == 200 and len(corpo["problemas"]) == 13
    texto = (dir_dados / "estado.json").read_text(encoding="utf-8")
    assert "tres-circo" not in json.loads(texto)["estado"].get("catalogo", {})
    assert '"catalogo"' not in texto


def test_sem_demo_sobe_sem_chamados_de_exemplo(modulo_dev, tmp_path, monkeypatch):
    dir_dados = tmp_path / "dados"
    with _subir(modulo_dev, dir_dados, "--sem-demo", monkeypatch=monkeypatch):
        inicial = _snapshot(dir_dados)  # o snapshot inicial existe mesmo sem exemplos
        assert inicial["chamados"] == []
        assert inicial["jornadas"] == []


def test_segunda_subida_nao_recria_os_exemplos(modulo_dev, tmp_path, monkeypatch):
    dir_dados = tmp_path / "dados"
    with _subir(modulo_dev, dir_dados, monkeypatch=monkeypatch):
        primeiros = _numeros(dir_dados)
    bytes_antes = (dir_dados / "estado.json").read_bytes()
    assert len(primeiros) == 3

    with _subir(modulo_dev, dir_dados, monkeypatch=monkeypatch) as base:
        assert _numeros(dir_dados) == primeiros  # mesmos números, nada a mais
        _, cab, _ = _login(base, "gestor", modulo_dev.SENHA_PADRAO)
        status, _, fila = _chamar(base, "GET", "/api/cs/fila", cabecalhos={"Cookie": _cookie(cab)})
        assert status == 200
        assert sorted(i["numero"] for i in fila["itens"]) == primeiros
    # sem --resetar o Snapshot existente não é apagado nem reescrito (Req 3.5)
    assert (dir_dados / "estado.json").read_bytes() == bytes_antes


def test_segunda_subida_com_sem_demo_mantem_os_exemplos_gravados(
    modulo_dev, tmp_path, monkeypatch
):
    dir_dados = tmp_path / "dados"
    with _subir(modulo_dev, dir_dados, monkeypatch=monkeypatch):
        primeiros = _numeros(dir_dados)
    with _subir(modulo_dev, dir_dados, "--sem-demo", monkeypatch=monkeypatch):
        assert _numeros(dir_dados) == primeiros


def test_segunda_subida_recarrega_o_que_foi_criado_depois(modulo_dev, tmp_path, monkeypatch):
    dir_dados = tmp_path / "dados"
    with _subir(modulo_dev, dir_dados, monkeypatch=monkeypatch) as base:
        _, _, criada = _chamar(base, "POST", "/api/pub/jornadas", _JORNADA)
    with _subir(modulo_dev, dir_dados, monkeypatch=monkeypatch) as base:
        status, _, corpo = _chamar(base, "GET", f"/api/pub/jornadas/{criada['jornada_id']}")
        assert status == 200
        assert corpo["jornada"]["modelo_id"] == "tres-passione"


# ---- --resetar (Req 3.1 a 3.4) ---------------------------------------------------------------


def test_resetar_apaga_o_estado_e_recria_os_exemplos(modulo_dev, tmp_path, monkeypatch):
    dir_dados = tmp_path / "dados"
    with _subir(modulo_dev, dir_dados, monkeypatch=monkeypatch) as base:
        _chamar(base, "POST", "/api/pub/jornadas", _JORNADA)
        antigos = _numeros(dir_dados)
        assert len(_snapshot(dir_dados)["jornadas"]) == 4
    (dir_dados / "estado.json.tmp").write_text("sobra de uma gravação interrompida")

    with _subir(modulo_dev, dir_dados, "--resetar", monkeypatch=monkeypatch):
        novos = _numeros(dir_dados)
        assert len(novos) == 3
        assert set(novos).isdisjoint(antigos)  # exemplos recriados (números novos)
        assert len(_snapshot(dir_dados)["jornadas"]) == 3  # a Jornada extra se foi
    assert not (dir_dados / "estado.json.tmp").exists()
    assert sorted(p.name for p in dir_dados.iterdir()) == ["estado.json"]


def test_resetar_com_sem_demo_recomeca_sem_exemplos(modulo_dev, tmp_path, monkeypatch):
    dir_dados = tmp_path / "dados"
    with _subir(modulo_dev, dir_dados, monkeypatch=monkeypatch):
        assert len(_numeros(dir_dados)) == 3
    with _subir(modulo_dev, dir_dados, "--resetar", "--sem-demo", monkeypatch=monkeypatch):
        inicial = _snapshot(dir_dados)
        assert inicial["chamados"] == []
        assert inicial["jornadas"] == []


def test_resetar_sem_snapshot_conclui_sem_erro(modulo_dev, tmp_path, monkeypatch):
    dir_dados = tmp_path / "dados"
    assert not dir_dados.exists()
    with _subir(modulo_dev, dir_dados, "--resetar", monkeypatch=monkeypatch):
        assert len(_numeros(dir_dados)) == 3  # mesma coisa que a primeira subida


# ---- Snapshot inválido (Req 2.6, 2.7) --------------------------------------------------------


@pytest.mark.parametrize(
    "conteudo",
    [
        "{isto nao e json",
        "",
        json.dumps({"versao": 999, "estado": {}}),
        json.dumps({"versao": 1, "estado": {"chamados": [{"campo_desconhecido": 1}]}}),
        json.dumps([1, 2, 3]),
    ],
    ids=["json_malformado", "vazio", "versao_diferente", "estrutura_desconhecida", "nao_objeto"],
)
def test_snapshot_invalido_devolve_2_e_nao_altera_o_arquivo(
    modulo_dev, tmp_path, monkeypatch, capsys, conteudo
):
    class NaoDeveSubir:
        def __init__(self, *args, **kwargs):
            raise AssertionError("o servidor não pode subir com snapshot inválido")

    monkeypatch.setattr(modulo_dev, "ThreadingHTTPServer", NaoDeveSubir)
    dir_dados = tmp_path / "dados"
    dir_dados.mkdir()
    arquivo = dir_dados / "estado.json"
    arquivo.write_text(conteudo, encoding="utf-8")
    antes = (arquivo.read_bytes(), arquivo.stat().st_mtime_ns)

    codigo = modulo_dev.main(["--porta", "0"], dir_dados=dir_dados)

    assert codigo == 2
    erro = capsys.readouterr().err
    assert str(arquivo) in erro
    assert "--resetar" in erro
    assert (arquivo.read_bytes(), arquivo.stat().st_mtime_ns) == antes
    assert sorted(p.name for p in dir_dados.iterdir()) == ["estado.json"]


def test_snapshot_com_bytes_invalidos_devolve_2(modulo_dev, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(modulo_dev, "ThreadingHTTPServer", None)
    arquivo = tmp_path / "estado.json"
    arquivo.write_bytes(b"\xff\xfe\x00 nao e utf-8")
    assert modulo_dev.main(["--porta", "0"], dir_dados=tmp_path) == 2
    assert arquivo.read_bytes() == b"\xff\xfe\x00 nao e utf-8"
    assert "--resetar" in capsys.readouterr().err


# ---- Falha de gravação (Req 1.5) -------------------------------------------------------------


def test_falha_ao_gravar_ainda_responde_com_o_status_calculado(modulo_dev, estado, tmp_path):
    bloqueio = tmp_path / "bloqueado"
    bloqueio.write_text("sou um arquivo, nao um diretorio")  # mkdir do snapshot vai falhar
    logs: list[str] = []
    persistencia = estado.Persistencia(bloqueio, log=logs.append)
    with _servidor_manual(modulo_dev, persistencia) as (base, _app):
        status, _, criada = _chamar(base, "POST", "/api/pub/jornadas", _JORNADA)
        assert status == 201  # o resultado calculado, apesar da falha ao gravar
        assert any("ERRO ao gravar o estado" in linha for linha in logs)
        # o servidor segue atendendo e o estado em memória está correto
        status, _, corpo = _chamar(base, "GET", f"/api/pub/jornadas/{criada['jornada_id']}")
        assert status == 200
        status, _, _ = _chamar(base, "POST", "/api/pub/jornadas", _JORNADA)
        assert status == 201
    assert bloqueio.read_text() == "sou um arquivo, nao um diretorio"


def test_falha_no_os_replace_responde_e_preserva_o_snapshot_anterior(
    modulo_dev, estado, tmp_path, monkeypatch
):
    dir_dados = tmp_path / "dados"
    logs: list[str] = []
    persistencia = estado.Persistencia(dir_dados, log=logs.append)
    with _servidor_manual(modulo_dev, persistencia, com_demo=True) as (base, _app):
        anterior = (dir_dados / "estado.json").read_bytes()
        original = os.replace

        def replace_com_falha(origem, destino, *args, **kwargs):
            if Path(destino) == dir_dados / "estado.json":
                raise OSError("disco cheio (injetado)")
            return original(origem, destino, *args, **kwargs)

        monkeypatch.setattr(os, "replace", replace_com_falha)
        status, _, _ = _chamar(base, "POST", "/api/pub/jornadas", _JORNADA)
        monkeypatch.setattr(os, "replace", original)
        assert status == 201
    assert (dir_dados / "estado.json").read_bytes() == anterior
    assert not (dir_dados / "estado.json.tmp").exists()
    assert any("disco cheio" in linha for linha in logs)


# ---- Login depois de reiniciar (Req 5.2, 5.5, 5.6) -------------------------------------------


def test_login_apos_reiniciar_sessoes_nao_persistem_e_nova_senha_vale(
    modulo_dev, tmp_path, monkeypatch
):
    dir_dados = tmp_path / "dados"
    monkeypatch.setenv("CS_SENHA_INICIAL", "senha-antiga-123")
    with _subir(modulo_dev, dir_dados, monkeypatch=monkeypatch) as base:
        status, cab, _ = _login(base, "atendente", "senha-antiga-123")
        assert status == 200
        cookie_antigo = _cookie(cab)
        status, _, _ = _chamar(base, "GET", "/api/cs/sessao", cabecalhos={"Cookie": cookie_antigo})
        assert status == 200

    monkeypatch.setenv("CS_SENHA_INICIAL", "senha-nova-456")
    with _subir(modulo_dev, dir_dados, monkeypatch=monkeypatch) as base:
        # a sessão antiga não sobrevive ao reinício
        status, _, _ = _chamar(base, "GET", "/api/cs/sessao", cabecalhos={"Cookie": cookie_antigo})
        assert status == 401
        # a senha antiga deixou de valer; a nova entra
        status, _, _ = _login(base, "atendente", "senha-antiga-123")
        assert status == 401
        # perfis preservados
        for usuario in ("atendente", "gestor"):
            status, cab, corpo = _login(base, usuario, "senha-nova-456")
            assert status == 200
            assert corpo["perfil"] == usuario
            status, _, sessao = _chamar(
                base, "GET", "/api/cs/sessao", cabecalhos={"Cookie": _cookie(cab)}
            )
            assert status == 200
            assert sessao["perfil"] == usuario
    # a senha e os hashes nunca vão para o arquivo (Req 5.4)
    texto = (dir_dados / "estado.json").read_text(encoding="utf-8")
    assert "senha-antiga-123" not in texto and "senha-nova-456" not in texto
    assert "hash_senha" not in texto


# ---- Estresse: várias requisições POST concorrentes (Req 1.6) ----------------------------------


def test_estresse_com_8_threads_deixa_snapshot_valido_e_igual_a_memoria(
    modulo_dev, estado, tmp_path
):
    dir_dados = tmp_path / "dados"
    persistencia = estado.Persistencia(dir_dados)
    por_thread = 6

    with _servidor_manual(modulo_dev, persistencia, com_demo=True) as (base, app):

        def trabalhar(_):
            resultados = []
            for _i in range(por_thread):
                status, _, corpo = _chamar(base, "POST", "/api/pub/jornadas", _JORNADA)
                resultados.append((status, corpo["jornada_id"]))
            return resultados

        with ThreadPoolExecutor(max_workers=8) as pool:
            lotes = list(pool.map(trabalhar, range(8)))

        respostas = [r for lote in lotes for r in lote]
        assert len(respostas) == 8 * por_thread
        assert all(status == 201 for status, _ in respostas)

        texto = (dir_dados / "estado.json").read_text(encoding="utf-8")
        gravado = json.loads(texto)  # JSON válido
        ids_gravados = {j["jornada_id"] for j in gravado["estado"]["jornadas"]}
        assert {jid for _, jid in respostas} <= ids_gravados
        assert len(ids_gravados) == 3 + 8 * por_thread  # 3 exemplos + as criadas
        # o último snapshot é exatamente o estado em memória
        assert texto == estado.serializar_estado(estado.capturar_estado(app.repos))
        assert not (dir_dados / "estado.json.tmp").exists()
