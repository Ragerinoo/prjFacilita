import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { criarArmazenamentoMemoria } from "./armazenamento";
import { ErroApi } from "./cliente";
import { CHAVE_FILA, FilaEventos } from "./filaEventos";
import { novoUlid } from "./ulid";

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("FilaEventos", () => {
  it("envia na hora, com evento_id no corpo, e esvazia a fila", async () => {
    const enviar = vi.fn().mockResolvedValue(undefined);
    const fila = new FilaEventos({ enviar, armazenamento: criarArmazenamentoMemoria() });
    const id = fila.enfileirar("/jornadas/j1/eventos", { tipo: "selecionado" });
    await vi.advanceTimersByTimeAsync(0);
    expect(enviar).toHaveBeenCalledTimes(1);
    expect(enviar.mock.calls[0][0].corpo).toEqual({ tipo: "selecionado", evento_id: id });
    expect(fila.listarPendentes()).toHaveLength(0);
  });

  it("reenvia 3 vezes a cada 5 s e depois desiste, sem lançar erro", async () => {
    const enviar = vi.fn().mockRejectedValue(new ErroApi("rede", "sem rede"));
    const armazenamento = criarArmazenamentoMemoria();
    const fila = new FilaEventos({ enviar, armazenamento });
    const falhas = vi.fn();
    fila.aoFalharDefinitivamente(falhas);
    fila.enfileirar("/jornadas/j1/eventos");
    await vi.advanceTimersByTimeAsync(0);
    expect(enviar).toHaveBeenCalledTimes(1);
    expect(armazenamento.getItem(CHAVE_FILA)).not.toBeNull();

    await vi.advanceTimersByTimeAsync(4999);
    expect(enviar).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(enviar).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(5000);
    expect(enviar).toHaveBeenCalledTimes(3);
    expect(falhas).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(5000);
    expect(enviar).toHaveBeenCalledTimes(4); // 1 envio + 3 reenvios
    expect(falhas).toHaveBeenCalledTimes(1);
    expect(fila.listarPendentes()).toHaveLength(0);
    expect(armazenamento.getItem(CHAVE_FILA)).toBeNull();

    await vi.advanceTimersByTimeAsync(20000);
    expect(enviar).toHaveBeenCalledTimes(4);
  });

  it("reenvia o mesmo evento_id e para ao ter sucesso", async () => {
    const enviar = vi
      .fn()
      .mockRejectedValueOnce(new ErroApi("timeout", "lento"))
      .mockResolvedValue(undefined);
    const fila = new FilaEventos({ enviar, armazenamento: criarArmazenamentoMemoria() });
    const id = fila.enfileirar("/jornadas/j1/avaliacao", { nota: 5 });
    await vi.advanceTimersByTimeAsync(5000);
    expect(enviar).toHaveBeenCalledTimes(2);
    expect(enviar.mock.calls[1][0].evento_id).toBe(id);
    await vi.advanceTimersByTimeAsync(20000);
    expect(enviar).toHaveBeenCalledTimes(2);
  });

  it("não reenvia quando o servidor recusa a requisição (4xx)", async () => {
    const enviar = vi.fn().mockRejectedValue(new ErroApi("http", "inválido", { status: 422 }));
    const fila = new FilaEventos({ enviar, armazenamento: criarArmazenamentoMemoria() });
    const falhas = vi.fn();
    fila.aoFalharDefinitivamente(falhas);
    fila.enfileirar("/jornadas/j1/eventos");
    await vi.advanceTimersByTimeAsync(20000);
    expect(enviar).toHaveBeenCalledTimes(1);
    expect(falhas).toHaveBeenCalledTimes(1);
  });

  it("retoma pendentes salvos depois de uma recarga", async () => {
    const armazenamento = criarArmazenamentoMemoria();
    const primeira = new FilaEventos({
      enviar: vi.fn().mockRejectedValue(new ErroApi("rede", "sem rede")),
      armazenamento,
    });
    const id = primeira.enfileirar("/jornadas/j1/eventos");
    await vi.advanceTimersByTimeAsync(0);
    primeira.parar();

    const enviar = vi.fn().mockResolvedValue(undefined);
    const segunda = new FilaEventos({ enviar, armazenamento });
    segunda.retomar();
    await vi.advanceTimersByTimeAsync(0);
    expect(enviar).toHaveBeenCalledTimes(1);
    expect(enviar.mock.calls[0][0].evento_id).toBe(id);
  });
});

describe("novoUlid", () => {
  it("gera 26 caracteres Crockford únicos", () => {
    const a = novoUlid();
    expect(a).toMatch(/^[0-9A-HJKMNP-TV-Z]{26}$/);
    expect(novoUlid()).not.toBe(a);
  });
});
