import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import type { EstadoAbrirChamado } from "../api/abrirChamado";
import { filaEventos } from "../api/filaEventos";
import { lerJornadaId } from "../api/jornada";
import { carregarMaquina, modeloNaoReconhecido, type DadosMaquina, type ProblemaCatalogado } from "../api/maquina";
import { iniciarJornadaQr, interpretarQr } from "../api/qr";
import { IconeProblema } from "../componentes/IconeProblema";
import "./PaginaMaquina.css";

export const MENSAGEM_MODELO_NAO_RECONHECIDO =
  "Não reconhecemos o modelo desse código. Escolha a sua máquina na lista.";
export const MENSAGEM_CODIGO_ILEGIVEL = "Não foi possível ler o código. Escolha a sua máquina na lista.";
export const MENSAGEM_INDISPONIVEL = "O serviço está indisponível por um momento. Tente novamente.";
export const MENSAGEM_FALHA_SELECAO = "Não foi possível abrir essa opção agora. Tente novamente.";
export const TEXTO_OUTRO_PROBLEMA = "Meu problema não está na lista / Não sei qual é";

type Estado =
  | { tipo: "carregando" }
  | { tipo: "indisponivel" }
  | { tipo: "pronto"; dados: DadosMaquina };

/** Foto do modelo; se não carregar, some sem afetar o resto (a identificação é o nome). */
function FotoModelo({ foto }: { foto?: string }) {
  const [falhou, setFalhou] = useState(false);
  if (!foto || falhou) return null;
  return <img className="maquina__foto" src={foto} alt="" onError={() => setFalhou(true)} />;
}

interface PropsMaquina {
  modeloId: string;
  numeroSerie?: string;
  /** Abertura direta (QR escaneado ou página recarregada), em vez de navegação dentro do Portal. */
  direto: boolean;
}

