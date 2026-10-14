import { criarArmazenamentoSessao, type ArmazenamentoChaveValor } from "../api/armazenamento";

/**
 * Estado do alerta de risco de segurança (Req 8.3, 8.4, 8.6).
 *
 * ## Contrato que as rotas do servidor devem cumprir
 *
 * Toda resposta JSON de `/api/pub` que se refere a uma Jornada (inclusive o
 * corpo de erros 4xx/5xx, ao lado de `erro`) PODE trazer o envelope `jornada`:
 *
 * ```json
 * {
 *   "jornada": {
 *     "jornada_id": "01J...",
 *     "estado": "ativa | escalada | encerrada_guia | encerrada_ia | encerrada_humano | abandonada",
 *     "risco": { "marcado": true, "origem": "lista | ia | guia", "em": "2025-01-01T12:00:00Z" },
 *     "contato_cs": "confirmado | pendente | nao_registrado"
 *   }
 * }
 * ```
 *
 * - `risco.marcado` espelha `Jornada.risco` do banco (monotônico no servidor, Req 8.4).
 *   Rotas que podem marcar risco (`/mensagens`, `/vazamento`, `/escalar`, `/resolucao`)
 *   DEVEM incluir o envelope; as demais, de preferência.
 * - `contato_cs` diz se o repasse P1 ao CS foi confirmado (Req 8.5, 8.6).
 *   `pendente` por mais de 10 s no cliente é tratado como "não registrado".
 *   Ausente com risco marcado equivale a `pendente`.
 * - `estado` terminal (`encerrada_*`, `abandonada`) encerra o alerta (Req 8.3).
 * - `GET /jornadas/{id}` devolve `{ "jornada": { ... } }` e é usado ao abrir o
 *   Portal (recarga da página) para renovar o cache local.
 * - `POST /jornadas/{id}/escalar` com `{ "motivo": "risco", "evento_id": "..." }`
 *   é a ação "Tentar novamente": idempotente (Req 9.9), refaz o repasse P1 se ele
 *   ainda não foi registrado e responde com o envelope `jornada`.
 *
 * ## Garantias do cliente
 *
 * - O estado só muda por respostas do servidor (`registrarRespostaServidor`).
 *   Nenhuma ação da interface remove o alerta.
 * - Dentro da mesma Jornada o risco é monotônico: resposta atrasada com
 *   `marcado: false` é ignorada, e `confirmado` nunca volta a `pendente`.
 * - O `sessionStorage` guarda apenas uma cópia do que o servidor disse, para o
 *   alerta aparecer logo depois de uma recarga, até a próxima resposta.
 */
export const CHAVE_RISCO = "tres.risco";
/** Tempo máximo para o servidor confirmar o repasse ao CS (Req 8.6). */
export const PRAZO_CONFIRMACAO_CONTATO_MS = 10_000;

export type OrigemRisco = "lista" | "ia" | "guia";
export type SituacaoContato = "confirmado" | "pendente" | "nao_registrado";

export interface EstadoRisco {
  /** Jornada a que o estado se refere (a última informada pelo servidor). */
  jornadaId: string | null;
  /** Risco marcado e Jornada ainda não encerrada: o alerta deve aparecer. */
  ativo: boolean;
  /** O servidor informou o fim da Jornada; respostas atrasadas não reativam o alerta. */
  encerrada: boolean;
  origem?: OrigemRisco;
  em?: string;
  contato: SituacaoContato;
  /** Momento (relógio local) em que o contato passou a `pendente`; base do prazo de 10 s. */
  contatoDesde: number;
}

export const ESTADO_INICIAL: EstadoRisco = {
  jornadaId: null,
  ativo: false,
  encerrada: false,
  contato: "pendente",
  contatoDesde: 0,
};

const ESTADOS_TERMINAIS = new Set(["encerrada_guia", "encerrada_ia", "encerrada_humano", "abandonada"]);
const ORIGENS: readonly string[] = ["lista", "ia", "guia"];
const CONTATOS: readonly string[] = ["confirmado", "pendente", "nao_registrado"];

export interface ArmazemRisco {
  obter(): EstadoRisco;
  assinar(ouvinte: () => void): () => void;
  /** Lê o envelope `jornada` de uma resposta do servidor. Ignora o que não se encaixa no contrato. */
  registrarRespostaServidor(corpo: unknown): void;
}

function registro(valor: unknown): Record<string, unknown> | null {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor)
    ? (valor as Record<string, unknown>)
    : null;
}

