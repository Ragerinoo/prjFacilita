/**
 * Tipos da resposta de `GET /api/cs/dashboard` (spec insights-gestor, D9) e a validação
 * mínima do corpo recebido. Só dados operacionais: nada de dados pessoais (Req 23).
 */

/** Motivos de foco, na ordem de urgência (a mesma de `servicos/dashboard.py`). */
export type MotivoDeFoco =
  | "p1_ou_risco"
  | "resposta_nao_lida"
  | "sem_responsavel"
  | "parado";

/** Perfis que abrem o Dashboard. */
export type PerfilDashboard = "gestor" | "atendente";

/** Abas do Gestor. */
export type AbaDashboard = "insights" | "chamados";

/** Um motivo conhecido ou, por tolerância a versões novas da API, qualquer texto. */
export type MotivoRecebido = MotivoDeFoco | (string & Record<never, never>);

export interface ItemEmFoco {
  numero: string;
  prioridade: string;
  status: string;
  modelo: string;
  problema: string;
  idade_min: number;
  risco: boolean;
  sem_responsavel: boolean;
  resposta_nao_lida: boolean;
  parado: boolean;
  motivos: MotivoRecebido[];
}

export interface VisaoGeralDashboard {
  abertos: number;
  em_atendimento: number;
  encerrados: number;
  p1_risco_abertos: number;
  sem_responsavel: number;
  respostas_nao_lidas: number;
}

export interface EmFocoDashboard {
  total: number;
  limite: number;
  itens: ItemEmFoco[];
}

export interface RespostaDashboard {
  modo_local: boolean;
  gerado_em: string;
  visao_geral: VisaoGeralDashboard;
  em_foco: EmFocoDashboard;
}

const CHAVES_VISAO_GERAL: readonly (keyof VisaoGeralDashboard)[] = [
  "abertos",
  "em_atendimento",
  "encerrados",
  "p1_risco_abertos",
  "sem_responsavel",
  "respostas_nao_lidas",
];

function ehObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

function ehNumero(valor: unknown): valor is number {
  return typeof valor === "number" && Number.isFinite(valor);
}

function lerItem(bruto: unknown): ItemEmFoco | null {
  if (!ehObjeto(bruto)) return null;
  const {
    numero,
    prioridade,
    status,
    modelo,
    problema,
    idade_min,
    risco,
    sem_responsavel,
    resposta_nao_lida,
    parado,
    motivos,
  } = bruto;
  if (
    typeof numero !== "string" ||
    typeof prioridade !== "string" ||
    typeof status !== "string" ||
    typeof modelo !== "string" ||
    typeof problema !== "string" ||
    !ehNumero(idade_min) ||
    typeof risco !== "boolean" ||
    typeof sem_responsavel !== "boolean" ||
    typeof resposta_nao_lida !== "boolean" ||
    typeof parado !== "boolean" ||
    !Array.isArray(motivos) ||
    !motivos.every((m) => typeof m === "string")
  ) {
    return null;
  }
  return {
    numero,
    prioridade,
    status,
    modelo,
    problema,
    idade_min,
    risco,
    sem_responsavel,
    resposta_nao_lida,
    parado,
    motivos: motivos as MotivoRecebido[],
  };
}

/**
 * Valida o mínimo do corpo (tipos dos campos que a tela usa) e devolve a resposta tipada.
 * Formato inesperado devolve `null`, que o chamador trata como erro. Campos extras são ignorados.
 */
export function lerRespostaDashboard(corpo: unknown): RespostaDashboard | null {
  if (!ehObjeto(corpo)) return null;
  const { modo_local, gerado_em, visao_geral, em_foco } = corpo;
  if (typeof modo_local !== "boolean" || typeof gerado_em !== "string") return null;
  if (!ehObjeto(visao_geral) || !ehObjeto(em_foco)) return null;

  const contagens: Partial<VisaoGeralDashboard> = {};
  for (const chave of CHAVES_VISAO_GERAL) {
    const valor = visao_geral[chave];
    if (!ehNumero(valor)) return null;
    contagens[chave] = valor;
  }

  const { total, limite, itens } = em_foco;
  if (!ehNumero(total) || !ehNumero(limite) || !Array.isArray(itens)) return null;
  const itensLidos: ItemEmFoco[] = [];
  for (const bruto of itens) {
    const item = lerItem(bruto);
    if (item === null) return null;
    itensLidos.push(item);
  }

  return {
    modo_local,
    gerado_em,
    visao_geral: contagens as VisaoGeralDashboard,
    em_foco: { total, limite, itens: itensLidos },
  };
}
