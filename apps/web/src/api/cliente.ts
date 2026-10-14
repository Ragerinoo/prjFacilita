import { registrarRespostaServidor } from "../risco/armazemRisco";

/**
 * Cliente HTTP da API pública (`/api/pub`), com timeout e erros padronizados.
 *
 * Contrato de erro (design.md): `{ erro: { codigo, mensagem, campos? } }`.
 */
export const BASE_API_PUBLICA = "/api/pub";
export const TIMEOUT_PADRAO_MS = 5000;

export type TipoErroApi = "timeout" | "rede" | "http" | "resposta";

export interface CampoInvalido {
  campo: string;
  motivo: string;
}

export class ErroApi extends Error {
  readonly tipo: TipoErroApi;
  readonly status?: number;
  readonly codigo?: string;
  readonly campos?: CampoInvalido[];

  constructor(
    tipo: TipoErroApi,
    mensagem: string,
    detalhes: { status?: number; codigo?: string; campos?: CampoInvalido[] } = {},
  ) {
    super(mensagem);
    this.name = "ErroApi";
    this.tipo = tipo;
    this.status = detalhes.status;
    this.codigo = detalhes.codigo;
    this.campos = detalhes.campos;
  }

  /** Falhas que não adianta repetir: o servidor recusou a requisição. */
  get definitivo(): boolean {
    return (
      this.tipo === "http" &&
      this.status !== undefined &&
      this.status >= 400 &&
      this.status < 500 &&
      this.status !== 408 &&
      this.status !== 429
    );
  }
}

export interface OpcoesRequisicao {
  metodo?: "GET" | "POST" | "PUT";
  corpo?: unknown;
  timeoutMs?: number;
  /** Chave de idempotência das mutações (usamos o `evento_id`). */
  idempotencyKey?: string;
  sinal?: AbortSignal;
}

export interface ConfiguracaoCliente {
  baseUrl?: string;
  timeoutMs?: number;
  /** Resolvido a cada chamada, para permitir substituição em testes. */
  fetchImpl?: typeof fetch;
  /**
   * Recebe o corpo JSON de toda resposta (sucesso ou erro) do servidor. Usado
   * para o envelope `jornada` do alerta de risco (Req 8.3), sem tocar nas páginas.
   */
  aoResponder?: (corpo: unknown) => void;
}

export interface ClienteApi {
  requisitar<T = unknown>(caminho: string, opcoes?: OpcoesRequisicao): Promise<T>;
  get<T = unknown>(caminho: string, opcoes?: Omit<OpcoesRequisicao, "metodo" | "corpo">): Promise<T>;
  post<T = unknown>(
    caminho: string,
    corpo?: unknown,
    opcoes?: Omit<OpcoesRequisicao, "metodo" | "corpo">,
  ): Promise<T>;
  put<T = unknown>(
    caminho: string,
    corpo?: unknown,
    opcoes?: Omit<OpcoesRequisicao, "metodo" | "corpo">,
  ): Promise<T>;
}

async function lerErroHttp(resposta: Response, aoResponder?: (corpo: unknown) => void): Promise<ErroApi> {
  let codigo: string | undefined;
  let mensagem = "Não foi possível concluir a operação.";
  let campos: CampoInvalido[] | undefined;
  try {
    const dados = (await resposta.json()) as {
      erro?: { codigo?: string; mensagem?: string; campos?: CampoInvalido[] };
    };
    informar(aoResponder, dados);
    codigo = dados.erro?.codigo;
    if (dados.erro?.mensagem) mensagem = dados.erro.mensagem;
    campos = dados.erro?.campos;
  } catch {
    // Corpo ausente ou fora do padrão: mantém a mensagem genérica.
  }
  return new ErroApi("http", mensagem, { status: resposta.status, codigo, campos });
}

function informar(aoResponder: ((corpo: unknown) => void) | undefined, corpo: unknown): void {
  try {
    aoResponder?.(corpo);
  } catch {
    // Quem observa a resposta nunca pode derrubar a requisição.
  }
}

export function criarClienteApi(config: ConfiguracaoCliente = {}): ClienteApi {
  const baseUrl = config.baseUrl ?? BASE_API_PUBLICA;
  const timeoutPadrao = config.timeoutMs ?? TIMEOUT_PADRAO_MS;

  async function requisitar<T>(caminho: string, opcoes: OpcoesRequisicao = {}): Promise<T> {
    const metodo = opcoes.metodo ?? "GET";
    const timeoutMs = opcoes.timeoutMs ?? timeoutPadrao;
    const controle = new AbortController();
    let expirou = false;
    const temporizador = setTimeout(() => {
      expirou = true;
      controle.abort();
    }, timeoutMs);
    const aoAbortarExterno = () => controle.abort();
    opcoes.sinal?.addEventListener("abort", aoAbortarExterno);
    if (opcoes.sinal?.aborted) controle.abort();

    const cabecalhos: Record<string, string> = { Accept: "application/json" };
    if (opcoes.corpo !== undefined) cabecalhos["Content-Type"] = "application/json";
    if (metodo !== "GET") cabecalhos["X-Requested-With"] = "tres-portal";
    if (opcoes.idempotencyKey) cabecalhos["Idempotency-Key"] = opcoes.idempotencyKey;

    try {
      const executar = config.fetchImpl ?? fetch;
      const resposta = await executar(`${baseUrl}${caminho}`, {
        method: metodo,
        headers: cabecalhos,
        body: opcoes.corpo === undefined ? undefined : JSON.stringify(opcoes.corpo),
        credentials: "same-origin",
        signal: controle.signal,
      });
      if (!resposta.ok) throw await lerErroHttp(resposta, config.aoResponder);
      if (resposta.status === 204) return undefined as T;
      try {
        const dados = (await resposta.json()) as T;
        informar(config.aoResponder, dados);
        return dados;
      } catch {
        throw new ErroApi("resposta", "A resposta do servidor não pôde ser lida.", {
          status: resposta.status,
        });
      }
    } catch (erro) {
      if (erro instanceof ErroApi) throw erro;
      if (expirou) {
        throw new ErroApi("timeout", "O servidor demorou para responder.");
      }
      throw new ErroApi("rede", "Não foi possível se conectar ao servidor.");
    } finally {
      clearTimeout(temporizador);
      opcoes.sinal?.removeEventListener("abort", aoAbortarExterno);
    }
  }

  return {
    requisitar,
    get: (caminho, opcoes) => requisitar(caminho, { ...opcoes, metodo: "GET" }),
    post: (caminho, corpo, opcoes) => requisitar(caminho, { ...opcoes, metodo: "POST", corpo }),
    put: (caminho, corpo, opcoes) => requisitar(caminho, { ...opcoes, metodo: "PUT", corpo }),
  };
}

/** Cliente padrão do Portal. */
export const api: ClienteApi = criarClienteApi({ aoResponder: registrarRespostaServidor });