function lerCache(armazenamento: ArmazenamentoChaveValor): EstadoRisco {
  try {
    const bruto = armazenamento.getItem(CHAVE_RISCO);
    const dados = bruto ? registro(JSON.parse(bruto)) : null;
    if (!dados || dados.ativo !== true || typeof dados.jornadaId !== "string") return ESTADO_INICIAL;
    return {
      jornadaId: dados.jornadaId,
      ativo: true,
      encerrada: false,
      origem: ORIGENS.includes(dados.origem as string) ? (dados.origem as OrigemRisco) : undefined,
      em: typeof dados.em === "string" ? dados.em : undefined,
      contato: CONTATOS.includes(dados.contato as string) ? (dados.contato as SituacaoContato) : "pendente",
      contatoDesde: Date.now(),
    };
  } catch {
    return ESTADO_INICIAL;
  }
}

function gravarCache(armazenamento: ArmazenamentoChaveValor, estado: EstadoRisco): void {
  try {
    if (!estado.ativo) {
      armazenamento.removeItem(CHAVE_RISCO);
      return;
    }
    const { jornadaId, ativo, origem, em, contato } = estado;
    armazenamento.setItem(CHAVE_RISCO, JSON.stringify({ jornadaId, ativo, origem, em, contato }));
  } catch {
    // O cache é só uma conveniência: falhar em gravá-lo não pode afetar o fluxo.
  }
}

export function criarArmazemRisco(
  armazenamento: ArmazenamentoChaveValor = criarArmazenamentoSessao(),
): ArmazemRisco {
  let estado = lerCache(armazenamento);
  const ouvintes = new Set<() => void>();

  function definir(novo: EstadoRisco) {
    estado = novo;
    gravarCache(armazenamento, novo);
    ouvintes.forEach((ouvinte) => ouvinte());
  }

  function registrarRespostaServidor(corpo: unknown): void {
    const jornada = registro(registro(corpo)?.jornada);
    if (!jornada || typeof jornada.jornada_id !== "string" || !jornada.jornada_id) return;
    const id = jornada.jornada_id;
    const mesma = estado.jornadaId === id;

    if (typeof jornada.estado === "string" && ESTADOS_TERMINAIS.has(jornada.estado)) {
      // Fim da Jornada: único caminho para o alerta sumir (Req 8.3).
      if ((mesma && !estado.encerrada) || (!mesma && !estado.ativo)) {
        definir({ ...ESTADO_INICIAL, jornadaId: id, encerrada: true });
      }
      return;
    }

    if (mesma && estado.encerrada) return;

    const risco = registro(jornada.risco);
    if (risco?.marcado === true) {
      const contatoInformado = CONTATOS.includes(jornada.contato_cs as string)
        ? (jornada.contato_cs as SituacaoContato)
        : "pendente";
      // `confirmado` é definitivo: uma resposta atrasada não pode desfazê-lo.
      const contato = mesma && estado.ativo && estado.contato === "confirmado" ? "confirmado" : contatoInformado;
      const mudouContato = !(mesma && estado.ativo) || contato !== estado.contato;
      const mantem = mesma && estado.ativo;
      const proximo: EstadoRisco = {
        jornadaId: id,
        ativo: true,
        encerrada: false,
        // Mantém a primeira origem e o primeiro horário: a marcação ocorre uma vez (Req 8.5).
        origem: mantem ? estado.origem : ORIGENS.includes(risco.origem as string) ? (risco.origem as OrigemRisco) : undefined,
        em: mantem ? estado.em : typeof risco.em === "string" ? risco.em : undefined,
        contato,
        contatoDesde: mudouContato ? Date.now() : estado.contatoDesde,
      };
      if (
        mantem &&
        proximo.contato === estado.contato &&
        proximo.origem === estado.origem &&
        proximo.em === estado.em
      ) {
        return;
      }
      definir(proximo);
      return;
    }

    // Sem risco marcado: dentro da mesma Jornada a marcação nunca é desfeita (Req 8.4).
    if (mesma) return;
    // Outra Jornada, informada pelo servidor sem risco: o alerta anterior deixa de valer.
    definir({ ...ESTADO_INICIAL, jornadaId: id });
  }

  return {
    obter: () => estado,
    assinar(ouvinte) {
      ouvintes.add(ouvinte);
      return () => void ouvintes.delete(ouvinte);
    },
    registrarRespostaServidor,
  };
}

/** Instância usada pelo cliente HTTP e, por padrão, pelo `RiscoProvider`. */
export const armazemRisco: ArmazemRisco = criarArmazemRisco();

/** Atalho para quem não está num componente: informa uma resposta do servidor. */
export function registrarRespostaServidor(corpo: unknown): void {
  armazemRisco.registrarRespostaServidor(corpo);
}
