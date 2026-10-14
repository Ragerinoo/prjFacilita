import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { carregarCatalogo, selecionarModeloPorBusca } from "./catalogo";
import { criarClienteApi } from "./cliente";
import { CHAVE_JORNADA_ID, lerJornadaId } from "./jornada";

function resposta(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => sessionStorage.clear());
afterEach(() => sessionStorage.clear());

describe("carregarCatalogo", () => {
  it("devolve só modelos ativos, em ordem alfabética", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      resposta({
        modelos: [
          { modelo_id: "b", nome: "Beta", foto_url: "/b.svg" },
          { modelo_id: "x", nome: "Inativo", ativo: false },
          { modelo_id: "a", nome: "Alfa" },
          { sem: "id" },
        ],
      }),
    );
    const modelos = await carregarCatalogo(criarClienteApi({ fetchImpl }));
    expect(fetchImpl.mock.calls[0][0]).toBe("/api/pub/modelos");
    expect(modelos).toEqual([
      { modelo_id: "a", nome: "Alfa", foto_url: undefined },
      { modelo_id: "b", nome: "Beta", foto_url: "/b.svg" },
    ]);
  });
});

describe("selecionarModeloPorBusca", () => {
  it("sem Jornada, cria uma com origem 'busca' e guarda o id", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(resposta({ jornada_id: "J1" }, 201));
    const id = await selecionarModeloPorBusca("tres-circo", criarClienteApi({ fetchImpl }));
    expect(id).toBe("J1");
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("/api/pub/jornadas");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ modelo_id: "tres-circo", origem: "busca" });
    expect(lerJornadaId()).toBe("J1");
  });

  it("com Jornada existente, associa o modelo a ela", async () => {
    sessionStorage.setItem(CHAVE_JORNADA_ID, "J9");
    const fetchImpl = vi.fn().mockResolvedValue(resposta({}));
    const id = await selecionarModeloPorBusca("tres-mimo", criarClienteApi({ fetchImpl }));
    expect(id).toBe("J9");
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("/api/pub/jornadas/J9/modelo");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({ modelo_id: "tres-mimo" });
  });

  it("se o servidor não conhece a Jornada guardada, cria uma nova", async () => {
    sessionStorage.setItem(CHAVE_JORNADA_ID, "velha");
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(resposta({ erro: { codigo: "nao_encontrada" } }, 404))
      .mockResolvedValueOnce(resposta({ jornada_id: "nova" }, 201));
    expect(await selecionarModeloPorBusca("tres-mimo", criarClienteApi({ fetchImpl }))).toBe("nova");
    expect(lerJornadaId()).toBe("nova");
  });
});
