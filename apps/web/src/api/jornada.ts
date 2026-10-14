import { criarArmazenamentoSessao, type ArmazenamentoChaveValor } from "./armazenamento";

/**
 * `jornada_id` e rascunhos ficam no `sessionStorage`: sobrevivem a recarga da
 * página (Req 19.9), mas não vazam entre abas nem entre sessões.
 */
export const CHAVE_JORNADA_ID = "tres.jornada_id";
const PREFIXO_RASCUNHO = "tres.rascunho.";

const armazenamentoPadrao = criarArmazenamentoSessao();

export function lerJornadaId(armazenamento: ArmazenamentoChaveValor = armazenamentoPadrao): string | null {
  return armazenamento.getItem(CHAVE_JORNADA_ID);
}

export function salvarJornadaId(
  jornadaId: string,
  armazenamento: ArmazenamentoChaveValor = armazenamentoPadrao,
): void {
  armazenamento.setItem(CHAVE_JORNADA_ID, jornadaId);
}

export function limparJornadaId(armazenamento: ArmazenamentoChaveValor = armazenamentoPadrao): void {
  armazenamento.removeItem(CHAVE_JORNADA_ID);
}

/** Guarda dados já informados (texto digitado, nota etc.) para sobreviver a "tentar novamente". */
export function salvarRascunho(
  chave: string,
  valor: unknown,
  armazenamento: ArmazenamentoChaveValor = armazenamentoPadrao,
): void {
  armazenamento.setItem(PREFIXO_RASCUNHO + chave, JSON.stringify(valor));
}

export function lerRascunho<T>(
  chave: string,
  armazenamento: ArmazenamentoChaveValor = armazenamentoPadrao,
): T | null {
  const bruto = armazenamento.getItem(PREFIXO_RASCUNHO + chave);
  if (bruto === null) return null;
  try {
    return JSON.parse(bruto) as T;
  } catch {
    return null;
  }
}

export function limparRascunho(
  chave: string,
  armazenamento: ArmazenamentoChaveValor = armazenamentoPadrao,
): void {
  armazenamento.removeItem(PREFIXO_RASCUNHO + chave);
}
