import { createContext, useContext, useEffect, useMemo, useSyncExternalStore, type ReactNode } from "react";
import { lerJornadaId } from "../api/jornada";
import { armazemRisco, type ArmazemRisco, type EstadoRisco } from "./armazemRisco";
import { sincronizarJornada } from "./contato";

const RiscoContext = createContext<ArmazemRisco>(armazemRisco);

interface PropsProvider {
  /** Só para testes: por padrão usa o armazém ligado ao cliente HTTP. */
  armazem?: ArmazemRisco;
  children: ReactNode;
}

/**
 * Disponibiliza o estado de risco (vindo só do servidor) a todas as telas e, ao abrir
 * o Portal, renova esse estado para a Jornada em andamento.
 */
export function RiscoProvider({ armazem = armazemRisco, children }: PropsProvider) {
  useEffect(() => {
    const jornadaId = lerJornadaId();
    if (!jornadaId) return;
    const controle = new AbortController();
    void sincronizarJornada(jornadaId, armazem, undefined, controle.signal);
    return () => controle.abort();
  }, [armazem]);

  return <RiscoContext.Provider value={armazem}>{children}</RiscoContext.Provider>;
}

export interface UsoRisco extends EstadoRisco {
  armazem: ArmazemRisco;
  /** Informa uma resposta do servidor que pode conter o envelope `jornada` (ver `armazemRisco.ts`). */
  registrarRespostaServidor: (corpo: unknown) => void;
}

/**
 * Estado de risco da Jornada e função para as telas informarem respostas do servidor
 * que não passaram pelo cliente HTTP padrão. Não existe função para remover o risco.
 */
export function useRisco(): UsoRisco {
  const armazem = useContext(RiscoContext);
  const estado = useSyncExternalStore(armazem.assinar, armazem.obter, armazem.obter);
  return useMemo(
    () => ({ ...estado, armazem, registrarRespostaServidor: armazem.registrarRespostaServidor }),
    [estado, armazem],
  );
}
