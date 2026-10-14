import { describe, expect, it } from "vitest";
import { interpretarQr } from "./qr";

const consulta = (texto = "") => new URLSearchParams(texto);

describe("interpretarQr", () => {
  it("aceita modelo em slug e série alfanumérica de 1 a 30 caracteres", () => {
    expect(interpretarQr("tres-passione", consulta("s=ABC123"))).toEqual({
      legivel: true,
      modeloId: "tres-passione",
      numeroSerie: "ABC123",
    });
    expect(interpretarQr("m1", consulta(`s=${"a".repeat(30)}`))).toMatchObject({ numeroSerie: "a".repeat(30) });
  });

  it.each([[""], ["a".repeat(31)], ["AB-1"], ["AB 1"], ["çedilha"]])(
    "descarta a série inválida %j sem invalidar o modelo",
    (serie) => {
      expect(interpretarQr("tres-passione", consulta(new URLSearchParams({ s: serie }).toString()))).toEqual({
        legivel: true,
        modeloId: "tres-passione",
        numeroSerie: undefined,
      });
    },
  );

  it("sem série, o modelo segue legível", () => {
    expect(interpretarQr("tres-passione", consulta())).toMatchObject({ legivel: true, numeroSerie: undefined });
    expect(interpretarQr("tres-passione", null)).toMatchObject({ legivel: true });
  });

  it("usa o primeiro valor de `s`, como o domínio", () => {
    expect(interpretarQr("m", consulta("s=ABC&s=DEF"))).toMatchObject({ numeroSerie: "ABC" });
  });

  it.each([[undefined], [null], [42], [""], ["TRES"], ["tres_passione"], ["-tres"], ["tres-"], ["tres--x"], ["a b"], ["a".repeat(65)]])(
    "trata o modelo %j como não legível",
    (modelo) => {
      expect(interpretarQr(modelo, consulta("s=ABC"))).toEqual({ legivel: false });
    },
  );
});
