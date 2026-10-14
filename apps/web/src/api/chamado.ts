import { ErroApi, api, type CampoInvalido, type ClienteApi } from "./cliente";
import { novoUlid } from "./ulid";

/**
 * Chamado do ponto de vista do Consumidor (Req 12, 18.1, 18.5).
 *
 * ## Contrato com o backend (tarefa 12.4), rotas públicas `/api/pub`
 *
 * `GET /chamados/{numero}` → 200
 * ```json
 * {
 *   "numero": "TRES-7K3M9QX2PD",
 *   "status": "aberto | em_atendimento | encerrado",
 *   "prioridade": "P1 | P2 | P3",
 *   "canal": "ligação imediata",
 *   "criado_em": "2025-01-01T12:05:11Z",
 *   "dados_solicitados": ["telefone", "cep"],
 *   "anexos_total": 0,
 *   "mensagens": [{ "autor": "atendente", "texto": "Olá!", "em": "2025-01-01T12:30:00Z" }],
 *   "agendamento": { "data_hora": "2025-01-02T14:00:00-03:00" },
 *   "avaliacao_pendente": false
 * }
 * ```
 * - `dados_solicitados`: o que o Portal ainda deve pedir. É
 *   `dominio.validadores.dados_pessoais_solicitados(prioridade, ja_informados)`, ou seja, o exigido
 *   pela prioridade (P1: telefone; P2: telefone e CEP; P3: nenhum) menos o que já foi informado.
 *   Vazio quando nada falta. Se o campo faltar na resposta, o Portal calcula o mesmo a partir de
 *   `prioridade` (nunca pede de novo um dado que a resposta marque em `dados_informados`).
 * - `anexos_total`: fotos já vinculadas ao Chamado (0 a 3), para respeitar o limite após recarregar.
 * - A resposta nunca traz telefone nem CEP. O Portal mostra a `prioridade` só como rótulo (nunca "P1").
 * - 404 com `{erro: {codigo: "chamado_nao_encontrado", mensagem}}`, sem dados de nenhum Chamado.
 *
 * Acompanhamento (tarefa 14.7; Req 12.8, 15.4 a 15.6, 16.5). O Portal repete o `GET` a cada 5 s enquanto a
 * página está visível (pausa oculta, retoma ao voltar), então a resposta deve ser barata e consistente:
 * - `mensagens`: do Atendente e do Consumidor, em ordem cronológica crescente (o Portal reordena por `em`).
 *   `autor`: `"atendente" | "consumidor"`; `texto`: o texto já mascarado; `em`: instante ISO 8601 do envio ou
 *   recebimento. O Portal mostra data e hora no fuso de Brasília. Campo ausente equivale a lista vazia.
 *   Entradas com `autor` desconhecido ou sem `texto`/`em` são ignoradas.
 * - `agendamento`: `{ "data_hora": ISO 8601 com offset }` ou `null`/ausente quando não há ligação marcada.
 * - `status`: `"aberto" | "em_atendimento" | "encerrado"`.
 * - `avaliacao_pendente`: `true` quando o Chamado está `encerrado` e ainda não foi avaliado. Se o campo faltar, o
 *   Portal assume `true` para Chamado `encerrado`. Depois da avaliação, o servidor devolve `false`.
 * - Nenhum desses campos traz telefone, CEP ou o `jornada_id`.
 *
 * `POST /chamados/{numero}/mensagens` `{texto, evento_id}` (cabeçalho `Idempotency-Key` = `evento_id`)
 * - Resposta do Consumidor (Req 15.5). `texto`: 1 a 2000 caracteres, não só espaços (o Portal envia aparado).
 * - 201/200 (corpo ignorado; o Portal recarrega o Chamado em seguida). A mensagem deve aparecer em `mensagens` com
 *   `autor: "consumidor"` e marcar o Chamado como "resposta não lida" no Painel_CS.
 * - 422 → `{erro: {codigo: "dados_invalidos", mensagem, campos: [{campo: "texto", motivo}]}}`; 404 se o número não existe.
 *
 * `POST /chamados/{numero}/avaliacao` `{nota, comentario?, evento_id}` (cabeçalho `Idempotency-Key` = `evento_id`)
 * - Avaliação do Consumidor ao encerrar (Req 16.5). `nota`: inteiro de 1 a 5; `comentario`: até 500 caracteres.
 *   A GET pública não devolve o `jornada_id` (é a capacidade de agir na Jornada), então esta rota, indexada pelo
 *   número, faz o que `POST /jornadas/{id}/avaliacao` faz: registra a nota na Jornada do Chamado, na camada "humano",
 *   uma por Jornada (Req 5.5). Só vale para Chamado `encerrado`; senão 409. O mesmo envio repetido (`evento_id`) é ignorado.
 *
 * `POST /chamados/{numero}/contato` `{telefone?, cep?, consentimento: true, evento_id}`
 * (cabeçalho `Idempotency-Key` = `evento_id`)
 * - Só os campos que o Portal pediu. Valores como digitados (aparados), com dígitos, espaço, `()` e `-`.
 * - `consentimento` precisa ser `true`; senão 422. Telefone e CEP são validados como em `validar_telefone`
 *   e `validar_cep`.
 * - 200 → `{ "dados_solicitados": [...] }` com o que ainda falta (vazio quando completo).
 * - 422 → `{erro: {codigo: "dados_invalidos", mensagem, campos: [{campo: "telefone"|"cep"|"consentimento", motivo}]}}`.
 *
 * Fotos (Req 12.7, 12.10), em três passos; cada foto é independente das demais:
 * 1. `POST /chamados/{numero}/anexos` `{mime, bytes, evento_id}` → 201
 *    `{ "anexo_id": "...", "upload": { "url": "https://<bucket>.s3...", "campos": { "key": "...", ... } } }`.
 *    `upload` é um **POST pré-assinado do S3** (a política deve fixar `content-length-range` 1 a 5 MB,
 *    o `Content-Type` e validade curta). Recusa com 422 `{erro: {codigo: "foto_invalida", mensagem}}`
 *    (formato, tamanho) ou 409 `{erro: {codigo: "limite_fotos", mensagem}}` (já há 3).
 * 2. O navegador envia `multipart/form-data` direto ao S3 para `upload.url`: todos os `campos`, na ordem, e
 *    por último o campo `file`. Sucesso: 200, 201 ou 204. O bucket precisa de CORS para a origem do Portal.
 * 3. `POST /chamados/{numero}/anexos/{anexo_id}/confirmacao` `{}` → 200 `{ "anexos_total": 2 }`.
 *    O servidor confere que o objeto existe, tem o tamanho e o tipo declarados e só então vincula ao Chamado.
 *    Se a conferência falha: 422 `foto_invalida` e o objeto é descartado.
 */
