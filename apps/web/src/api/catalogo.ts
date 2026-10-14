import { ErroApi, api, type ClienteApi } from "./cliente";
import { lerJornadaId, salvarJornadaId } from "./jornada";
import { ordenarPorNome } from "../busca/filtro";

/** Modelo do Catalogo_Maquinas como a grade da página inicial usa. */
export interface ModeloCatalogo {
  modelo_id: string;
  nome: string;
  foto_url?: string;
}

interface ModeloBruto {
  modelo_id?: unknown;
  nome?: unknown;
  foto_url?: unknown;
  ativo?: unknown;
}

/**
 * `GET /api/pub/modelos`. Aceita `{ modelos: [...] }` ou a lista direta.
 * Devolve só modelos ativos, em ordem alfabética de nome (Req 2.1).
 */
export async function carregarCatalogo(
  cliente: ClienteApi = api,
  sinal?: AbortSignal,
): Promise<ModeloCatalogo[]> {
  const resposta = await cliente.get<{ modelos?: unknown } | unknown[]>("/modelos", { sinal });
  const lista = Array.isArray(resposta) ? resposta : resposta?.modelos;
  if (!Array.isArray(lista)) {
    throw new ErroApi("resposta", "A resposta do servidor não pôde ser lida.");
  }
  const modelos: ModeloCatalogo[] = [];
  for (const item of lista as ModeloBruto[]) {
    if (typeof item?.modelo_id !== "string" || typeof item.nome !== "string") continue;
    if (item.ativo === false) continue;
    modelos.push({
      modelo_id: item.modelo_id,
      nome: item.nome,
      foto_url: typeof item.foto_url === "string" && item.foto_url ? item.foto_url : undefined,
    });
  }
  return ordenarPorNome(modelos);
}

function extrairJornadaId(resposta: unknown): string {
  const id = (resposta as { jornada_id?: unknown } | null)?.jornada_id;
  if (typeof id !== "string" || !id) {
    throw new ErroApi("resposta", "A resposta do servidor não pôde ser lida.");
  }
  return id;
}

/**
 * Registra na Jornada a origem "busca" e o modelo escolhido (Req 2.4).
 * Com Jornada já iniciada (por exemplo um QR não reconhecido), associa o modelo
 * a ela (`PUT /jornadas/{id}/modelo`); sem Jornada, cria uma (`POST /jornadas`).
 */
export async function selecionarModeloPorBusca(
  modeloId: string,
  cliente: ClienteApi = api,
): Promise<string> {
  const existente = lerJornadaId();
  if (existente) {
    try {
      await cliente.put(`/jornadas/${encodeURIComponent(existente)}/modelo`, { modelo_id: modeloId });
      return existente;
    } catch (erro) {
      // Jornada desconhecida pelo servidor: segue para criar uma nova.
      if (!(erro instanceof ErroApi && erro.status === 404)) throw erro;
    }
  }
  const criada = await cliente.post("/jornadas", { modelo_id: modeloId, origem: "busca" });
  const jornadaId = extrairJornadaId(criada);
  salvarJornadaId(jornadaId);
  return jornadaId;
}
