/**
 * Contrato da resposta de `GET /api/cs/insights` (design D4).
 *
 * Decimais chegam como texto (`"4.2"`), pois a API serializa `Decimal` como string.
 * Quando o denominador é zero, o lugar do número é ocupado por `SEM_DADOS`.
 */

/** Texto literal que a API devolve no lugar de um número sem denominador. */
export const SEM_DADOS = "sem dados";

/** Decimal em texto (`"4.2"`) ou `SEM_DADOS`. */
export type Decimal = string;

export type IdPeriodo = "hoje" | "7d" | "30d" | "personalizado";

export type Desfecho = "falso_defeito" | "defeito_real" | "nao_informado";

export interface PeriodoInsights {
  id: IdPeriodo;
  /** ISO 8601 com fuso (UTC). */
  inicio: string;
  fim: string;
}

export interface LinhaDistribuicao {
  nota: number;
  quantidade: number;
  percentual: Decimal;
}

export interface NotaPorCamada {
  camada: "guia" | "humano";
  nota_media: Decimal;
  avaliacoes: number;
}

export interface Satisfacao {
  nota_media: Decimal;
  total: number;
  /** Sempre 5 linhas (notas 1 a 5), zeros incluídos. */
  distribuicao: LinhaDistribuicao[];
  por_camada: NotaPorCamada[];
}

export interface ComentarioInsights {
  nota: number;
  /** Instante da avaliação em ISO 8601. */
  em: string;
  /** Texto já mascarado pela API; exibir sempre como texto simples. */
  texto: string;
}

export interface TempoAtendimento {
  /** Texto `min:seg` (ex.: `"5:12"`) ou `SEM_DADOS`. */
  media: string;
  mediana: string;
  quantidade: number;
}

export interface Atendimento {
  ate_assumir: TempoAtendimento;
  ate_encerrar: TempoAtendimento;
}

export interface LinhaDesfecho {
  desfecho: Desfecho;
  quantidade: number;
  percentual: Decimal;
}

export interface ResumoDesfecho {
  total: number;
  /** Sempre as 3 linhas, na ordem falso_defeito, defeito_real, nao_informado. */
  itens: LinhaDesfecho[];
  precisao_escalada_pct: Decimal;
}

export interface P1Risco {
  total: number;
  nao_encerrados: number;
}

export interface SolucaoMaisRegistrada {
  solucao_tipo: string;
  solucao: string;
  quantidade: number;
}

export interface ItemRanking {
  problema_id: number;
  titulo: string;
  selecoes: number;
  chamados: number;
  falso_defeito_pct: Decimal;
  /** `SEM_DADOS` quando o problema não tem Chamado encerrado no período. */
  solucao_mais_registrada: SolucaoMaisRegistrada | typeof SEM_DADOS;
}

export interface LinhaOrigem {
  origem: "qr" | "busca";
  quantidade: number;
  percentual: Decimal;
}

export interface LinhaDeflexao {
  camada: "guia" | "humano" | "abandonada";
  quantidade: number;
  percentual: Decimal;
}

export interface Funil {
  total_encerradas: number;
  por_origem: LinhaOrigem[];
  abandono_pct: Decimal;
  deflexao: LinhaDeflexao[];
}

export interface RespostaInsights {
  periodo: PeriodoInsights;
  modo_local: boolean;
  satisfacao: Satisfacao;
  comentarios: ComentarioInsights[];
  atendimento: Atendimento;
  desfecho: ResumoDesfecho;
  p1_risco: P1Risco;
  ranking_problemas: ItemRanking[];
  /** `null` quando a leitura das Jornadas encerradas falhou. */
  funil: Funil | null;
}

/**
 * Estado da busca de Insights (design D12). Em `pronto`, `dados` é a resposta
 * da consulta atual; nunca de outro Período nem de antes de "Tentar novamente".
 */
export type EstadoInsights =
  | { fase: "carregando" }
  | { fase: "erro" }
  | { fase: "pronto"; dados: RespostaInsights };

/** O que `useBuscaInsights` entrega: o estado e a ação de repetir a busca. */
export interface FonteInsights {
  estado: EstadoInsights;
  recarregar(): void;
}
