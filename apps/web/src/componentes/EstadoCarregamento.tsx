import { useEffect, useState, type ReactNode } from "react";
import { ErroCarregamento } from "./ErroCarregamento";

export const LIMITE_CARREGAMENTO_MS = 10_000;

interface Props {
  carregando: boolean;
  falhou?: boolean;
  limiteMs?: number;
  aoTentarNovamente?: () => void;
  children: ReactNode;
}

/**
 * Envolve o conteúdo principal de uma página. Se o carregamento falhar, ou se o
 * conteúdo não aparecer em 10 s, mostra a tela de erro com "Tentar novamente"
 * (Req 19.9).
 */
export function EstadoCarregamento({
  carregando,
  falhou = false,
  limiteMs = LIMITE_CARREGAMENTO_MS,
  aoTentarNovamente,
  children,
}: Props) {
  const [estourou, setEstourou] = useState(false);

  useEffect(() => {
    if (!carregando) return;
    const temporizador = setTimeout(() => setEstourou(true), limiteMs);
    return () => clearTimeout(temporizador);
  }, [carregando, limiteMs]);

  if (falhou || (carregando && estourou)) {
    return (
      <ErroCarregamento
        aoTentarNovamente={() => {
          setEstourou(false);
          (aoTentarNovamente ?? (() => window.location.reload()))();
        }}
      />
    );
  }
  if (carregando) {
    return (
      <p role="status" className="carregando">
        Carregando…
      </p>
    );
  }
  return <>{children}</>;
}
