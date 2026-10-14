import { describe, expect, it, vi } from "vitest";
import { criarArmazenamentoMemoria } from "../api/armazenamento";
import { criarClienteApi } from "../api/cliente";
import { CHAVE_RISCO, criarArmazemRisco } from "./armazemRisco";

const marcada = (extra: Record<string, unknown> = {}, jornadaId = "J1") => ({
  jornada: {
    jornada_id: jornadaId,
    estado: "escalada",
    risco: { marcado: true, origem: "lista", em: "2025-01-01T12:00:00Z" },
    ...extra,
  },
});
const semRisco = (jornadaId = "J1", estado = "ativa") => ({
  jornada: { jornada_id: jornadaId, estado, risco: { marcado: false } },
});

describe("armazém de risco", () => {
  it("ativa o alerta quando o servidor marca o risco e guarda só uma cópia no sessionStorage", () => {
    const memoria = criarArmazenamentoMemoria();
    const armazem = criarArmazemRisco(memoria);
    armazem.registrarRespostaServidor(marcada({ contato_cs: "confirmado" }));
    expect(armazem.obter()).toMatchObject({ ativo: true, jornadaId: "J1", origem: "lista", contato: "confirmado" });
    expect(JSON.parse(memoria.getItem(CHAVE_RISCO) ?? "null")).toMatchObject({ jornadaId: "J1", ativo: true });
  });

  it("restaura o alerta do cache depois de uma recarga", () => {
    const memoria = criarArmazenamentoMemoria();
    criarArmazemRisco(memoria).registrarRespostaServidor(marcada());
    expect(criarArmazemRisco(memoria).obter()).toMatchObject({ ativo: true, jornadaId: "J1", contato: "pendente" });
  });

  it("ignora cache corrompido", () => {
    const memoria = criarArmazenamentoMemoria();
    memoria.setItem(CHAVE_RISCO, "{não é json");
    expect(criarArmazemRisco(memoria).obter().ativo).toBe(false);
  });

  it("nunca desfaz o risco na mesma Jornada, nem com resposta atrasada sem risco", () => {
    const armazem = criarArmazemRisco(criarArmazenamentoMemoria());
    armazem.registrarRespostaServidor(marcada());
    armazem.registrarRespostaServidor(semRisco());
    armazem.registrarRespostaServidor({ jornada: { jornada_id: "J1", estado: "ativa" } });
    expect(armazem.obter().ativo).toBe(true);
  });

  it("mantém 'confirmado' e a primeira origem, mesmo que outra origem marque depois", () => {
    const armazem = criarArmazemRisco(criarArmazenamentoMemoria());
    armazem.registrarRespostaServidor(marcada({ contato_cs: "confirmado" }));
    armazem.registrarRespostaServidor({
      jornada: { jornada_id: "J1", estado: "escalada", risco: { marcado: true, origem: "ia" }, contato_cs: "pendente" },
    });
    expect(armazem.obter()).toMatchObject({ contato: "confirmado", origem: "lista", em: "2025-01-01T12:00:00Z" });
  });

  it("só o encerramento da Jornada remove o alerta, e resposta atrasada não o reativa", () => {
    const armazem = criarArmazemRisco(criarArmazenamentoMemoria());
    armazem.registrarRespostaServidor(marcada());
    armazem.registrarRespostaServidor(semRisco("J1", "encerrada_humano"));
    expect(armazem.obter().ativo).toBe(false);
    armazem.registrarRespostaServidor(marcada());
    expect(armazem.obter().ativo).toBe(false);
  });

  it("encerramento de outra Jornada não derruba o alerta atual", () => {
    const armazem = criarArmazemRisco(criarArmazenamentoMemoria());
    armazem.registrarRespostaServidor(marcada());
    armazem.registrarRespostaServidor(semRisco("OUTRA", "abandonada"));
    expect(armazem.obter()).toMatchObject({ ativo: true, jornadaId: "J1" });
  });

  it("ignora corpos fora do contrato", () => {
    const armazem = criarArmazemRisco(criarArmazenamentoMemoria());
    const ouvinte = vi.fn();
    armazem.assinar(ouvinte);
    for (const corpo of [null, undefined, "x", 3, [], {}, { jornada: "x" }, { jornada: { risco: { marcado: true } } }]) {
      armazem.registrarRespostaServidor(corpo);
    }
    expect(armazem.obter().ativo).toBe(false);
    expect(ouvinte).not.toHaveBeenCalled();
  });

  it("notifica quem assina somente quando o estado muda", () => {
    const armazem = criarArmazemRisco(criarArmazenamentoMemoria());
    const ouvinte = vi.fn();
    const cancelar = armazem.assinar(ouvinte);
    armazem.registrarRespostaServidor(marcada());
    armazem.registrarRespostaServidor(marcada());
    expect(ouvinte).toHaveBeenCalledTimes(1);
    cancelar();
    armazem.registrarRespostaServidor(marcada({ contato_cs: "confirmado" }));
    expect(ouvinte).toHaveBeenCalledTimes(1);
  });

  it("recebe o envelope por meio do cliente HTTP, em respostas de sucesso e de erro", async () => {
    const armazem = criarArmazemRisco(criarArmazenamentoMemoria());
    const respostas = [
      new Response(JSON.stringify(marcada()), { status: 200 }),
      new Response(JSON.stringify({ erro: { codigo: "x", mensagem: "falhou" }, ...marcada({ contato_cs: "nao_registrado" }) }), {
        status: 503,
      }),
    ];
    const fetchImpl = vi.fn(async () => respostas.shift() as Response);
    const cliente = criarClienteApi({ fetchImpl, aoResponder: armazem.registrarRespostaServidor });
    await cliente.get("/jornadas/J1");
    expect(armazem.obter()).toMatchObject({ ativo: true, contato: "pendente" });
    await cliente.post("/jornadas/J1/escalar", {}).catch(() => undefined);
    expect(armazem.obter().contato).toBe("nao_registrado");
  });
});
