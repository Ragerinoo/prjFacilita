import { criarArmazenamentoSessao, type ArmazenamentoChaveValor } from "./armazenamento";
import { ErroApi, api, type ClienteApi } from "./cliente";
import { lerJornadaId, salvarJornadaId } from "./jornada";

/**
 * Regras do Codigo_QR no cliente (Req 1.2, 1.4, 1.5, 1.6).
 *
 * Espelham `packages/dominio/.../qr.py` (`interpretar_qr`). O servidor continua
 * sendo a fonte da verdade: aqui só evitamos enviar lixo e decidimos, antes da
 * chamada à API, se o código é legível.
 */
export const PADRAO_MODELO_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
export const TAMANHO_MAX_MODELO_ID = 64;
export const PADRAO_SERIE = /^[A-Za-z0-9]{1,30}$/;
export const PARAMETRO_SERIE = "s";

export type InterpretacaoQr =
  | { legivel: false }
  | { legivel: true; modeloId: string; numeroSerie?: string };

/**
 * `modeloId` vem do caminho `/m/:modeloId` e `consulta` do `?s=`.
 * Modelo ausente ou malformado → "não legível". Série fora do formato é
 * descartada em silêncio e o modelo segue válido. Nunca lança exceção.
 */
export function interpretarQr(modeloId: unknown, consulta: URLSearchParams | null): InterpretacaoQr {
  try {
    if (
      typeof modeloId !== "string" ||
      modeloId.length === 0 ||
      modeloId.length > TAMANHO_MAX_MODELO_ID ||
      !PADRAO_MODELO_ID.test(modeloId)
    ) {
      return { legivel: false };
    }
    const serie = consulta?.get(PARAMETRO_SERIE) ?? null;
    return {
      legivel: true,
      modeloId,
      numeroSerie: serie !== null && PADRAO_SERIE.test(serie) ? serie : undefined,
    };
  } catch {
    return { legivel: false };
  }
}

export interface DadosJornadaQr {
  /** Identificador lido do QR. Ausente quando o modelo não foi reconhecido (Req 1.4). */
  modeloId?: string;
  numeroSerie?: string;
  /** "qr" é o padrão; "busca" cobre a abertura sem Jornada por navegação interna. */
  origem?: "qr" | "busca";
  /** Identificador lido do QR, usado só para deduplicar (inclusive quando não reconhecido). */
  lido?: string;
}

interface RegistroJornadaQr {
  chave: string;
  jornada_id: string;
}

export const CHAVE_REGISTRO_QR = "tres.jornada_qr";
const emAndamento = new Map<string, Promise<string>>();
const armazenamentoPadrao = criarArmazenamentoSessao();

function chaveDe(dados: DadosJornadaQr): string {
  return [dados.origem ?? "qr", dados.lido ?? dados.modeloId ?? "", dados.numeroSerie ?? ""].join("|");
}

function lerRegistro(armazenamento: ArmazenamentoChaveValor): RegistroJornadaQr | null {
  try {
    const bruto = armazenamento.getItem(CHAVE_REGISTRO_QR);
    return bruto ? (JSON.parse(bruto) as RegistroJornadaQr) : null;
  } catch {
    return null;
  }
}

/**
 * Cria a Jornada de um acesso por QR (`POST /jornadas`) e guarda o `jornada_id`.
 *
 * Recarregar a página (ou o StrictMode do React) não deve abrir uma segunda
 * Jornada para o mesmo QR: chamadas simultâneas compartilham a mesma promessa e,
 * se o `sessionStorage` já tem a Jornada deste mesmo QR, ela é reutilizada.
 */
export function iniciarJornadaQr(
  dados: DadosJornadaQr,
  cliente: ClienteApi = api,
  armazenamento: ArmazenamentoChaveValor = armazenamentoPadrao,
): Promise<string> {
  const chave = chaveDe(dados);
  const pendente = emAndamento.get(chave);
  if (pendente) return pendente;

  const registro = lerRegistro(armazenamento);
  const atual = lerJornadaId(armazenamento);
  if (registro && registro.chave === chave && atual === registro.jornada_id) {
    return Promise.resolve(registro.jornada_id);
  }

  const corpo: Record<string, unknown> = { origem: dados.origem ?? "qr" };
  if (dados.modeloId) corpo.modelo_id = dados.modeloId;
  if (dados.modeloId && dados.numeroSerie) corpo.numero_serie = dados.numeroSerie;

  const promessa = cliente
    .post<{ jornada_id?: unknown }>("/jornadas", corpo)
    .then((resposta) => {
      const id = resposta?.jornada_id;
      if (typeof id !== "string" || !id) {
        throw new ErroApi("resposta", "A resposta do servidor não pôde ser lida.");
      }
      salvarJornadaId(id, armazenamento);
      try {
        armazenamento.setItem(CHAVE_REGISTRO_QR, JSON.stringify({ chave, jornada_id: id }));
      } catch {
        // Sem registro, apenas perdemos a deduplicação após recarga.
      }
      return id;
    })
    .finally(() => {
      emAndamento.delete(chave);
    });
  emAndamento.set(chave, promessa);
  return promessa;
}
