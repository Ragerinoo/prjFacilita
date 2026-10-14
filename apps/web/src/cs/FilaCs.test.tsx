import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Component as FilaCs, formatarEspera, INTERVALO_FILA_MS, type ItemFila } from "./FilaCs";

function json(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
}

function item(extra: Partial<ItemFila> = {}): ItemFila {
  return {
    numero: "TRES-0001",
    prioridade: "P3",
    classificacao: "Instalação",
    status: "aguardando_atendimento",
    responsavel: null,
    tempo_espera_s: 300,
    criado_em: "2025-01-01T10:00:00Z",
    alerta_p1: false,
    alerta_p1_visto: false,
    resposta_nao_lida: false,
    resumo: "Cliente sem sinal",
    ...extra,
  };
}

function renderizar() {
  return render(
    <MemoryRouter>
      <FilaCs />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("FilaCs", () => {
  it("formata o tempo de espera", () => {
    expect(formatarEspera(45)).toBe("45 s");
    expect(formatarEspera(300)).toBe("5 min");
    expect(formatarEspera(7500)).toBe("2 h 05 min");
  });

  it("lista na ordem do servidor com prioridade em texto, espera, responsável, não lida, link e alerta P1", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json({
          itens: [
            item({ numero: "TRES-0009", prioridade: "P1", alerta_p1: true, tempo_espera_s: 90 }),
            item({
              numero: "TRES-0002",
              prioridade: "P2",
              responsavel: { usuario: "maria", nome: "Maria Souza" },
              resposta_nao_lida: true,
            }),
            item({ numero: "TRES-0001" }),
          ],
        }),
      ),
    );
    const { container } = renderizar();

    const lista = await screen.findByRole("list", { name: "Chamados na fila" });
    const linhas = lista.querySelectorAll("li");
    expect(linhas).toHaveLength(3);
    expect(linhas[0]).toHaveTextContent("P1 · Urgente");
    expect(linhas[0]).toHaveTextContent("TRES-0009");
    expect(linhas[0]).toHaveTextContent("Espera: 1 min");
    expect(linhas[1]).toHaveTextContent("Responsável: Maria Souza");
    expect(linhas[1]).toHaveTextContent("Resposta não lida");
    expect(linhas[2]).toHaveTextContent("Responsável: Sem responsável");
    expect(linhas[2]).not.toHaveTextContent("Resposta não lida");

    expect(linhas[0].querySelector("a")).toHaveAttribute("href", "/cs/chamados/TRES-0009");
    expect(screen.getByRole("alert")).toHaveTextContent("1 chamado P1");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sem P1 não visto, não mostra o alerta; sem itens, mostra o estado vazio", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ itens: [] })));
    renderizar();
    expect(await screen.findByText("Não há chamados na fila no momento.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("mostra erro com 'Tentar de novo' quando a carga inicial falha e recupera ao tentar", async () => {
    let falhar = true;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => (falhar ? json({ erro: { codigo: "x", mensagem: "x" } }, 500) : json({ itens: [item()] }))),
    );
    const { container } = renderizar();
    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível carregar a fila de chamados.");
    expect(await axe(container)).toHaveNoViolations();

    falhar = false;
    await userEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(await screen.findByText("TRES-0001")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("atualiza a cada intervalo, mantém os últimos dados se uma atualização falha e pausa quando a página está oculta", async () => {
    vi.useFakeTimers();
    let modo: "ok" | "falha" = "ok";
    let numero = "TRES-0001";
    const fetchFalso = vi.fn(async () => (modo === "ok" ? json({ itens: [item({ numero })] }) : json({}, 500)));
    vi.stubGlobal("fetch", fetchFalso);
    renderizar();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText("TRES-0001")).toBeInTheDocument();
    expect(fetchFalso).toHaveBeenCalledTimes(1);

    numero = "TRES-0002";
    await act(async () => {
      await vi.advanceTimersByTimeAsync(INTERVALO_FILA_MS);
    });
    expect(fetchFalso).toHaveBeenCalledTimes(2);
    expect(screen.getByText("TRES-0002")).toBeInTheDocument();

    modo = "falha";
    await act(async () => {
      await vi.advanceTimersByTimeAsync(INTERVALO_FILA_MS);
    });
    expect(fetchFalso).toHaveBeenCalledTimes(3);
    expect(screen.getByText("TRES-0002")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Não foi possível atualizar a fila");

    const visibilidade = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
      await vi.advanceTimersByTimeAsync(INTERVALO_FILA_MS * 3);
    });
    expect(fetchFalso).toHaveBeenCalledTimes(3);

    modo = "ok";
    visibilidade.mockReturnValue("visible");
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetchFalso).toHaveBeenCalledTimes(4);
    visibilidade.mockRestore();
  });
});
