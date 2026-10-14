import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { rotas } from "../app/rotas";
import { apiCs } from "./clienteCs";
import { AVISO_SESSAO_EXPIRADA, MENSAGEM_CREDENCIAIS } from "./LoginCs";
import type { RespostaMetricas } from "./MetricasCs";

const MENSAGEM_BLOQUEIO =
  "Acesso temporariamente bloqueado por excesso de tentativas. Tente de novo em 12 minutos.";

function json(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
}

function sessaoDe(perfil: "atendente" | "gestor", usuario = "maria") {
  return { usuario, perfil, deve_trocar_senha: false, inatividade_maxima_s: 1800 };
}

const SEM_SESSAO = () => json({ erro: { codigo: "nao_autenticado", mensagem: "É preciso entrar." } }, 401);

type Manipulador = (url: string, init?: RequestInit) => Response | Promise<Response>;

function simular(manipuladores: Record<string, Manipulador>) {
  const fetchFalso = vi.fn(async (entrada: RequestInfo | URL, init?: RequestInit) => {
    const url = String(entrada);
    const chave = `${init?.method ?? "GET"} ${url}`;
    const manipulador = manipuladores[chave];
    if (!manipulador) throw new Error(`Requisição inesperada: ${chave}`);
    return manipulador(url, init);
  });
  vi.stubGlobal("fetch", fetchFalso);
  return fetchFalso;
}

function renderizar(caminho: string) {
  const router = createMemoryRouter(rotas, { initialEntries: [caminho] });
  const resultado = render(<RouterProvider router={router} />);
  return { ...resultado, router };
}

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  localStorage.clear();
});

