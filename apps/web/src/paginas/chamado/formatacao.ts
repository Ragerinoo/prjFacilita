/** Datas do acompanhamento: sempre em pt-BR e no fuso de Brasília (Req 12.8, 15.4, 15.6). */
export const FUSO_BRASILIA = "America/Sao_Paulo";

const curto = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: FUSO_BRASILIA });
const longo = new Intl.DateTimeFormat("pt-BR", { dateStyle: "full", timeStyle: "short", timeZone: FUSO_BRASILIA });

function formatar(formato: Intl.DateTimeFormat, iso: string): string {
  const instante = Date.parse(iso);
  return Number.isNaN(instante) ? iso : formato.format(instante);
}

/** Exemplo: "02/01/2025, 14:00". */
export function formatarDataHora(iso: string): string {
  return formatar(curto, iso);
}

/** Exemplo: "quinta-feira, 2 de janeiro de 2025 às 14:00". */
export function formatarDataHoraExtenso(iso: string): string {
  return formatar(longo, iso);
}
