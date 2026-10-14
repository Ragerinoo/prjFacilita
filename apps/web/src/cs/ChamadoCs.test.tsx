import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { rotas } from "../app/rotas";
import type { CardChamado } from "./chamado/tipos";

function json(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
}

const SESSAO = { usuario: "maria", perfil: "atendente", deve_trocar_senha: false, inatividade_maxima_s: 1800 };

function cardBase(extra: Partial<CardChamado> = {}): CardChamado {
  return {
    numero: "TRES-ABC123",
    jornada_id: "j1",
    status: "aberto",
    prioridade: "P1",
    classificacao: "risco_seguranca",
    canal: "telefone",
    criado_em: "2025-01-01T12:00:00+00:00",
    responsavel: null,
    alerta_p1_visto: true,
    resposta_nao_lida: true,
    os_status: null,
    agendamento: null,
    pacote_ia_status: "ok",
    decisao_criterio: 1,
    pacote: {
      modelo: "Forno X1",
      numero_serie: "SN123",
      origem: "qr",
      categoria: "forno",
      resumo: "Cheiro de queimado no forno.",
      ja_tentado: [{ passo: "Desligar da tomada", camada: "guia", resultado: "persistiu" }],
      classificacao: "risco_seguranca",
      prioridade: "P1",
      canal_recomendado: "telefone",
      sentimento: "preocupado",
      proxima_acao: "Ligar para o consumidor",
    },
    anexos: [{ indice: 0, mime: "image/jpeg", bytes: 2048 }],
    encerramento: null,
    mensagens: [
      { ts_ulid: "01A", autor: "consumidor", texto: "Socorro, cheira a queimado", em: "2025-01-01T12:05:00+00:00", lida: false },
      { ts_ulid: "01B", autor: "atendente", texto: "Já estou vendo", em: "2025-01-01T12:06:00+00:00", lida: true },
    ],
    historico: [{ evento_id: "e1", tipo: "jornada_iniciada", em: "2025-01-01T11:55:00+00:00", dados: { origem: "qr" } }],
    ...extra,
  };
}

function simular(card: CardChamado, extras: Record<string, () => Response> = {}) {
  const fetchFalso = vi.fn(async (entrada: RequestInfo | URL, init?: RequestInit) => {
    const chave = `${init?.method ?? "GET"} ${String(entrada)}`;
    if (chave === "GET /api/cs/sessao") return json(SESSAO);
    if (chave === "GET /api/cs/chamados/TRES-ABC123") return json(card);
    const m = extras[chave];
    if (!m) throw new Error(`Requisição inesperada: ${chave}`);
    return m();
  });
  vi.stubGlobal("fetch", fetchFalso);
  return fetchFalso;
}