export type DadoPessoal = "telefone" | "cep";
export type Prioridade = "P1" | "P2" | "P3";

export type AutorMensagem = "atendente" | "consumidor";

export interface MensagemChamado {
  autor: AutorMensagem;
  texto: string;
  /** Instante ISO 8601 de envio ou recebimento. */
  em: string;
}

export interface AgendamentoChamado {
  /** ISO 8601 com offset de Brasília. */
  dataHora: string;
}

export interface ChamadoPublico {
  numero: string;
  prioridade: Prioridade;
  status?: string;
  canal?: string;
  criadoEm?: string;
  dadosSolicitados: DadoPessoal[];
  anexosTotal: number;
  /** Em ordem cronológica. */
  mensagens: MensagemChamado[];
  agendamento: AgendamentoChamado | null;
  /** O Portal deve oferecer a avaliação (Chamado encerrado e ainda não avaliado). */
  avaliacaoPendente: boolean;
}

export const STATUS_ENCERRADO = "encerrado";
export const INTERVALO_ACOMPANHAMENTO_MS = 5000;

export interface ApresentacaoPrioridade {
  /** Rótulo em linguagem simples (Req 12.1): nunca "P1", "P2" ou "P3". */
  rotulo: string;
  /** Próximo passo esperado, com o prazo de contato. */
  proximoPasso: string;
}

export const PRIORIDADES: Record<Prioridade, ApresentacaoPrioridade> = {
  P1: {
    rotulo: "Atendimento urgente",
    proximoPasso: "Uma pessoa vai ligar para você em até 15 minutos.",
  },
  P2: {
    rotulo: "Atendimento prioritário",
    proximoPasso: "Uma pessoa vai entrar em contato com você em até 4 horas úteis.",
  },
  P3: {
    rotulo: "Atendimento comum",
    proximoPasso: "Você vai receber uma resposta em até 1 dia útil.",
  },
};

const DADOS_POR_PRIORIDADE: Record<Prioridade, DadoPessoal[]> = {
  P1: ["telefone"],
  P2: ["telefone", "cep"],
  P3: [],
};

/** Espelha `dominio.validadores.dados_pessoais_solicitados`. */
export function dadosSolicitados(prioridade: Prioridade, jaInformados: readonly DadoPessoal[] = []): DadoPessoal[] {
  return DADOS_POR_PRIORIDADE[prioridade].filter((d) => !jaInformados.includes(d));
}

