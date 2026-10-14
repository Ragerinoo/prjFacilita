import { criarClienteApi, type ClienteApi } from "../api/cliente";

/**
 * Cliente HTTP da API do Painel_CS (`/api/cs`).
 *
 * Mesmo modelo de erro do Portal (`ErroApi`). A sessão é um cookie HttpOnly enviado
 * pelo navegador (`credentials: same-origin`, definido em `criarClienteApi`); o
 * cabeçalho `X-Requested-With` vai em toda mutação (proteção anti-CSRF do servidor,
 * Req 13.2).
 *
 * Qualquer 401 fora do login significa "sessão expirada ou inexistente": os ouvintes
 * registrados são avisados para limpar o estado e voltar ao login sem mostrar dados
 * (Req 13.5, 13.6).
 */
export const BASE_API_CS = "/api/cs";

/** Prazo maior que o do Portal: o Painel lê Chamados e dados pessoais. */
export const TIMEOUT_CS_MS = 10_000;

const ouvintesExpiracao = new Set<() => void>();

/** Registra um ouvinte de sessão expirada. Devolve a função que o remove. */
export function aoSessaoExpirar(ouvinte: () => void): () => void {
  ouvintesExpiracao.add(ouvinte);
  return () => {
    ouvintesExpiracao.delete(ouvinte);
  };
}

function avisarExpiracao(): void {
  for (const ouvinte of [...ouvintesExpiracao]) {
    try {
      ouvinte();
    } catch {
      // Um ouvinte com defeito não pode impedir os demais nem a requisição.
    }
  }
}

function ehLogin(entrada: RequestInfo | URL): boolean {
  const url = typeof entrada === "string" ? entrada : entrada instanceof URL ? entrada.href : entrada.url;
  return url.split("?")[0].endsWith("/login");
}

/**
 * `fetch` que avisa os ouvintes em qualquer 401. O login fica de fora: lá o 401 é
 * "usuário ou senha inválidos" e não expiração. O corpo da resposta não é lido aqui.
 */
async function fetchComVigiaDeSessao(entrada: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const resposta = await fetch(entrada, init);
  if (resposta.status === 401 && !ehLogin(entrada)) avisarExpiracao();
  return resposta;
}

export function criarClienteCs(): ClienteApi {
  return criarClienteApi({
    baseUrl: BASE_API_CS,
    timeoutMs: TIMEOUT_CS_MS,
    fetchImpl: fetchComVigiaDeSessao,
  });
}

export const apiCs: ClienteApi = criarClienteCs();