function renderizar() {
  const router = createMemoryRouter(rotas, { initialEntries: ["/cs/chamados/TRES-ABC123"] });
  return render(<RouterProvider router={router} />);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("card do Chamado", () => {
  it("mostra cabeçalho, Pacote, histórico e anexos sem violações de acessibilidade, e não busca dados pessoais sozinho", async () => {
    const fetchFalso = simular(cardBase());
    const { container } = renderizar();

    expect(
      await screen.findByRole("heading", { level: 1, name: "Chamado TRES-ABC123" }, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/Prioridade: P1/, undefined, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText(/Prioridade: P1/)).toBeInTheDocument();
    expect(screen.getByText(/Status: Aberto/)).toBeInTheDocument();
    expect(screen.getByText("Resposta do consumidor não lida")).toBeInTheDocument();
    expect(screen.getByText("Cheiro de queimado no forno.")).toBeInTheDocument();
    expect(screen.getByText("Forno X1")).toBeInTheDocument();
    expect(screen.getByText(/Desligar da tomada/)).toBeInTheDocument();
    expect(screen.getByText("Socorro, cheira a queimado")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Abrir foto 1" })).toBeInTheDocument();
    expect(screen.queryByText("Telefone")).not.toBeInTheDocument();
    expect(fetchFalso.mock.calls.some(([u]) => String(u).includes("dados-pessoais"))).toBe(false);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("assume o Chamado e recarrega; o botão fica desabilitado quando já há responsável", async () => {
    let assumido = false;
    const fetchFalso = vi.fn(async (entrada: RequestInfo | URL, init?: RequestInit) => {
      const chave = `${init?.method ?? "GET"} ${String(entrada)}`;
      if (chave === "GET /api/cs/sessao") return json(SESSAO);
      if (chave === "POST /api/cs/chamados/TRES-ABC123/assumir") {
        assumido = true;
        return json({ numero: "TRES-ABC123" });
      }
      if (chave === "GET /api/cs/chamados/TRES-ABC123")
        return json(
          cardBase(assumido ? { status: "em_atendimento", responsavel: { usuario: "maria", nome: "Maria" } } : {}),
        );
      throw new Error(chave);
    });
    vi.stubGlobal("fetch", fetchFalso);
    renderizar();
    await userEvent.click(await screen.findByRole("button", { name: "Assumir" }));
    expect(await screen.findByText("Assumido por Maria.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Assumir" })).toBeDisabled();
  });

  it("no conflito 409 mostra o nome de quem assumiu", async () => {
    simular(cardBase(), {
      "POST /api/cs/chamados/TRES-ABC123/assumir": () =>
        json(
          { erro: { codigo: "ja_assumido", mensagem: "Este Chamado já foi assumido por João.", responsavel: { usuario: "joao", nome: "João" } } },
          409,
        ),
    });
    renderizar();
    await userEvent.click(await screen.findByRole("button", { name: "Assumir" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Este Chamado já foi assumido por João.");
  });

  it("desabilita Assumir em Chamado encerrado", async () => {
    simular(cardBase({ status: "encerrado" }));
    renderizar();
    expect(await screen.findByRole("button", { name: "Assumir" })).toBeDisabled();
  });

  it("só mostra telefone e CEP após o clique e o sucesso", async () => {
    simular(cardBase(), {
      "GET /api/cs/chamados/TRES-ABC123/dados-pessoais": () =>
        json({ numero: "TRES-ABC123", telefone: "11999990000", cep: "01310100" }),
    });
    renderizar();
    await userEvent.click(await screen.findByRole("button", { name: "Ver dados pessoais" }));
    expect(await screen.findByText("11999990000")).toBeInTheDocument();
    expect(screen.getByText("01310100")).toBeInTheDocument();
  });

  it("com 403 log_acesso_indisponivel não mostra dados e explica o motivo", async () => {
    simular(cardBase(), {
      "GET /api/cs/chamados/TRES-ABC123/dados-pessoais": () =>
        json({ erro: { codigo: "log_acesso_indisponivel", mensagem: "x" } }, 403),
    });
    renderizar();
    await userEvent.click(await screen.findByRole("button", { name: "Ver dados pessoais" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível registrar o acesso; dados não exibidos.",
    );
    expect(screen.queryByText("Telefone")).not.toBeInTheDocument();
  });

  it("abre o anexo em nova aba só no clique", async () => {
    const abrir = vi.spyOn(window, "open").mockReturnValue(null);
    simular(cardBase(), {
      "GET /api/cs/chamados/TRES-ABC123/anexos/0": () =>
        json({ url: "https://s3.exemplo/foto?assinatura=1", expira_em_s: 60, mime: "image/jpeg" }),
    });
    renderizar();
    expect(abrir).not.toHaveBeenCalled();
    await userEvent.click(await screen.findByRole("button", { name: "Abrir foto 1" }));
    await vi.waitFor(() =>
      expect(abrir).toHaveBeenCalledWith("https://s3.exemplo/foto?assinatura=1", "_blank", "noopener,noreferrer"),
    );
  });

  it("mostra erro com Tentar novamente quando o carregamento falha", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (entrada: RequestInfo | URL) =>
        String(entrada) === "/api/cs/sessao" ? json(SESSAO) : json({ erro: { codigo: "x", mensagem: "x" } }, 404),
      ),
    );
    renderizar();
    expect(await screen.findByRole("alert")).toHaveTextContent("Chamado não encontrado.");
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });
});