describe("login e guarda de rotas do Painel_CS", () => {
  it("sem sessão, qualquer rota do Painel leva ao login sem mostrar dados e sem violações de acessibilidade", async () => {
    simular({ "GET /api/cs/sessao": SEM_SESSAO });
    const { container, router } = renderizar("/cs/chamados/TRES-ABC");
    expect(await screen.findByRole("heading", { level: 1, name: "Entrar no painel de atendimento" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/cs/login");
    expect(screen.queryByText(/TRES-ABC/)).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Senha")).toHaveAttribute("type", "password");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("mostra a mesma mensagem de erro para credenciais inválidas, limpa a senha e não guarda nada no navegador", async () => {
    const fetchFalso = simular({
      "GET /api/cs/sessao": SEM_SESSAO,
      "POST /api/cs/login": () =>
        json({ erro: { codigo: "credenciais_invalidas", mensagem: "texto qualquer do servidor" } }, 401),
    });
    renderizar("/cs/login");
    await userEvent.type(await screen.findByLabelText("Usuário"), "maria");
    await userEvent.type(screen.getByLabelText("Senha"), "segredo-123");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(MENSAGEM_CREDENCIAIS);
    expect(screen.getByLabelText("Senha")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Entrar" })).toBeEnabled();
    expect(JSON.stringify({ ...sessionStorage, ...localStorage })).not.toContain("segredo-123");

    const chamada = fetchFalso.mock.calls.find(([url]) => String(url).endsWith("/login"));
    const init = chamada?.[1] as RequestInit;
    expect((init.headers as Record<string, string>)["X-Requested-With"]).toBeTruthy();
    expect(init.credentials).toBe("same-origin");
    expect(JSON.parse(String(init.body))).toEqual({ usuario: "maria", senha: "segredo-123" });
  });

  it("desabilita o botão enquanto envia e mostra a mensagem de bloqueio temporário com os minutos do servidor", async () => {
    let responder: (r: Response) => void = () => undefined;
    simular({
      "GET /api/cs/sessao": SEM_SESSAO,
      "POST /api/cs/login": () => new Promise<Response>((resolver) => (responder = resolver)),
    });
    renderizar("/cs/login");
    await userEvent.type(await screen.findByLabelText("Usuário"), "maria");
    await userEvent.type(screen.getByLabelText("Senha"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    const botao = await screen.findByRole("button", { name: "Entrando…" });
    expect(botao).toBeDisabled();

    await act(async () => {
      responder(json({ erro: { codigo: "login_bloqueado", mensagem: MENSAGEM_BLOQUEIO } }, 429));
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(MENSAGEM_BLOQUEIO);
    expect(screen.getByRole("button", { name: "Entrar" })).toBeEnabled();
  });

  it("não chama a API quando usuário ou senha estão vazios", async () => {
    const fetchFalso = simular({ "GET /api/cs/sessao": SEM_SESSAO });
    renderizar("/cs/login");
    await userEvent.click(await screen.findByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Informe o usuário e a senha.");
    expect(fetchFalso).toHaveBeenCalledTimes(1);
  });

  it("entra como Atendente: mostra usuário e perfil, esconde Métricas e volta ao login ao sair", async () => {
    let logado = false;
    simular({
      "GET /api/cs/sessao": () => (logado ? json(sessaoDe("atendente")) : SEM_SESSAO()),
      "POST /api/cs/login": () => {
        logado = true;
        return json(sessaoDe("atendente"));
      },
      "POST /api/cs/logout": () => {
        logado = false;
        return new Response(null, { status: 204 });
      },
    });
    const { container, router } = renderizar("/cs/fila");
    await userEvent.type(await screen.findByLabelText("Usuário"), "maria");
    await userEvent.type(screen.getByLabelText("Senha"), "segredo");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Fila de chamados" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/cs/fila"); // volta para onde queria ir
    expect(screen.getByText("maria")).toBeInTheDocument();
    expect(screen.getByText("(Atendente)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Fila de chamados" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Métricas" })).not.toBeInTheDocument();
    // O Painel tem layout próprio: sem o alerta de risco nem o rodapé do Portal.
    expect(screen.queryByRole("link", { name: "Aviso de privacidade" })).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();

    await userEvent.click(screen.getByRole("button", { name: "Sair" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Entrar no painel de atendimento" })).toBeInTheDocument();
    expect(screen.queryByText("maria")).not.toBeInTheDocument();
  });

  it("Atendente que digita /cs/metricas vê acesso negado, sem dados de métricas", async () => {
    // Sem handler de /api/cs/metricas: qualquer chamada a ela falharia o teste (requisição inesperada).
    const fetchFalso = simular({ "GET /api/cs/sessao": () => json(sessaoDe("atendente")) });
    const { container } = renderizar("/cs/metricas");
    expect(await screen.findByRole("heading", { level: 1, name: "Acesso negado" })).toBeInTheDocument();
    expect(fetchFalso.mock.calls.some(([url]) => String(url).includes("/metricas"))).toBe(false);
    expect(screen.queryByRole("heading", { name: "Métricas" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Métricas" })).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("Gestor vê o link e a página de Métricas, carregada de GET /api/cs/metricas", async () => {
    const metricas: RespostaMetricas = {
      totais: { abertos: 2, encerrados: 1 },
      por_problema: [{ chave: "nao_liga", rotulo: "Não liga", quantidade: 3 }],
      por_modelo: [{ chave: "TRES-1", rotulo: "TRES-1", quantidade: 3 }],
      por_prioridade: [{ chave: "alta", rotulo: "Alta", quantidade: 3 }],
      por_desfecho: [{ chave: "nao_informado", rotulo: "nao_informado", quantidade: 3 }],
    };
    const fetchFalso = simular({
      "GET /api/cs/sessao": () => json(sessaoDe("gestor", "joao")),
      "GET /api/cs/metricas": () => json(metricas),
    });
    renderizar("/cs/metricas");
    expect(await screen.findByRole("heading", { level: 1, name: "Métricas" })).toBeInTheDocument();
    expect(screen.getByText("(Gestor)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Métricas" })).toBeInTheDocument();
    expect(await screen.findByText("Chamados abertos")).toBeInTheDocument();
    expect(fetchFalso.mock.calls.some(([url]) => String(url) === "/api/cs/metricas")).toBe(true);
  });

  it("um 401 em qualquer chamada volta ao login com o aviso de sessão expirada, sem dados anteriores", async () => {
    simular({
      "GET /api/cs/sessao": () => json(sessaoDe("atendente")),
      "GET /api/cs/fila": SEM_SESSAO,
    });
    const { router } = renderizar("/cs/fila");
    await screen.findByRole("heading", { level: 1, name: "Fila de chamados" });

    await act(async () => {
      await apiCs.get("/fila").catch(() => undefined);
    });

    expect(await screen.findByRole("heading", { level: 1, name: "Entrar no painel de atendimento" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(AVISO_SESSAO_EXPIRADA);
    expect(router.state.location.pathname).toBe("/cs/login");
    expect(screen.queryByText("maria")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Fila de chamados" })).not.toBeInTheDocument();
  });

  it("sem sessão inicial (401 em /sessao) não mostra aviso de expiração", async () => {
    simular({ "GET /api/cs/sessao": SEM_SESSAO });
    renderizar("/cs/fila");
    await screen.findByRole("heading", { level: 1, name: "Entrar no painel de atendimento" });
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
  });

  it("login com 401 não é tratado como sessão expirada", async () => {
    simular({
      "GET /api/cs/sessao": SEM_SESSAO,
      "POST /api/cs/login": () => json({ erro: { codigo: "credenciais_invalidas", mensagem: "x" } }, 401),
    });
    renderizar("/cs/login");
    await userEvent.type(await screen.findByLabelText("Usuário"), "maria");
    await userEvent.type(screen.getByLabelText("Senha"), "errada");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    await screen.findByRole("alert");
    expect(screen.queryByText(AVISO_SESSAO_EXPIRADA)).not.toBeInTheDocument();
  });
});
