import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { apiCs } from "./clienteCs";
import "./fila.css";

/** Intervalo da atualização automática da fila (enquanto a página está visível). */
export const INTERVALO_FILA_MS = 10_000;

export type PrioridadeFila = "P1" | "P2" | "P3";

export interface ItemFila {
  numero: string;
  prioridade: PrioridadeFila;
  classificacao: string;
  status: string;
  responsavel: { usuario: string; nome: string } | null;
  tempo_espera_s: number;
  criado_em: string;
  alerta_p1: boolean;
  alerta_p1_visto: boolean;
  resposta_nao_lida: boolean;
  resumo: string;
}

interface RespostaFila {
  itens: ItemFila[];
}

const ROTULO_PRIORIDADE: Record<PrioridadeFila, string> = {
  P1: "P1 · Urgente",
  P2: "P2 · Alta",
  P3: "P3 · Normal",
};

/** "45 s", "5 min", "2 h 05 min". */
export function formatarEspera(segundos: number): string {
  const s = Math.max(0, Math.floor(segundos));
  if (s < 60) return `${s} s`;
  const min = Math.floor(s / 60);
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  return `${h} h ${String(min % 60).padStart(2, "0")} min`;
}

function rotuloStatus(status: string): string {
  const texto = status.replace(/_/g, " ");
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

type Estado =
  | { fase: "carregando" }
  | { fase: "erro" }
  | { fase: "pronto"; itens: ItemFila[]; falhaAtualizacao: boolean };

export function Component() {
  const [estado, setEstado] = useState<Estado>({ fase: "carregando" });
  const montado = useRef(true);

  const carregar = useCallback(async () => {
    try {
      const dados = await apiCs.get<RespostaFila>("/fila");
      if (!montado.current) return;
      setEstado({ fase: "pronto", itens: dados.itens ?? [], falhaAtualizacao: false });
    } catch {
      if (!montado.current) return;
      // Mantém os últimos dados em falhas de atualização; só mostra erro cheio sem dados.
      setEstado((atual) =>
        atual.fase === "pronto" ? { ...atual, falhaAtualizacao: true } : { fase: "erro" },
      );
    }
  }, []);

  const tentarDeNovo = useCallback(() => {
    setEstado({ fase: "carregando" });
    void carregar();
  }, [carregar]);

  useEffect(() => {
    montado.current = true;
    void carregar();

    let temporizador: ReturnType<typeof setInterval> | undefined;
    const iniciar = () => {
      if (temporizador === undefined) temporizador = setInterval(() => void carregar(), INTERVALO_FILA_MS);
    };
    const parar = () => {
      if (temporizador !== undefined) clearInterval(temporizador);
      temporizador = undefined;
    };
    const aoMudarVisibilidade = () => {
      if (document.visibilityState === "hidden") {
        parar();
      } else {
        void carregar();
        iniciar();
      }
    };

    if (document.visibilityState !== "hidden") iniciar();
    document.addEventListener("visibilitychange", aoMudarVisibilidade);
    return () => {
      montado.current = false;
      parar();
      document.removeEventListener("visibilitychange", aoMudarVisibilidade);
    };
  }, [carregar]);

  return (
    <section aria-labelledby="titulo-fila">
      <h1 id="titulo-fila">Fila de chamados</h1>
      {estado.fase === "carregando" && <p role="status">Carregando a fila…</p>}
      {estado.fase === "erro" && (
        <div role="alert" className="fila__erro">
          <p>Não foi possível carregar a fila de chamados.</p>
          <button type="button" onClick={tentarDeNovo}>
            Tentar de novo
          </button>
        </div>
      )}
      {estado.fase === "pronto" && <ConteudoFila itens={estado.itens} falha={estado.falhaAtualizacao} />}
    </section>
  );
}

function ConteudoFila({ itens, falha }: { itens: ItemFila[]; falha: boolean }) {
  const urgentes = itens.filter((i) => i.alerta_p1);
  return (
    <>
      {urgentes.length > 0 && (
        <div role="alert" className="fila__alerta-p1">
          <strong>
            {urgentes.length === 1
              ? "Atenção: 1 chamado P1 (urgente) ainda não foi aberto."
              : `Atenção: ${urgentes.length} chamados P1 (urgentes) ainda não foram abertos.`}
          </strong>{" "}
          {urgentes.map((i, idx) => (
            <span key={i.numero}>
              {idx > 0 && ", "}
              <Link to={`/cs/chamados/${encodeURIComponent(i.numero)}`}>{i.numero}</Link>
            </span>
          ))}
        </div>
      )}
      {falha && (
        <p role="status" className="fila__aviso">
          Não foi possível atualizar a fila. Mostrando os últimos dados recebidos; nova tentativa em instantes.
        </p>
      )}
      {itens.length === 0 ? (
        <p>Não há chamados na fila no momento.</p>
      ) : (
        <ul className="fila__lista" aria-label="Chamados na fila">
          {itens.map((item) => (
            <ItemDaFila key={item.numero} item={item} />
          ))}
        </ul>
      )}
    </>
  );
}

function ItemDaFila({ item }: { item: ItemFila }) {
  return (
    <li className={`fila__item fila__item--${item.prioridade.toLowerCase()}`}>
      <p className="fila__linha">
        <span className={`fila__prioridade fila__prioridade--${item.prioridade.toLowerCase()}`}>
          {ROTULO_PRIORIDADE[item.prioridade] ?? item.prioridade}
        </span>{" "}
        <Link to={`/cs/chamados/${encodeURIComponent(item.numero)}`}>{item.numero}</Link>{" "}
        <span>{item.classificacao}</span>
        {item.resposta_nao_lida && <span className="fila__nao-lida"> Resposta não lida</span>}
      </p>
      <p className="fila__resumo">{item.resumo}</p>
      <p className="fila__meta">
        <span>Status: {rotuloStatus(item.status)}</span>
        {" · "}
        <span>Espera: {formatarEspera(item.tempo_espera_s)}</span>
        {" · "}
        <span>Responsável: {item.responsavel ? item.responsavel.nome : "Sem responsável"}</span>
      </p>
    </li>
  );
}
