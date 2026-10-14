/**
 * Regras puras da busca por modelo (Req 2.1 a 2.3, 2.5).
 * O filtro é local: roda sobre o catálogo já carregado, sem chamar a API.
 */
export const LIMITE_BUSCA = 50;
export const MINIMO_CARACTERES_BUSCA = 2;

export interface ModeloBusca {
  nome: string;
}

/** Minúsculas e sem acentos, para comparar sem diferenciar caixa nem acento. */
export function normalizarTexto(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/\p{M}+/gu, "")
    .toLowerCase();
}

/** Ordem alfabética de nome, sem diferenciar caixa nem acento (Req 2.1). */
export function ordenarPorNome<T extends ModeloBusca>(modelos: readonly T[]): T[] {
  return [...modelos].sort((a, b) =>
    a.nome.localeCompare(b.nome, "pt-BR", { sensitivity: "base", numeric: true }),
  );
}

export interface ResultadoBusca<T> {
  /** Modelos a exibir na grade. Sempre a grade completa quando nada casa. */
  modelos: T[];
  /** Verdadeiro quando o texto tem 2 ou mais caracteres e nenhum modelo casou (Req 2.5). */
  semResultado: boolean;
}

/**
 * Aplica o filtro do Req 2.2/2.3/2.5 sobre modelos já ordenados.
 * - Espaços no início e no fim não contam; menos de 2 caracteres mostra tudo.
 * - Com 2 ou mais, mantém os modelos cujo nome contém o texto.
 * - Sem nenhum resultado, devolve a grade completa e sinaliza `semResultado`.
 */
export function buscarModelos<T extends ModeloBusca>(
  modelos: readonly T[],
  texto: string,
): ResultadoBusca<T> {
  const termo = normalizarTexto(texto.trim());
  if ([...termo].length < MINIMO_CARACTERES_BUSCA) {
    return { modelos: [...modelos], semResultado: false };
  }
  const encontrados = modelos.filter((m) => normalizarTexto(m.nome).includes(termo));
  if (encontrados.length === 0) {
    return { modelos: [...modelos], semResultado: true };
  }
  return { modelos: encontrados, semResultado: false };
}