function Maquina({ modeloId, numeroSerie, direto }: PropsMaquina) {
  const navegar = useNavigate();
  const [tentativa, setTentativa] = useState(0);
  const [estado, setEstado] = useState<Estado>({ tipo: "carregando" });
  const [abrindo, setAbrindo] = useState(false);
  const [falhaSelecao, setFalhaSelecao] = useState(false);
  const jornada = useRef<Promise<string> | null>(null);

  /**
   * Garante a Jornada desta página. Num acesso direto (QR), cria uma com origem
   * "qr"; ao voltar de outra tela do Portal, reaproveita a que já existe.
   * Se a criação falhar, a próxima chamada tenta de novo.
   */
  const garantirJornada = useCallback((): Promise<string> => {
    if (!jornada.current) {
      const existente = lerJornadaId();
      const promessa =
        !direto && existente
          ? Promise.resolve(existente)
          : iniciarJornadaQr({ modeloId, numeroSerie, origem: direto ? "qr" : "busca" });
      jornada.current = promessa;
      promessa.catch(() => {
        if (jornada.current === promessa) jornada.current = null;
      });
    }
    return jornada.current;
  }, [direto, modeloId, numeroSerie]);

  useEffect(() => {
    const controle = new AbortController();
    const cancelado = () => controle.signal.aborted;
    carregarMaquina(modeloId, undefined, controle.signal).then(
      (dados) => {
        if (cancelado()) return;
        setEstado({ tipo: "pronto", dados });
        // A Jornada só nasce depois que o modelo foi resolvido (Req 1.7) e sem
        // atrasar a exibição da página (Req 1.1 e 19.2).
        garantirJornada().catch(() => undefined);
      },
      async (erro: unknown) => {
        if (cancelado()) return;
        if (modeloNaoReconhecido(erro)) {
          // Req 1.4: Jornada "qr" sem modelo e volta para a busca com mensagem.
          await iniciarJornadaQr({ lido: modeloId, origem: "qr" }).catch(() => undefined);
          if (cancelado()) return;
          await navegar("/", { replace: true, state: { mensagem: MENSAGEM_MODELO_NAO_RECONHECIDO } });
          return;
        }
        setEstado({ tipo: "indisponivel" });
      },
    );
    return () => controle.abort();
  }, [modeloId, tentativa, garantirJornada, navegar]);

  function tentarNovamente() {
    setEstado({ tipo: "carregando" });
    setTentativa((n) => n + 1);
  }

  async function selecionar(problema: ProblemaCatalogado) {
    if (abrindo) return;
    setAbrindo(true);
    setFalhaSelecao(false);
    try {
      const jornadaId = await garantirJornada();
      // Req 3.9: o evento vai para a fila local e não bloqueia a navegação.
      filaEventos.enfileirar(`/jornadas/${encodeURIComponent(jornadaId)}/eventos`, {
        tipo: "selecionado",
        problema_id: problema.problema_id,
        ocorrido_em: new Date().toISOString(),
      });
      await navegar(`/m/${encodeURIComponent(modeloId)}/p/${encodeURIComponent(String(problema.problema_id))}`);
    } catch {
      setFalhaSelecao(true);
    } finally {
      setAbrindo(false);
    }
  }

  if (estado.tipo === "carregando") {
    return (
      <section className="maquina">
        <h1>Sua máquina</h1>
        <p role="status" className="carregando">
          Carregando…
        </p>
      </section>
    );
  }

  if (estado.tipo === "indisponivel") {
    return (
      <section className="maquina">
        <h1>Sua máquina</h1>
        <div role="alert" className="maquina__aviso">
          <p>{MENSAGEM_INDISPONIVEL}</p>
          <button type="button" className="botao" onClick={tentarNovamente}>
            Tentar novamente
          </button>
        </div>
      </section>
    );
  }

  const { modelo, problemas } = estado.dados;
  return (
    <section className="maquina">
      <header className="maquina__identificacao">
        <FotoModelo foto={modelo.foto_url} />
        <h1>{modelo.nome}</h1>
      </header>
      <h2>Qual é o problema?</h2>
      {falhaSelecao ? (
        <p role="alert" className="maquina__aviso">
          {MENSAGEM_FALHA_SELECAO}
        </p>
      ) : null}
      <ol className="problemas" aria-label="Problemas">
        {problemas.map((problema) => (
          <li key={problema.problema_id}>
            <button
              type="button"
              className="problema"
              aria-busy={abrindo}
              onClick={() => void selecionar(problema)}
            >
              <IconeProblema nome={problema.icone} alt={problema.icone_alt} />
              <span className="problema__titulo">{problema.titulo}</span>
            </button>
          </li>
        ))}
      </ol>
      <button
        type="button"
        className="botao botao--secundario maquina__outro"
        onClick={() => {
          const estado: EstadoAbrirChamado = { categoria: "outro", contexto: `Problema não listado - modelo ${modelo.nome} (${modeloId})` };
          void navegar("/abrir-chamado", { state: estado });
        }}
      >
        {TEXTO_OUTRO_PROBLEMA}
      </button>
    </section>
  );
}

/**
 * Rota `/m/:modeloId?s=` (Req 1). Abre direto na Pagina_Maquina, sem tela
 * intermediária. Código ilegível volta para a busca com mensagem (Req 1.6).
 */
export function Component() {
  const { modeloId } = useParams();
  const [consulta] = useSearchParams();
  const local = useLocation();
  const qr = interpretarQr(modeloId, consulta);
  if (!qr.legivel) {
    return <Navigate to="/" replace state={{ mensagem: MENSAGEM_CODIGO_ILEGIVEL }} />;
  }
  return (
    <Maquina
      key={`${qr.modeloId}|${qr.numeroSerie ?? ""}`}
      modeloId={qr.modeloId}
      numeroSerie={qr.numeroSerie}
      // Navegação dentro do Portal gera uma chave de localização própria; o
      // primeiro carregamento da página (QR ou recarga) usa "default".
      direto={local.key === "default"}
    />
  );
}
