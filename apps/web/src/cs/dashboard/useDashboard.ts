import { useCallback, useEffect, useRef, useState } from "react";
import { apiCs } from "../clienteCs";
import { lerRespostaDashboard, type RespostaDashboard } from "./tipos";

/**
 * Intervalo da atualização automática do Dashboard (enquanto a página está visível).
 * Igual a `INTERVALO_FILA_MS` de `FilaCs.tsx`; não é importado de lá para não arrastar a
 * tela da Fila para o chunk do Dashboard. Um teste confere a igualdade.
 */
export const INTERVALO_DASHBOARD_MS = 10_000;

export type EstadoDashboard =
  | { fase: "carregando" }
  | { fase: "erro" }
  | { fase: "pronto"; dados: RespostaDashboard; falhaAtualizacao: boolean };

export interface RetornoDashboard {
  estado: EstadoDashboard;
  /** Repete a solicitação mostrando o carregamento; substitui qualquer pedido em andamento. */
  tentarDeNovo(): void;
}

/**
 * Carrega `GET /api/cs/dashboard` e o atualiza a cada `INTERVALO_DASHBOARD_MS`.
 *
 * - A atualização automática nunca passa por `carregando` (sem piscar).
 * - Há no máximo um pedido em voo: o tick espera; "Tentar de novo" substitui.
 * - Falha depois de sucesso mantém os dados e liga `falhaAtualizacao`.
 * - Página oculta pausa o intervalo; ao voltar, carrega na hora e reinicia.
 * - Ao desmontar: `clearInterval`, remove o ouvinte e aborta o pedido em voo.
 */
export function useDashboard(): RetornoDashboard {
  const [estado, setEstado] = useState<EstadoDashboard>({ fase: "carregando" });
  const emVoo = useRef<AbortController | null>(null);

  const carregar = useCallback(async (substituir: boolean) => {
    if (emVoo.current !== null && !substituir) return;
    emVoo.current?.abort();
    const controle = new AbortController();
    emVoo.current = controle;
    try {
      const corpo = await apiCs.get<unknown>("/dashboard", { sinal: controle.signal });
      const dados = lerRespostaDashboard(corpo);
      if (controle.signal.aborted) return;
      if (dados === null) throw new Error("formato inesperado");
      setEstado({ fase: "pronto", dados, falhaAtualizacao: false });
    } catch {
      if (controle.signal.aborted) return;
      // Mantém os últimos dados em falhas de atualização; só mostra erro cheio sem dados.
      setEstado((atual) => (atual.fase === "pronto" ? { ...atual, falhaAtualizacao: true } : { fase: "erro" }));
    } finally {
      if (emVoo.current === controle) emVoo.current = null;
    }
  }, []);

  const tentarDeNovo = useCallback(() => {
    setEstado({ fase: "carregando" });
    void carregar(true);
  }, [carregar]);

  useEffect(() => {
    void carregar(false);

    let temporizador: ReturnType<typeof setInterval> | undefined;
    const iniciar = () => {
      if (temporizador === undefined) {
        temporizador = setInterval(() => void carregar(false), INTERVALO_DASHBOARD_MS);
      }
    };
    const parar = () => {
      if (temporizador !== undefined) clearInterval(temporizador);
      temporizador = undefined;
    };
    const aoMudarVisibilidade = () => {
      if (document.visibilityState === "hidden") {
        parar();
      } else {
        void carregar(false);
        iniciar();
      }
    };

    if (document.visibilityState !== "hidden") iniciar();
    document.addEventListener("visibilitychange", aoMudarVisibilidade);
    return () => {
      parar();
      document.removeEventListener("visibilitychange", aoMudarVisibilidade);
      // Zera a referência para que uma remontagem (StrictMode) não espere um pedido já cancelado.
      const pendente = emVoo.current;
      emVoo.current = null;
      pendente?.abort();
    };
  }, [carregar]);

  return { estado, tentarDeNovo };
}
