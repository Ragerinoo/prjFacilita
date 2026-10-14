import { afterEach, describe, expect, it } from "vitest";
import {
  CHAVE_JORNADA_ID,
  lerJornadaId,
  lerRascunho,
  limparJornadaId,
  salvarJornadaId,
  salvarRascunho,
} from "./jornada";

afterEach(() => {
  window.sessionStorage.clear();
});

describe("jornada_id e rascunhos no sessionStorage", () => {
  it("guarda e recupera o jornada_id usando o sessionStorage", () => {
    expect(lerJornadaId()).toBeNull();
    salvarJornadaId("01JORNADA");
    expect(window.sessionStorage.getItem(CHAVE_JORNADA_ID)).toBe("01JORNADA");
    expect(lerJornadaId()).toBe("01JORNADA");
    limparJornadaId();
    expect(lerJornadaId()).toBeNull();
  });

  it("guarda rascunhos como JSON", () => {
    salvarRascunho("avaliacao", { nota: 4, comentario: "ok" });
    expect(lerRascunho("avaliacao")).toEqual({ nota: 4, comentario: "ok" });
    expect(lerRascunho("inexistente")).toBeNull();
  });
});
