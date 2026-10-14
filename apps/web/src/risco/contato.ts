import { api, type ClienteApi } from "../api/cliente";
import { novoUlid } from "../api/ulid";
import type { ArmazemRisco } from "./armazemRisco";

/** Tempo para o servidor confirmar o repasse ao refazê-lo (Req 8.6). */
const TIMEOUT_REPASSE_MS = 10_000;

/**
 * "Tentar novamente" do aviso de contato não registrado (Req 8.6).
 * `POST /jornadas/{id}/escalar {motivo: "risco"}` é idempotente no servidor (Req 9.9):
 * refaz o repasse P1 se ainda não houve e devolve o envelope `jornada`.
 * Lança `ErroApi` se a chamada falhar.
 */
export async function tentarNovamenteContato(
  jornadaId: string,
  armazem: ArmazemRisco,
  cliente: ClienteApi = api,
): Promise<void> {
  const eventoId = novoUlid();
  const resposta = await cliente.post<unknown>(
    `/jornadas/${encodeURIComponent(jornadaId)}/escalar`,
    { motivo: "risco", evento_id: eventoId },
    { idempotencyKey: eventoId, timeoutMs: TIMEOUT_REPASSE_MS },
  );
  armazem.registrarRespostaServidor(resposta);
}

/**
 * Renova o estado a partir do servidor (`GET /jornadas/{id}`), por exemplo ao abrir
 * o Portal depois de uma recarga. Falhas são ignoradas: vale o último estado conhecido.
 */
export async function sincronizarJornada(
  jornadaId: string,
  armazem: ArmazemRisco,
  cliente: ClienteApi = api,
  sinal?: AbortSignal,
): Promise<void> {
  try {
    const resposta = await cliente.get<unknown>(`/jornadas/${encodeURIComponent(jornadaId)}`, { sinal });
    if (!sinal?.aborted) armazem.registrarRespostaServidor(resposta);
  } catch {
    // Sem rede ou rota indisponível: o alerta já exibido continua como está.
  }
}
