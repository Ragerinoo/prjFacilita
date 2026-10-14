import { ErroApi, api, type ClienteApi } from "./cliente";

/**
 * Chamadas da tela de instrução (Req 3, 5). Todas usam `jornada_id`.
 *
 * - `GET  /jornadas/{id}/instrucao?problema_id=&variante=`: passos determinísticos.
 *   404 (ou lista de passos vazia) significa "sem instrução para este modelo" (Req 3.10).
 * - `POST /jornadas/{id}/vazamento`  `{tipo: externo|interno}`: interno marca risco e escala.
 * - `POST /jornadas/{id}/resolucao`  `{resolvido, problema_id, evento_id}`: "Sim/Não" do guia.
 *
 * O formato dos passos segue `seed/instrucoes/*.json`. Os campos
 * `midia_estatica_url` (imagem parada de uma animação ou vídeo) são opcionais.
 */
export type TipoMidia = "imagem" | "animacao" | "video";
export type VarianteInstrucao = "padrao" | "externo";

export interface PassoInstrucao {
  n: number;
  texto: string;
  alt: string;
  texto_equivalente: string;
  midia_url?: string;
  midia_tipo: TipoMidia;
  /** Imagem estática usada com movimento reduzido (Req 19.7). */
  midia_estatica_url?: string;
}

export interface Instrucao {
  problema_id: string | number;
  variante: string;
  passos: PassoInstrucao[];
}

function texto(valor: unknown): string | undefined {
  return typeof valor === "string" && valor ? valor : undefined;
}

function tipoMidia(valor: unknown): TipoMidia {
  const v = typeof valor === "string" ? valor.toLowerCase() : "";
  if (v === "animacao" || v === "animação" || v === "gif") return "animacao";
  if (v === "video" || v === "vídeo") return "video";
  return "imagem";
}

function lerPasso(bruto: unknown, posicao: number): PassoInstrucao | null {
  if (!bruto || typeof bruto !== "object") return null;
  const item = bruto as Record<string, unknown>;
  const passoTexto = texto(item.texto);
  if (!passoTexto) return null;
  const alt = texto(item.alt) ?? "";
  return {
    n: typeof item.n === "number" ? item.n : posicao + 1,
    texto: passoTexto,
    alt,
    // Req 19.5: sempre há um texto equivalente, mesmo que o cadastro o omita.
    texto_equivalente: texto(item.texto_equivalente) ?? passoTexto,
    midia_url: texto(item.midia_url),
    midia_tipo: tipoMidia(item.midia_tipo),
    midia_estatica_url: texto(item.midia_estatica_url),
  };
}

/** Não existe instrução para a combinação modelo + problema (HTTP 404). */
export function instrucaoInexistente(erro: unknown): boolean {
  return erro instanceof ErroApi && erro.tipo === "http" && erro.status === 404;
}

/**
 * Devolve a instrução ou `null` quando não há instrução cadastrada (Req 3.10).
 * Outras falhas (rede, timeout, 5xx) são lançadas para a tela oferecer "tentar novamente".
 */
export async function carregarInstrucao(
  jornadaId: string,
  problemaId: string | number,
  variante?: VarianteInstrucao,
  cliente: ClienteApi = api,
  sinal?: AbortSignal,
): Promise<Instrucao | null> {
  const consulta = new URLSearchParams({ problema_id: String(problemaId) });
  if (variante) consulta.set("variante", variante);
  let resposta: Record<string, unknown> | null;
  try {
    resposta = await cliente.get<Record<string, unknown> | null>(
      `/jornadas/${encodeURIComponent(jornadaId)}/instrucao?${consulta.toString()}`,
      { sinal },
    );
  } catch (erro) {
    if (instrucaoInexistente(erro)) return null;
    throw erro;
  }
  if (!resposta || typeof resposta !== "object") {
    throw new ErroApi("resposta", "A resposta do servidor não pôde ser lida.");
  }
  const bruto = (typeof resposta.instrucao === "object" && resposta.instrucao !== null
    ? resposta.instrucao
    : resposta) as Record<string, unknown>;
  if (!Array.isArray(bruto.passos)) {
    throw new ErroApi("resposta", "A resposta do servidor não pôde ser lida.");
  }
  const passos = bruto.passos
    .map((p, i) => lerPasso(p, i))
    .filter((p): p is PassoInstrucao => p !== null)
    .sort((a, b) => a.n - b.n);
  if (passos.length === 0) return null;
  const id = bruto.problema_id;
  return {
    problema_id: typeof id === "string" || typeof id === "number" ? id : problemaId,
    variante: texto(bruto.variante) ?? variante ?? "padrao",
    passos,
  };
}

/** Número do Chamado, quando a resposta o traz (`numero`, `chamado.numero` ou `numero_chamado`). */
export function lerNumeroChamado(resposta: unknown): string | undefined {
  if (!resposta || typeof resposta !== "object") return undefined;
  const dados = resposta as Record<string, unknown>;
  const chamado = typeof dados.chamado === "object" && dados.chamado !== null ? (dados.chamado as Record<string, unknown>) : {};
  for (const candidato of [dados.numero, chamado.numero, dados.numero_chamado]) {
    if (typeof candidato === "string" && candidato) return candidato;
    if (typeof candidato === "number") return String(candidato);
  }
  return undefined;
}

/** `POST /vazamento`. Para "interno" o servidor marca risco (origem "guia") e escala (Req 3.8, 8.7). */
export async function informarVazamento(
  jornadaId: string,
  tipo: "externo" | "interno",
  eventoId: string,
  cliente: ClienteApi = api,
): Promise<{ numero?: string }> {
  const resposta = await cliente.post<unknown>(
    `/jornadas/${encodeURIComponent(jornadaId)}/vazamento`,
    { tipo, evento_id: eventoId },
    { idempotencyKey: eventoId },
  );
  return { numero: lerNumeroChamado(resposta) };
}

/**
 * `POST /resolucao`. "Sim" marca a Jornada como resolvida na camada "guia" (Req 5.2).
 * "Não" faz o Motor_Escalada iniciar o repasse com prioridade P2 (Req 5.3) e devolve o Chamado.
 */
export async function registrarResolucao(
  jornadaId: string,
  dados: { resolvido: boolean; problemaId: string | number; eventoId: string },
  cliente: ClienteApi = api,
): Promise<{ numero?: string }> {
  const resposta = await cliente.post<unknown>(
    `/jornadas/${encodeURIComponent(jornadaId)}/resolucao`,
    { resolvido: dados.resolvido, problema_id: dados.problemaId, evento_id: dados.eventoId },
    { idempotencyKey: dados.eventoId },
  );
  return { numero: lerNumeroChamado(resposta) };
}
