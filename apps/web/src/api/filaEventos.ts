import { criarArmazenamentoSessao, type ArmazenamentoChaveValor } from "./armazenamento";
import { api, ErroApi } from "./cliente";
import { novoUlid } from "./ulid";

/**
 * Fila local de eventos com reenvio (Req 3.12 e 5.7).
 *
 * - Cada evento recebe um `evento_id` (ULID), enviado no corpo e em
 *   `Idempotency-Key`, para o servidor ignorar duplicatas.
 * - Se o envio falhar, o evento é retido e reenviado até 3 vezes, a cada 5 s.
 * - O envio nunca lança e nunca bloqueia o chamador: o fluxo do Consumidor
 *   segue sem mensagem de erro. Quem precisa avisar (por exemplo, a avaliação
 *   do Req 5.7) assina `aoFalharDefinitivamente`.
 * - Pendentes ficam no `sessionStorage` e são retomados após recarga.
 */
export const INTERVALO_REENVIO_MS = 5000;
export const MAX_REENVIOS = 3;
export const CHAVE_FILA = "tres.eventos_pendentes";

export interface EventoPendente {
  evento_id: string;
  metodo: "POST" | "PUT";
  caminho: string;
  corpo: Record<string, unknown> & { evento_id: string };
  /** Quantidade de reenvios já realizados (o primeiro envio não conta). */
  reenvios: number;
}

export type EnviarEvento = (evento: EventoPendente) => Promise<void>;

export interface OpcoesFila {
  enviar?: EnviarEvento;
  armazenamento?: ArmazenamentoChaveValor;
  intervaloMs?: number;
  maxReenvios?: number;
  gerarId?: () => string;
}

const enviarPelaApi: EnviarEvento = async (evento) => {
  await api.requisitar(evento.caminho, {
    metodo: evento.metodo,
    corpo: evento.corpo,
    idempotencyKey: evento.evento_id,
  });
};

export class FilaEventos {
  private readonly enviar: EnviarEvento;
  private readonly armazenamento: ArmazenamentoChaveValor;
  private readonly intervaloMs: number;
  private readonly maxReenvios: number;
  private readonly gerarId: () => string;
  private readonly pendentes = new Map<string, EventoPendente>();
  private readonly temporizadores = new Map<string, ReturnType<typeof setTimeout>>();
  private readonly emVoo = new Set<string>();
  private readonly ouvintesFalha = new Set<(evento: EventoPendente) => void>();
  private readonly ouvintesSucesso = new Set<(evento: EventoPendente) => void>();

  constructor(opcoes: OpcoesFila = {}) {
    this.enviar = opcoes.enviar ?? enviarPelaApi;
    this.armazenamento = opcoes.armazenamento ?? criarArmazenamentoSessao();
    this.intervaloMs = opcoes.intervaloMs ?? INTERVALO_REENVIO_MS;
    this.maxReenvios = opcoes.maxReenvios ?? MAX_REENVIOS;
    this.gerarId = opcoes.gerarId ?? novoUlid;
  }

  /** Registra o evento e tenta enviá-lo na hora. Devolve o `evento_id`. */
  enfileirar(
    caminho: string,
    corpo: Record<string, unknown> = {},
    metodo: "POST" | "PUT" = "POST",
  ): string {
    const evento_id = this.gerarId();
    const evento: EventoPendente = {
      evento_id,
      metodo,
      caminho,
      corpo: { ...corpo, evento_id },
      reenvios: 0,
    };
    this.pendentes.set(evento_id, evento);
    this.persistir();
    void this.tentar(evento);
    return evento_id;
  }

  /** Retoma os pendentes salvos (por exemplo, depois de recarregar a página). */
  retomar(): void {
    for (const evento of this.lerSalvos()) {
      if (this.pendentes.has(evento.evento_id)) continue;
      this.pendentes.set(evento.evento_id, evento);
      void this.tentar(evento);
    }
  }

  listarPendentes(): EventoPendente[] {
    return [...this.pendentes.values()];
  }

  aoFalharDefinitivamente(ouvinte: (evento: EventoPendente) => void): () => void {
    this.ouvintesFalha.add(ouvinte);
    return () => this.ouvintesFalha.delete(ouvinte);
  }

  aoEnviar(ouvinte: (evento: EventoPendente) => void): () => void {
    this.ouvintesSucesso.add(ouvinte);
    return () => this.ouvintesSucesso.delete(ouvinte);
  }

  /** Cancela os temporizadores (os pendentes continuam salvos para `retomar`). */
  parar(): void {
    for (const t of this.temporizadores.values()) clearTimeout(t);
    this.temporizadores.clear();
  }

  private async tentar(evento: EventoPendente): Promise<void> {
    if (this.emVoo.has(evento.evento_id)) return;
    this.emVoo.add(evento.evento_id);
    try {
      await this.enviar(evento);
      this.concluir(evento, this.ouvintesSucesso);
    } catch (erro) {
      const definitivo = erro instanceof ErroApi && erro.definitivo;
      if (definitivo || evento.reenvios >= this.maxReenvios) {
        this.concluir(evento, this.ouvintesFalha);
      } else {
        this.agendarReenvio(evento);
      }
    } finally {
      this.emVoo.delete(evento.evento_id);
    }
  }

  private agendarReenvio(evento: EventoPendente): void {
    const temporizador = setTimeout(() => {
      this.temporizadores.delete(evento.evento_id);
      evento.reenvios += 1;
      this.persistir();
      void this.tentar(evento);
    }, this.intervaloMs);
    this.temporizadores.set(evento.evento_id, temporizador);
  }

  private concluir(evento: EventoPendente, ouvintes: Set<(e: EventoPendente) => void>): void {
    this.pendentes.delete(evento.evento_id);
    this.persistir();
    for (const ouvinte of ouvintes) {
      try {
        ouvinte(evento);
      } catch {
        // Um ouvinte com defeito não pode interromper a fila.
      }
    }
  }

  private persistir(): void {
    try {
      if (this.pendentes.size === 0) this.armazenamento.removeItem(CHAVE_FILA);
      else this.armazenamento.setItem(CHAVE_FILA, JSON.stringify(this.listarPendentes()));
    } catch {
      // Sem persistência a fila continua funcionando em memória.
    }
  }

  private lerSalvos(): EventoPendente[] {
    try {
      const bruto = this.armazenamento.getItem(CHAVE_FILA);
      if (!bruto) return [];
      const dados: unknown = JSON.parse(bruto);
      return Array.isArray(dados) ? (dados as EventoPendente[]) : [];
    } catch {
      return [];
    }
  }
}

/** Fila padrão do Portal. */
export const filaEventos = new FilaEventos();
