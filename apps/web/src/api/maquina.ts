import { ErroApi, api, type ClienteApi } from "./cliente";

/** Tempo máximo da consulta ao Catalogo_Maquinas num acesso por QR (Req 1.7). */
export const TIMEOUT_CATALOGO_QR_MS = 5000;

export interface ModeloMaquina {
  modelo_id: string;
  nome: string;
  foto_url?: string;
}

export interface ProblemaCatalogado {
  problema_id: string | number;
  ordem: number;
  titulo: string;
  icone: string;
  icone_alt: string;
}

export interface DadosMaquina {
  modelo: ModeloMaquina;
  problemas: ProblemaCatalogado[];
  /** Mapa do Seletor_Visual (tarefa 22). Repassado sem interpretação. */
  seletor?: unknown;
}

/** O modelo não existe no Catalogo_Maquinas (HTTP 404). */
export function modeloNaoReconhecido(erro: unknown): boolean {
  return erro instanceof ErroApi && erro.tipo === "http" && erro.status === 404;
}

function textoOuUndefined(valor: unknown): string | undefined {
  return typeof valor === "string" && valor ? valor : undefined;
}

function lerProblemas(lista: unknown): ProblemaCatalogado[] {
  if (!Array.isArray(lista)) {
    throw new ErroApi("resposta", "A resposta do servidor não pôde ser lida.");
  }
  const problemas: ProblemaCatalogado[] = [];
  lista.forEach((item: Record<string, unknown> | null, posicao) => {
    const id = item?.problema_id;
    const titulo = item?.titulo;
    if ((typeof id !== "string" && typeof id !== "number") || typeof titulo !== "string" || !titulo) return;
    problemas.push({
      problema_id: id,
      ordem: typeof item?.ordem === "number" ? item.ordem : posicao + 1,
      titulo,
      icone: textoOuUndefined(item?.icone) ?? "",
      icone_alt: textoOuUndefined(item?.icone_alt) ?? `Ícone de ${titulo.toLowerCase()}`,
    });
  });
  // Ordem do Req 3.1; `sort` é estável, então empates mantêm a ordem recebida.
  return problemas.sort((a, b) => a.ordem - b.ordem);
}

/**
 * `GET /api/pub/modelos/{modelo_id}`: modelo, 13 problemas e mapa do seletor.
 * Aceita `{ modelo: {...}, problemas, seletor }` ou os campos do modelo no
 * nível raiz. Timeout de 5 s (Req 1.7); 404 significa modelo não reconhecido.
 */
export async function carregarMaquina(
  modeloId: string,
  cliente: ClienteApi = api,
  sinal?: AbortSignal,
): Promise<DadosMaquina> {
  const resposta = await cliente.get<Record<string, unknown> | null>(
    `/modelos/${encodeURIComponent(modeloId)}`,
    { sinal, timeoutMs: TIMEOUT_CATALOGO_QR_MS },
  );
  if (!resposta || typeof resposta !== "object") {
    throw new ErroApi("resposta", "A resposta do servidor não pôde ser lida.");
  }
  const bruto = (typeof resposta.modelo === "object" && resposta.modelo !== null
    ? resposta.modelo
    : resposta) as Record<string, unknown>;
  const nome = textoOuUndefined(bruto.nome);
  if (!nome) throw new ErroApi("resposta", "A resposta do servidor não pôde ser lida.");
  return {
    modelo: {
      modelo_id: textoOuUndefined(bruto.modelo_id) ?? modeloId,
      nome,
      foto_url: textoOuUndefined(bruto.foto_url),
    },
    problemas: lerProblemas(resposta.problemas),
    seletor: resposta.seletor ?? bruto.seletor ?? undefined,
  };
}
