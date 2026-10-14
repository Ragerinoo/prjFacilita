import { afterEach, describe, expect, it, vi } from "vitest";
import { criarClienteApi, ErroApi } from "./cliente";

afterEach(() => {
  vi.useRealTimers();
});

function resposta(corpo: unknown, status = 200): Response {
  return new Response(corpo === undefined ? null : JSON.stringify(corpo), { status });
}

describe("cliente da API", () => {
  it("envia JSON, cabeçalhos de mutação e devolve o corpo", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(resposta({ ok: true }));
    const cliente = criarClienteApi({ fetchImpl });
    const dados = await cliente.post("/jornadas", { origem: "qr" }, { idempotencyKey: "abc" });
    expect(dados).toEqual({ ok: true });
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("/api/pub/jornadas");
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"origem":"qr"}');
    expect(init.headers["Idempotency-Key"]).toBe("abc");
    expect(init.headers["X-Requested-With"]).toBe("tres-portal");
  });

  it("converte erro padronizado do servidor em ErroApi", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(resposta({ erro: { codigo: "invalido", mensagem: "Texto inválido." } }, 422));
    const erro = await criarClienteApi({ fetchImpl })
      .get("/x")
      .catch((e: unknown) => e);
    expect(erro).toBeInstanceOf(ErroApi);
    expect(erro).toMatchObject({ tipo: "http", status: 422, codigo: "invalido", definitivo: true });
  });

  it("trata 5xx como falha que pode ser repetida", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(resposta({}, 503));
    const erro = (await criarClienteApi({ fetchImpl })
      .get("/x")
      .catch((e: unknown) => e)) as ErroApi;
    expect(erro.definitivo).toBe(false);
  });

  it("aborta e sinaliza timeout quando o servidor não responde a tempo", async () => {
    vi.useFakeTimers();
    const fetchImpl = vi.fn(
      (_url: string, init: RequestInit) =>
        new Promise<Response>((_resolve, rejeitar) => {
          init.signal?.addEventListener("abort", () => rejeitar(new DOMException("abort", "AbortError")));
        }),
    );
    const cliente = criarClienteApi({ fetchImpl: fetchImpl as unknown as typeof fetch, timeoutMs: 5000 });
    const promessa = cliente.get("/lento").catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(5000);
    expect(await promessa).toMatchObject({ tipo: "timeout" });
  });

  it("sinaliza erro de rede", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("falhou"));
    const erro = await criarClienteApi({ fetchImpl })
      .get("/x")
      .catch((e: unknown) => e);
    expect(erro).toMatchObject({ tipo: "rede" });
  });
});
