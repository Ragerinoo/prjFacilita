import { describe, expect, it } from "vitest";
import {
  MENSAGEM_FOTO_FORMATO,
  MENSAGEM_FOTO_LIMITE,
  MENSAGEM_FOTO_TAMANHO,
  motivoFotoRejeitada,
  validarCep,
  validarTelefone,
} from "./validacaoContato";

describe("validarTelefone", () => {
  it.each(["1133334444", "11912345678", "(11) 91234-5678", " 11 3333-4444 "])("aceita %s", (v) => {
    expect(validarTelefone(v)).toBe(true);
  });
  it.each(["", "113333444", "119123456789", "11a12345678", "+5511912345678", "11.91234.5678"])("recusa %s", (v) => {
    expect(validarTelefone(v)).toBe(false);
  });
});

describe("validarCep", () => {
  it.each(["01310100", "01310-100", " 01310 100"])("aceita %s", (v) => {
    expect(validarCep(v)).toBe(true);
  });
  it.each(["", "0131010", "013101000", "0131x-100", "01.310-100"])("recusa %s", (v) => {
    expect(validarCep(v)).toBe(false);
  });
});

describe("motivoFotoRejeitada", () => {
  const MB = 1024 * 1024;
  it("aceita JPEG e PNG de até 5 MB com menos de 3 fotos", () => {
    expect(motivoFotoRejeitada("image/jpeg", 5 * MB, 2)).toBeNull();
    expect(motivoFotoRejeitada("image/png", 1, 0)).toBeNull();
  });
  it("recusa por formato, tamanho e limite, nesta ordem", () => {
    expect(motivoFotoRejeitada("image/gif", 1, 0)).toBe(MENSAGEM_FOTO_FORMATO);
    expect(motivoFotoRejeitada("image/png", 5 * MB + 1, 0)).toBe(MENSAGEM_FOTO_TAMANHO);
    expect(motivoFotoRejeitada("image/png", 1, 3)).toBe(MENSAGEM_FOTO_LIMITE);
    expect(motivoFotoRejeitada("image/gif", 6 * MB, 3)).toBe(MENSAGEM_FOTO_FORMATO);
  });
});
