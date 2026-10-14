/**
 * Acesso seguro ao `sessionStorage`.
 *
 * Em navegação privada ou com armazenamento bloqueado, o `sessionStorage`
 * pode lançar exceções. Nesse caso usamos um mapa em memória, para o fluxo
 * do Consumidor nunca ser interrompido por causa do armazenamento.
 */
export interface ArmazenamentoChaveValor {
  getItem(chave: string): string | null;
  setItem(chave: string, valor: string): void;
  removeItem(chave: string): void;
}

export function criarArmazenamentoMemoria(): ArmazenamentoChaveValor {
  const mapa = new Map<string, string>();
  return {
    getItem: (chave) => mapa.get(chave) ?? null,
    setItem: (chave, valor) => void mapa.set(chave, valor),
    removeItem: (chave) => void mapa.delete(chave),
  };
}

export function criarArmazenamentoSessao(): ArmazenamentoChaveValor {
  const reserva = criarArmazenamentoMemoria();
  return {
    getItem(chave) {
      try {
        return window.sessionStorage.getItem(chave);
      } catch {
        return reserva.getItem(chave);
      }
    },
    setItem(chave, valor) {
      try {
        window.sessionStorage.setItem(chave, valor);
      } catch {
        reserva.setItem(chave, valor);
      }
    },
    removeItem(chave) {
      try {
        window.sessionStorage.removeItem(chave);
      } catch {
        reserva.removeItem(chave);
      }
    },
  };
}
