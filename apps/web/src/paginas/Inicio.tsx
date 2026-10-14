import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { carregarCatalogo, selecionarModeloPorBusca, type ModeloCatalogo } from "../api/catalogo";
import { buscarModelos, LIMITE_BUSCA } from "../busca/filtro";
import "./Inicio.css";

export const MENSAGEM_SEM_RESULTADO = "Não encontramos esse nome. Escolha sua máquina pela foto.";
export const MENSAGEM_CATALOGO_INDISPONIVEL =
  "A lista de máquinas está indisponível no momento. Tente novamente.";
export const MENSAGEM_FALHA_SELECAO = "Não foi possível abrir essa máquina agora. Tente novamente.";

type Resultado =
  | { tentativa: number; modelos: ModeloCatalogo[]; falhou: false }
  | { tentativa: number; falhou: true };

/** Foto do modelo; se não carregar, mostra uma imagem substituta (Req 2.6). */
function FotoModelo({ foto }: { foto?: string }) {
  const [falhou, setFalhou] = useState(false);
  if (!foto || falhou) {
    return (
      <span className="modelo__foto modelo__foto--substituta" aria-hidden="true" data-testid="foto-substituta">
        <svg viewBox="0 0 48 48" width="48" height="48" focusable="false">
          <path
            d="M10 14h24v14a8 8 0 0 1-8 8h-8a8 8 0 0 1-8-8zM34 18h3a4 4 0 0 1 0 8h-3M16 8v3M22 8v3M28 8v3"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
    );
  }
  return <img className="modelo__foto" src={foto} alt="" loading="lazy" onError={() => setFalhou(true)} />;
}

export function Component() {
  const navegar = useNavigate();
  const local = useLocation();
  // Mensagem opcional enviada pela Pagina_Maquina (QR não reconhecido ou ilegível).
  const avisoDeOrigem = (local.state as { mensagem?: unknown } | null)?.mensagem;

  const [tentativa, setTentativa] = useState(0);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [texto, setTexto] = useState("");
  const [abrindo, setAbrindo] = useState<string | null>(null);
  const [falhaSelecao, setFalhaSelecao] = useState(false);

  useEffect(() => {
    const controle = new AbortController();
    carregarCatalogo(undefined, controle.signal).then(
      (modelos) => {
        if (!controle.signal.aborted) setResultado({ tentativa, modelos, falhou: false });
      },
      () => {
        if (!controle.signal.aborted) setResultado({ tentativa, falhou: true });
      },
    );
    return () => controle.abort();
  }, [tentativa]);

  const carregando = resultado === null || resultado.tentativa !== tentativa;
  const indisponivel = !carregando && resultado.falhou;
  const catalogo = useMemo(
    () => (resultado && !resultado.falhou ? resultado.modelos : []),
    [resultado],
  );
  const { modelos, semResultado } = useMemo(() => buscarModelos(catalogo, texto), [catalogo, texto]);

  function tentarNovamente() {
    setResultado(null);
    setTentativa((n) => n + 1);
  }

  async function selecionar(modelo: ModeloCatalogo) {
    if (abrindo) return;
    setAbrindo(modelo.modelo_id);
    setFalhaSelecao(false);
    try {
      await selecionarModeloPorBusca(modelo.modelo_id);
      await navegar(`/m/${encodeURIComponent(modelo.modelo_id)}`);
    } catch {
      setFalhaSelecao(true);
    } finally {
      setAbrindo(null);
    }
  }

  return (
    <section className="inicio">
      <h1>Escolha a sua máquina</h1>
      <p>Digite o nome da máquina ou escolha pela foto para ver como resolver o seu problema.</p>

      {typeof avisoDeOrigem === "string" && avisoDeOrigem ? (
        <p role="status" className="inicio__aviso">
          {avisoDeOrigem}
        </p>
      ) : null}

      <div className="inicio__busca">
        <label htmlFor="busca-modelo">Nome da máquina</label>
        <input
          id="busca-modelo"
          type="text"
          inputMode="search"
          autoComplete="off"
          maxLength={LIMITE_BUSCA}
          value={texto}
          disabled={carregando || indisponivel}
          onChange={(e) => setTexto(e.target.value)}
        />
      </div>

      {carregando ? (
        <p role="status" className="carregando">
          Carregando as máquinas…
        </p>
      ) : null}

      {indisponivel ? (
        <div role="alert" className="inicio__indisponivel">
          <p>{MENSAGEM_CATALOGO_INDISPONIVEL}</p>
          <button type="button" className="botao" onClick={tentarNovamente}>
            Tentar novamente
          </button>
        </div>
      ) : null}

      {semResultado ? (
        <p role="status" className="inicio__sem-resultado">
          {MENSAGEM_SEM_RESULTADO}
        </p>
      ) : null}

      {falhaSelecao ? (
        <p role="alert" className="inicio__aviso">
          {MENSAGEM_FALHA_SELECAO}
        </p>
      ) : null}

      {!carregando && !indisponivel ? (
        <ul className="modelos" aria-label="Máquinas">
          {modelos.map((modelo) => (
            <li key={modelo.modelo_id}>
              <button
                type="button"
                className="modelo"
                aria-busy={abrindo === modelo.modelo_id}
                disabled={abrindo !== null}
                onClick={() => void selecionar(modelo)}
              >
                <FotoModelo foto={modelo.foto_url} />
                <span className="modelo__nome">{modelo.nome}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
