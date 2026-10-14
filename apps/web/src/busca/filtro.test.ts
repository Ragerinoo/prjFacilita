import { describe, expect, it } from "vitest";
import { buscarModelos, normalizarTexto, ordenarPorNome } from "./filtro";

const catalogo = ordenarPorNome([
  { nome: "TRES Passione" },
  { nome: "TRES Circo" },
  { nome: "Máquina Çafé" },
  { nome: "TRES Mimo" },
]);

describe("normalizarTexto", () => {
  it("remove acentos e ignora maiúsculas", () => {
    expect(normalizarTexto("MÁQUINA Çafé")).toBe("maquina cafe");
  });
});

describe("ordenarPorNome", () => {
  it("ordena em ordem alfabética sem diferenciar acento e caixa", () => {
    expect(catalogo.map((m) => m.nome)).toEqual([
      "Máquina Çafé",
      "TRES Circo",
      "TRES Mimo",
      "TRES Passione",
    ]);
  });
});

describe("buscarModelos", () => {
  it("mostra a grade completa com menos de 2 caracteres", () => {
    expect(buscarModelos(catalogo, "").modelos).toHaveLength(4);
    expect(buscarModelos(catalogo, "t").modelos).toHaveLength(4);
    expect(buscarModelos(catalogo, "  t  ").modelos).toHaveLength(4);
  });

  it("filtra por trecho do nome sem diferenciar caixa e acento, desconsiderando espaços nas pontas", () => {
    expect(buscarModelos(catalogo, "  PASSI ").modelos.map((m) => m.nome)).toEqual(["TRES Passione"]);
    expect(buscarModelos(catalogo, "maquina cafe").modelos.map((m) => m.nome)).toEqual(["Máquina Çafé"]);
    expect(buscarModelos(catalogo, "tres").modelos).toHaveLength(3);
  });

  it("sem resultado devolve a grade completa e sinaliza a mensagem", () => {
    const r = buscarModelos(catalogo, "xyz");
    expect(r.semResultado).toBe(true);
    expect(r.modelos).toHaveLength(4);
  });
});