function lerDados(bruto: unknown): DadoPessoal[] | undefined {
  if (!Array.isArray(bruto)) return undefined;
  const dados = bruto.filter((d): d is DadoPessoal => d === "telefone" || d === "cep");
  return DADOS_POR_PRIORIDADE.P2.filter((d) => dados.includes(d)); // ordem fixa, sem repetição
}

function lerMensagens(bruto: unknown): MensagemChamado[] {
  if (!Array.isArray(bruto)) return [];
  const lidas: MensagemChamado[] = [];
  for (const item of bruto) {
    if (!item || typeof item !== "object") continue;
    const { autor, texto, em } = item as Record<string, unknown>;
    if ((autor !== "atendente" && autor !== "consumidor") || typeof texto !== "string" || typeof em !== "string") continue;
    lidas.push({ autor, texto, em });
  }
  // Ordem cronológica; `sort` é estável, então instantes iguais mantêm a ordem do servidor.
  return lidas.sort((a, b) => (Date.parse(a.em) || 0) - (Date.parse(b.em) || 0));
}

function lerAgendamento(bruto: unknown): AgendamentoChamado | null {
  if (!bruto || typeof bruto !== "object") return null;
  const dataHora = (bruto as Record<string, unknown>).data_hora;
  return typeof dataHora === "string" && !Number.isNaN(Date.parse(dataHora)) ? { dataHora } : null;
}

function erroResposta(): ErroApi {
  return new ErroApi("resposta", "A resposta do servidor não pôde ser lida.");
}

export function chamadoNaoEncontrado(erro: unknown): boolean {
  return erro instanceof ErroApi && erro.tipo === "http" && erro.status === 404;
}

/** `GET /chamados/{numero}`. Lança `ErroApi` (404: use `chamadoNaoEncontrado`). */
export async function carregarChamado(
  numero: string,
  cliente: ClienteApi = api,
  sinal?: AbortSignal,
): Promise<ChamadoPublico> {
  const bruto = await cliente.get<Record<string, unknown> | null>(`/chamados/${encodeURIComponent(numero)}`, { sinal });
  if (!bruto || typeof bruto !== "object") throw erroResposta();
  const prioridade = bruto.prioridade;
  if (prioridade !== "P1" && prioridade !== "P2" && prioridade !== "P3") throw erroResposta();
  const solicitados =
    lerDados(bruto.dados_solicitados) ?? dadosSolicitados(prioridade, lerDados(bruto.dados_informados) ?? []);
  const total = bruto.anexos_total;
  const status = typeof bruto.status === "string" ? bruto.status : undefined;
  return {
    numero: typeof bruto.numero === "string" && bruto.numero ? bruto.numero : numero,
    prioridade,
    status,
    canal: typeof bruto.canal === "string" && bruto.canal ? bruto.canal : undefined,
    criadoEm: typeof bruto.criado_em === "string" ? bruto.criado_em : undefined,
    dadosSolicitados: solicitados,
    anexosTotal: typeof total === "number" && total >= 0 ? Math.floor(total) : 0,
    mensagens: lerMensagens(bruto.mensagens),
    agendamento: lerAgendamento(bruto.agendamento),
    avaliacaoPendente:
      typeof bruto.avaliacao_pendente === "boolean" ? bruto.avaliacao_pendente : status === STATUS_ENCERRADO,
  };
}

export const MAX_MENSAGEM = 2000;
export const MENSAGEM_TEXTO_VAZIO = "Escreva uma mensagem antes de enviar.";
export const MENSAGEM_TEXTO_LONGO = `A mensagem pode ter até ${MAX_MENSAGEM} caracteres.`;

/** Valida a resposta do Consumidor (1 a 2000 caracteres, não só espaços). Devolve o erro ou `null`. */
export function validarMensagem(texto: string): string | null {
  const aparado = texto.trim();
  if (!aparado) return MENSAGEM_TEXTO_VAZIO;
  if (aparado.length > MAX_MENSAGEM) return MENSAGEM_TEXTO_LONGO;
  return null;
}

/** `POST /chamados/{numero}/mensagens` (Req 15.5). Lança `ErroApi`. */
export async function enviarMensagem(numero: string, texto: string, cliente: ClienteApi = api): Promise<void> {
  const eventoId = novoUlid();
  await cliente.post(
    `/chamados/${encodeURIComponent(numero)}/mensagens`,
    { texto: texto.trim(), evento_id: eventoId },
    { idempotencyKey: eventoId },
  );
}

