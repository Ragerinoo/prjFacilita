import type { ConsultaPeriodo } from "./SeletorPeriodo";
import { SEM_DADOS } from "./tipos";

/** Máximo de dias (inclusivos) do período personalizado. */
export const MAX_DIAS_PERSONALIZADO = 90;

const MS_POR_DIA = 24 * 60 * 60 * 1000;

const FORMATO_DATA = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  timeZone: "UTC",
});

const ROTULOS_DESFECHO: Record<string, string> = {
  falso_defeito: "Falso defeito",
  defeito_real: "Defeito real",
  nao_informado: "Não informado",
};

/** `"4.2"` vira `"4,2"`; `SEM_DADOS` segue como veio. */
export function formatarDecimal(valor: string): string {
  if (valor === SEM_DADOS) return SEM_DADOS;
  return valor.replace(".", ",");
}

/** `"43.8"` vira `"43,8%"`; `SEM_DADOS` segue como veio (sem o símbolo). */
export function formatarPercentual(valor: string): string {
  if (valor === SEM_DADOS) return SEM_DADOS;
  return `${formatarDecimal(valor)}%`;
}

/** Data ISO 8601 em pt-BR (`dd/mm/aaaa`), sempre em UTC. Texto inválido volta como veio. */
export function formatarData(iso: string): string {
  const instante = new Date(iso);
  if (Number.isNaN(instante.getTime())) return iso;
  return FORMATO_DATA.format(instante);
}

/** Texto de exibição de um Desfecho; valor desconhecido segue como veio. */
export function rotuloDesfecho(desfecho: string): string {
  return ROTULOS_DESFECHO[desfecho] ?? desfecho;
}

/** Converte `AAAA-MM-DD` em milissegundos UTC; `null` se não for uma data de calendário válida. */
function paraMsUtc(data: string): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(data);
  if (m === null) return null;
  const [ano, mes, dia] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const ms = Date.UTC(ano, mes - 1, dia);
  const d = new Date(ms);
  if (d.getUTCFullYear() !== ano || d.getUTCMonth() !== mes - 1 || d.getUTCDate() !== dia) {
    return null;
  }
  return ms;
}

/**
 * Valida o intervalo do período personalizado (datas `AAAA-MM-DD`).
 * Devolve `null` quando é válido ou a mensagem que explica o motivo.
 */
export function validarIntervalo(inicio: string, fim: string): string | null {
  if (inicio === "" || fim === "") return "Informe a data inicial e a data final.";
  const msInicio = paraMsUtc(inicio);
  const msFim = paraMsUtc(fim);
  if (msInicio === null || msFim === null) return "Informe datas válidas.";
  if (msFim < msInicio) return "A data final não pode ser anterior à data inicial.";
  const dias = Math.round((msFim - msInicio) / MS_POR_DIA) + 1;
  if (dias > MAX_DIAS_PERSONALIZADO) {
    return `O período não pode passar de ${MAX_DIAS_PERSONALIZADO} dias.`;
  }
  return null;
}

/**
 * Monta a query string de `GET /insights` a partir do Período escolhido:
 * `periodo=7d` ou `periodo=personalizado&inicio=AAAA-MM-DD&fim=AAAA-MM-DD`.
 * `inicio` e `fim` só entram no personalizado.
 */
export function montarConsulta(selecao: ConsultaPeriodo): string {
  const params = new URLSearchParams({ periodo: selecao.periodo });
  if (selecao.periodo === "personalizado") {
    params.set("inicio", selecao.inicio ?? "");
    params.set("fim", selecao.fim ?? "");
  }
  return params.toString();
}
