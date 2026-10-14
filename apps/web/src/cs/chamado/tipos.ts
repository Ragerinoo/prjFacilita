/** Formas da resposta de `GET /api/cs/chamados/{numero}` (services/api/routes/cs_chamados.py). */
export type Prioridade = "P1" | "P2" | "P3";
export type StatusChamado = "aberto" | "em_atendimento" | "encerrado";

export interface Responsavel {
  usuario: string;
  nome: string;
}

export interface ItemJaTentado {
  passo: string;
  camada: string;
  resultado: string;
}

export interface PacoteRepasse {
  modelo: string;
  numero_serie: string | null;
  origem: string;
  categoria: string;
  resumo: string;
  ja_tentado: ItemJaTentado[];
  classificacao: string;
  prioridade: Prioridade;
  canal_recomendado: string;
  sentimento: string;
  proxima_acao: string;
}

export interface AnexoChamado {
  indice: number;
  mime: string;
  bytes: number;
}

export interface MensagemChamado {
  ts_ulid: string;
  autor: "atendente" | "consumidor";
  texto: string;
  em: string | null;
  lida: boolean;
}

export interface EventoHistorico {
  evento_id: string;
  tipo: string;
  em: string | null;
  dados: unknown;
}

export interface CardChamado {
  numero: string;
  jornada_id: string;
  status: StatusChamado;
  prioridade: Prioridade;
  classificacao: string;
  canal: string;
  criado_em: string | null;
  responsavel: Responsavel | null;
  alerta_p1_visto: boolean;
  resposta_nao_lida: boolean;
  os_status: string | null;
  agendamento: string | null;
  pacote_ia_status: string;
  decisao_criterio: 1 | 2 | 3;
  pacote: PacoteRepasse;
  anexos: AnexoChamado[];
  encerramento: { desfecho: string; solucao_tipo: string; solucao: string; em: string | null; por: string } | null;
  mensagens: MensagemChamado[];
  historico: EventoHistorico[];
}

export const ROTULO_STATUS: Record<StatusChamado, string> = {
  aberto: "Aberto",
  em_atendimento: "Em atendimento",
  encerrado: "Encerrado",
};

export const ROTULO_PRIORIDADE: Record<Prioridade, string> = {
  P1: "P1 (urgente)",
  P2: "P2 (importante)",
  P3: "P3 (normal)",
};

export function formatarData(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" });
}
