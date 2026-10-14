import { describe, expect, it, vi } from "vitest";
import { criarClienteApi } from "./cliente";
import { carregarInstrucao, lerNumeroChamado } from "./instrucao";

function cliente(resposta: () => Response) {
  const fetchImpl = vi.fn(async () => resposta()) as unknown as typeof fetch;
  return { api: criarClienteApi({ baseUrl: "/api/pub", fetchImpl }), fetchImpl };
}
const json = (corpo: unknown, status = 200) =>
  new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });

describe("carregarInstrucao", () => {
  it("ordena os passos por n, aceita o formato do seed e completa o texto equivalente", async () => {
    const { api, fetchImpl } = cliente(() =>
      json({
        problema_id: 1,
        variante: "padrao",
        passos: [
          { n: 2, texto: "B", alt: "b", midia_url: "/b.svg", midia_tipo: "animação" },
          { n: 1, texto: "A", alt: "a", texto_equivalente: "Passo 1: A", midia_tipo: "imagem" },
        ],
      }),
    );
    const instrucao = await carregarInstrucao("J 1", 1, "externo", api);
    expect(instrucao?.passos.map((p) => p.n)).toEqual([1, 2]);
    expect(instrucao?.passos[1]).toMatchObject({ texto_equivalente: "B", midia_tipo: "animacao" });
    expect(vi.mocked(fetchImpl).mock.calls[0]?.[0]).toBe("/api/pub/jornadas/J%201/instrucao?problema_id=1&variante=externo");
  });

  it("devolve null para 404 e para lista de passos vazia", async () => {
    expect(await carregarInstrucao("J1", 3, undefined, cliente(() => json({ erro: { codigo: "x", mensagem: "y" } }, 404)).api)).toBeNull();
    expect(await carregarInstrucao("J1", 3, undefined, cliente(() => json({ passos: [] })).api)).toBeNull();
  });

  it("lança erro para falhas do servidor", async () => {
    await expect(
      carregarInstrucao("J1", 3, undefined, cliente(() => json({ erro: { codigo: "x", mensagem: "y" } }, 500)).api),
    ).rejects.toMatchObject({ tipo: "http", status: 500 });
  });
});

describe("lerNumeroChamado", () => {
  it.each([
    [{ numero: "TRES-1" }, "TRES-1"],
    [{ chamado: { numero: 42 } }, "42"],
    [{ numero_chamado: "X9" }, "X9"],
    [{}, undefined],
    [null, undefined],
  ])("lê o número de %j", (resposta, esperado) => {
    expect(lerNumeroChamado(resposta)).toBe(esperado);
  });
});