/** Caminho da avaliação do Chamado (Req 16.5), usado com `AvaliacaoEstrelas`. */
export function caminhoAvaliacao(numero: string): string {
  return `/chamados/${encodeURIComponent(numero)}/avaliacao`;
}

export interface DadosContato {
  telefone?: string;
  cep?: string;
}

/** `POST /chamados/{numero}/contato` (Req 12.2 a 12.6). Devolve o que ainda falta. */
export async function enviarContato(
  numero: string,
  dados: DadosContato,
  cliente: ClienteApi = api,
): Promise<DadoPessoal[]> {
  const eventoId = novoUlid();
  const resposta = await cliente.post<{ dados_solicitados?: unknown } | undefined>(
    `/chamados/${encodeURIComponent(numero)}/contato`,
    { ...dados, consentimento: true, evento_id: eventoId },
    { idempotencyKey: eventoId },
  );
  return lerDados(resposta?.dados_solicitados) ?? [];
}

/** Erros por campo do envelope de erro (`campos`), agrupados pelo nome do campo. */
export function errosPorCampo(erro: unknown): Record<string, string> {
  const resultado: Record<string, string> = {};
  if (erro instanceof ErroApi) {
    erro.campos?.forEach((c: CampoInvalido) => {
      if (!(c.campo in resultado)) resultado[c.campo] = c.motivo;
    });
  }
  return resultado;
}

/** Envia um arquivo ao destino pré-assinado (POST multipart do S3). */
export type EnviadorArquivo = (url: string, corpo: FormData, sinal: AbortSignal) => Promise<Response>;

export const TIMEOUT_UPLOAD_MS = 30_000;
export const MENSAGEM_FALHA_FOTO = "Não foi possível enviar a foto. Tente de novo.";

const enviadorPadrao: EnviadorArquivo = (url, corpo, sinal) =>
  fetch(url, { method: "POST", body: corpo, signal: sinal });

interface RespostaAnexo {
  anexo_id?: unknown;
  upload?: { url?: unknown; campos?: unknown };
}

/**
 * Anexa uma foto: pede o destino pré-assinado, envia o arquivo e confirma (Req 12.7, 12.10).
 * Devolve o total de fotos do Chamado informado pelo servidor, se vier. Lança `ErroFoto` com o motivo em português; falha de uma foto
 * não afeta o Chamado nem as fotos já anexadas.
 */
export async function anexarFoto(
  numero: string,
  arquivo: File,
  cliente: ClienteApi = api,
  enviar: EnviadorArquivo = enviadorPadrao,
): Promise<number | undefined> {
  const base = `/chamados/${encodeURIComponent(numero)}/anexos`;
  try {
    const eventoId = novoUlid();
    const pedido = await cliente.post<RespostaAnexo>(
      base,
      { mime: arquivo.type, bytes: arquivo.size, evento_id: eventoId },
      { idempotencyKey: eventoId },
    );
    const url = pedido?.upload?.url;
    const campos = pedido?.upload?.campos;
    if (typeof pedido?.anexo_id !== "string" || typeof url !== "string" || !campos || typeof campos !== "object") {
      throw erroResposta();
    }
    const corpo = new FormData();
    Object.entries(campos as Record<string, unknown>).forEach(([nome, valor]) => corpo.append(nome, String(valor)));
    corpo.append("file", arquivo); // o S3 exige o arquivo como último campo
    const controle = new AbortController();
    const temporizador = setTimeout(() => controle.abort(), TIMEOUT_UPLOAD_MS);
    let envio: Response;
    try {
      envio = await enviar(url, corpo, controle.signal);
    } finally {
      clearTimeout(temporizador);
    }
    if (!envio.ok) throw new ErroApi("http", MENSAGEM_FALHA_FOTO, { status: envio.status });
    const confirmacao = await cliente.post<{ anexos_total?: unknown } | undefined>(
      `${base}/${encodeURIComponent(pedido.anexo_id)}/confirmacao`,
      {},
    );
    const total = confirmacao?.anexos_total;
    return typeof total === "number" ? total : undefined;
  } catch (erro) {
    throw new ErroFoto(motivoDaFalhaDeFoto(erro));
  }
}

export class ErroFoto extends Error {
  constructor(mensagem: string) {
    super(mensagem);
    this.name = "ErroFoto";
  }
}

function motivoDaFalhaDeFoto(erro: unknown): string {
  // Recusas do servidor (4xx) trazem o motivo em português; o resto é falha de envio.
  if (erro instanceof ErroApi && erro.definitivo && erro.message) return erro.message;
  return MENSAGEM_FALHA_FOTO;
}
