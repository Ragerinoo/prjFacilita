import { useSyncExternalStore } from "react";

const CONSULTA = "(prefers-reduced-motion: reduce)";

function consulta(): MediaQueryList | null {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(CONSULTA)
    : null;
}

function assinar(aviso: () => void): () => void {
  const lista = consulta();
  lista?.addEventListener("change", aviso);
  return () => lista?.removeEventListener("change", aviso);
}

/** `true` enquanto a preferência de movimento reduzido do sistema estiver ativa (Req 19.7). */
export function useMovimentoReduzido(): boolean {
  return useSyncExternalStore(
    assinar,
    () => consulta()?.matches ?? false,
    () => false,
  );
}
