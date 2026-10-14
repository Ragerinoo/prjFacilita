/**
 * Formatação do Dashboard: idade, rótulos de prioridade, status e motivo, e a escolha da aba.
 * Funções puras; prioridade e motivos sempre saem em texto, nunca só por cor (Req 24.13).
 */
import type { AbaDashboard, PerfilDashboard } from "./tipos";

const ROTULO_PRIORIDADE: Record<string, string> = {
  P1: "P1 · Urgente",
  P2: "P2 · Alta",
  P3: "P3 · Normal",
};

const ROTULO_STATUS: Record<string, string> = {
  aberto: "Aberto",
  em_atendimento: "Em atendimento",
  encerrado: "Encerrado",
};

const ROTULO_MOTIVO: Record<string, string> = {
  p1_ou_risco: "P1 ou risco",
  resposta_nao_lida: "Resposta não lida",
  sem_responsavel: "Sem responsável",
  parado: "Parado há mais de 60 min",
};

/** Valor que a API usa quando o modelo ou o problema não são conhecidos. */
const NAO_INFORMADO = "nao_informado";

/** "menos de 1 min", "5 min", "2 h 05 min". */
export function formatarIdade(minutos: number): string {
  const total = Number.isFinite(minutos) ? Math.max(0, Math.floor(minutos)) : 0;
  if (total < 1) return "menos de 1 min";
  if (total < 60) return `${total} min`;
  const horas = Math.floor(total / 60);
  return `${horas} h ${String(total % 60).padStart(2, "0")} min`;
}

/** "P1 · Urgente"; valor desconhecido aparece como veio. */
export function rotuloPrioridade(prioridade: string): string {
  return ROTULO_PRIORIDADE[prioridade] ?? prioridade;
}

/** "Em atendimento"; valor desconhecido aparece como veio. */
export function rotuloStatus(status: string): string {
  return ROTULO_STATUS[status] ?? status;
}

/** "Sem responsável"; valor desconhecido aparece como veio. */
export function rotuloMotivo(motivo: string): string {
  return ROTULO_MOTIVO[motivo] ?? motivo;
}

/** Modelo ou problema: `nao_informado` vira "Não informado"; o resto aparece como veio. */
export function rotuloInformacao(valor: string): string {
  return valor === NAO_INFORMADO ? "Não informado" : valor;
}

/**
 * Aba exibida conforme o `?aba=` e o perfil.
 * Gestor: `insights` por padrão (ausente ou inválido) e `chamados` quando pedido.
 * Atendente: sempre `chamados`, qualquer que seja o parâmetro.
 */
export function abaEfetiva(parametro: string | null, perfil: PerfilDashboard): AbaDashboard {
  if (perfil !== "gestor") return "chamados";
  return parametro === "chamados" ? "chamados" : "insights";
}
