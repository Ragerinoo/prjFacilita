import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Component as MetricasCs, formatarRotulo, type RespostaMetricas } from "./MetricasCs";

function json(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
}

function metricas(extra: Partial<RespostaMetricas> = {}): RespostaMetricas {
  return {
    totais: { abertos: 3, encerrados: 2 },
    por_problema: [
      { chave: "sem_sinal", rotulo: "Sem sinal", quantidade: 4 },
      { chave: "nao_informado", rotulo: "nao_informado", quantidade: 1 },
    ],
    por_modelo: [{ chave: "tres-passione", rotulo: "Três Passione", quantidade: 5 }],
    por_prioridade: [
      { chave: "P1", rotulo: "P1", quantidade: 1 },
      { chave: "P2", rotulo: "P2", quantidade: 0 },
      { chave: "P3", rotulo: "P3", quantidade: 4 },
    ],
    por_desfecho: [
      { chave: "falso_defeito", rotulo: "falso_defeito", quantidade: 1 },
      { chave: "defeito_real", rotulo: "defeito_real", quantidade: 1 },
    ],
    ...extra,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("MetricasCs", () => {
  it("formata rótulos conhecidos e mantém os demais como vieram", () => {
    expect(formatarRotulo("nao_informado")).toBe("Não informado");
    expect(formatarRotulo("falso_defeito")).toBe("Falso defeito");
    expect(formatarRotulo("defeito_real")).toBe("Defeito real");
    expect(formatarRotulo("Sem sinal")).toBe("Sem sinal");
  });

  it("mostra o indicador de carregamento enquanto aguarda a resposta", async () => {
    let resolver: (r: Response) => void = () => {};
    const fetchFalso = vi.fn<typeof fetch>(() => new Promise<Response>((resolve) => (resolver = resolve)));
    vi.stubGlobal("fetch", fetchFalso);
    render(<MetricasCs />);

    expect(screen.getByRole("heading", { level: 1, name: "Métricas" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Carregando as métricas");
    expect(fetchFalso).toHaveBeenCalledTimes(1);
    expect(String(fetchFalso.mock.calls[0][0])).toContain("/api/cs/metricas");

    resolver(json(metricas()));
    expect(await screen.findByText("Chamados abertos")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("exibe os totais e uma tabela por dimensão com rótulo e número em texto", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(metricas())));
    const { container } = render(<MetricasCs />);

    expect(await screen.findByText("Chamados abertos")).toBeInTheDocument();
    expect(screen.getByText("Chamados abertos").nextElementSibling).toHaveTextContent("3");
    expect(screen.getByText("Chamados encerrados").nextElementSibling).toHaveTextContent("2");

    for (const titulo of ["Por problema", "Por modelo", "Por prioridade", "Por desfecho"]) {
      expect(screen.getByRole("heading", { level: 2, name: titulo })).toBeInTheDocument();
      const tabela = screen.getByRole("table", { name: titulo });
      expect(within(tabela).getAllByRole("columnheader").map((c) => c.textContent)).toEqual([
        "Rótulo",
        "Quantidade",
        "Proporção",
      ]);
    }
    expect(screen.getAllByRole("table")).toHaveLength(4);

    const problema = screen.getByRole("table", { name: "Por problema" });
    const linhasProblema = within(problema).getAllByRole("row").slice(1);
    expect(linhasProblema).toHaveLength(2);
    expect(linhasProblema[0]).toHaveTextContent("Sem sinal");
    expect(within(linhasProblema[0]).getAllByRole("cell")[1]).toHaveTextContent("4");
    expect(linhasProblema[1]).toHaveTextContent("Não informado");
    expect(within(linhasProblema[1]).getAllByRole("cell")[1]).toHaveTextContent("1");

    // Barras são decorativas: o número fica sempre em texto.
    expect(container.querySelectorAll(".metricas__barra").length).toBeGreaterThan(0);
    for (const barra of container.querySelectorAll(".metricas__barra")) {
      expect(barra).toHaveAttribute("aria-hidden", "true");
    }
    // Prioridade com quantidade zero continua listada, sem barra.
    const p2 = within(screen.getByRole("table", { name: "Por prioridade" })).getByText("P2").closest("tr")!;
    expect(within(p2).getAllByRole("cell")[1]).toHaveTextContent("0");
    expect(p2.querySelector(".metricas__barra")).toBeNull();

    expect(await axe(container)).toHaveNoViolations();
  });

  it("mostra erro com 'Tentar de novo' e carrega as métricas ao tentar outra vez", async () => {
    let falhar = true;
    const fetchFalso = vi.fn(async () =>
      falhar ? json({ erro: { codigo: "x", mensagem: "x" } }, 500) : json(metricas()),
    );
    vi.stubGlobal("fetch", fetchFalso);
    const { container } = render(<MetricasCs />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível carregar as métricas.");
    expect(screen.getByRole("heading", { level: 1, name: "Métricas" })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();

    falhar = false;
    await userEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(await screen.findByText("Chamados abertos")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(fetchFalso).toHaveBeenCalledTimes(2);
  });

  it("mostra erro quando a requisição falha na rede", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("rede"))));
    render(<MetricasCs />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível carregar as métricas.");
    expect(screen.getByRole("button", { name: "Tentar de novo" })).toBeInTheDocument();
  });

  it.each([
    ["lista vazia", []],
    ["só quantidades zero", [{ chave: "P1", rotulo: "P1", quantidade: 0 }]],
  ])("dimensão sem quantidade maior que zero (%s) mostra a mensagem e nenhuma tabela", async (_nome, linhas) => {
    vi.stubGlobal("fetch", vi.fn(async () => json(metricas({ por_modelo: linhas }))));
    const { container } = render(<MetricasCs />);

    const secao = (await screen.findByRole("heading", { level: 2, name: "Por modelo" })).closest("section")!;
    expect(within(secao).getByText("Não há chamados para esta dimensão.")).toBeInTheDocument();
    expect(within(secao).queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getAllByRole("table")).toHaveLength(3);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sem nenhum chamado, mostra totais zero e a mensagem em todas as dimensões", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json({
          totais: { abertos: 0, encerrados: 0 },
          por_problema: [],
          por_modelo: [],
          por_prioridade: [
            { chave: "P1", rotulo: "P1", quantidade: 0 },
            { chave: "P2", rotulo: "P2", quantidade: 0 },
            { chave: "P3", rotulo: "P3", quantidade: 0 },
          ],
          por_desfecho: [
            { chave: "falso_defeito", rotulo: "falso_defeito", quantidade: 0 },
            { chave: "defeito_real", rotulo: "defeito_real", quantidade: 0 },
          ],
        }),
      ),
    );
    const { container } = render(<MetricasCs />);

    expect(await screen.findByText("Chamados abertos")).toBeInTheDocument();
    expect(screen.getByText("Chamados abertos").nextElementSibling).toHaveTextContent("0");
    expect(screen.getByText("Chamados encerrados").nextElementSibling).toHaveTextContent("0");
    expect(screen.getAllByText("Não há chamados para esta dimensão.")).toHaveLength(4);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it.each([
    {
      nome: "nao_informado em problema",
      dimensao: "por_problema" as const,
      titulo: "Por problema",
      linhas: [
        { chave: "nao_informado", rotulo: "nao_informado", quantidade: 7 },
        { chave: "wifi", rotulo: "Wi-Fi instável", quantidade: 2 },
      ],
      esperados: [
        ["Não informado", "7"],
        ["Wi-Fi instável", "2"],
      ],
    },
    {
      nome: "nao_informado em modelo",
      dimensao: "por_modelo" as const,
      titulo: "Por modelo",
      linhas: [{ chave: "nao_informado", rotulo: "nao_informado", quantidade: 3 }],
      esperados: [["Não informado", "3"]],
    },
    {
      nome: "falso_defeito e defeito_real em desfecho",
      dimensao: "por_desfecho" as const,
      titulo: "Por desfecho",
      linhas: [
        { chave: "falso_defeito", rotulo: "falso_defeito", quantidade: 5 },
        { chave: "defeito_real", rotulo: "defeito_real", quantidade: 0 },
      ],
      esperados: [
        ["Falso defeito", "5"],
        ["Defeito real", "0"],
      ],
    },
    {
      nome: "prioridades com zero",
      dimensao: "por_prioridade" as const,
      titulo: "Por prioridade",
      linhas: [
        { chave: "P1", rotulo: "P1", quantidade: 0 },
        { chave: "P2", rotulo: "P2", quantidade: 12 },
        { chave: "P3", rotulo: "P3", quantidade: 6 },
      ],
      esperados: [
        ["P1", "0"],
        ["P2", "12"],
        ["P3", "6"],
      ],
    },
  ])("exibe rótulo e quantidade em texto: $nome", async ({ dimensao, titulo, linhas, esperados }) => {
    vi.stubGlobal("fetch", vi.fn(async () => json(metricas({ [dimensao]: linhas }))));
    const { container } = render(<MetricasCs />);

    const tabela = await screen.findByRole("table", { name: titulo });
    const corpo = within(tabela).getAllByRole("row").slice(1);
    expect(corpo).toHaveLength(esperados.length);
    esperados.forEach(([rotulo, quantidade], i) => {
      const celulas = within(corpo[i]).getAllByRole("cell");
      expect(celulas[0]).toHaveTextContent(rotulo);
      expect(celulas[1]).toHaveTextContent(quantidade);
    });
    expect(tabela).not.toHaveTextContent("nao_informado");
    expect(tabela).not.toHaveTextContent("falso_defeito");
    expect(tabela).not.toHaveTextContent("defeito_real");
    expect(await axe(container)).toHaveNoViolations();
  });
});
