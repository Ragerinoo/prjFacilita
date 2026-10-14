import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { createMemoryRouter, Link } from "react-router";
import { RouterProvider } from "react-router/dom";
import { Layout } from "../app/Layout";
import { armazemRisco } from "../risco/armazemRisco";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { criarArmazenamentoMemoria } from "../api/armazenamento";
import { criarArmazemRisco, PRAZO_CONFIRMACAO_CONTATO_MS, type ArmazemRisco } from "../risco/armazemRisco";
import { RiscoProvider, useRisco } from "../risco/RiscoContext";
import { AlertaRisco, MENSAGEM_CONTATO_NAO_REGISTRADO, TEXTO_ORIENTACAO_RISCO } from "./AlertaRisco";

const jornada = (extra: Record<string, unknown> = {}, estado = "escalada") => ({
  jornada: {
    jornada_id: "J1",
    estado,
    risco: { marcado: true, origem: "ia", em: "2025-01-01T12:00:00Z" },
    ...extra,
  },
});

function Tela({ armazem }: { armazem: ArmazemRisco }) {
  return (
    <RiscoProvider armazem={armazem}>
      <AlertaRisco />
      <main>
        <h1>Conteúdo</h1>
      </main>
    </RiscoProvider>
  );
}

function novoArmazem() {
  return criarArmazemRisco(criarArmazenamentoMemoria());
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("AlertaRisco", () => {
  it("não aparece sem risco marcado pelo servidor", () => {
    render(<Tela armazem={novoArmazem()} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("aparece como alerta com a orientação quando o servidor marca o risco, sem botão para fechar", () => {
    const armazem = novoArmazem();
    render(<Tela armazem={armazem} />);
    act(() => armazem.registrarRespostaServidor(jornada({ contato_cs: "confirmado" })));
    const alerta = screen.getByRole("alert");
    expect(alerta).toHaveTextContent(TEXTO_ORIENTACAO_RISCO);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(alerta.compareDocumentPosition(screen.getByRole("main")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("some só quando o servidor informa o fim da Jornada", () => {
    const armazem = novoArmazem();
    render(<Tela armazem={armazem} />);
    act(() => armazem.registrarRespostaServidor(jornada({ contato_cs: "confirmado" })));
    act(() => armazem.registrarRespostaServidor({ jornada: { jornada_id: "J1", estado: "ativa", risco: { marcado: false } } }));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    act(() => armazem.registrarRespostaServidor(jornada({}, "encerrada_humano")));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("aparece de imediato com o estado guardado no sessionStorage (recarga)", () => {
    const memoria = criarArmazenamentoMemoria();
    criarArmazemRisco(memoria).registrarRespostaServidor(jornada({ contato_cs: "confirmado" }));
    render(<Tela armazem={criarArmazemRisco(memoria)} />);
    expect(screen.getByRole("alert")).toHaveTextContent(TEXTO_ORIENTACAO_RISCO);
  });

  it("avisa que o contato não foi registrado quando o servidor diz isso, mantendo a orientação", () => {
    const armazem = novoArmazem();
    render(<Tela armazem={armazem} />);
    act(() => armazem.registrarRespostaServidor(jornada({ contato_cs: "nao_registrado" })));
    const alerta = screen.getByRole("alert");
    expect(alerta).toHaveTextContent(TEXTO_ORIENTACAO_RISCO);
    expect(alerta).toHaveTextContent(MENSAGEM_CONTATO_NAO_REGISTRADO);
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });

  it("trata contato sem confirmação em 10 s como não registrado", () => {
    vi.useFakeTimers();
    const armazem = novoArmazem();
    render(<Tela armazem={armazem} />);
    act(() => armazem.registrarRespostaServidor(jornada({ contato_cs: "pendente" })));
    expect(screen.queryByRole("button", { name: "Tentar novamente" })).not.toBeInTheDocument();
    act(() => void vi.advanceTimersByTime(PRAZO_CONFIRMACAO_CONTATO_MS + 10));
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });

  it("não mostra o aviso se o servidor confirma antes dos 10 s", () => {
    vi.useFakeTimers();
    const armazem = novoArmazem();
    render(<Tela armazem={armazem} />);
    act(() => armazem.registrarRespostaServidor(jornada({ contato_cs: "pendente" })));
    act(() => void vi.advanceTimersByTime(5000));
    act(() => armazem.registrarRespostaServidor(jornada({ contato_cs: "confirmado" })));
    act(() => void vi.advanceTimersByTime(20_000));
    expect(screen.queryByRole("button", { name: "Tentar novamente" })).not.toBeInTheDocument();
  });

  it("'Tentar novamente' refaz o repasse e o aviso some quando o servidor confirma", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(jornada({ contato_cs: "confirmado" })), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const armazem = novoArmazem();
    render(<Tela armazem={armazem} />);
    act(() => armazem.registrarRespostaServidor(jornada({ contato_cs: "nao_registrado" })));
    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Tentar novamente" })).not.toBeInTheDocument());
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/pub/jornadas/J1/escalar");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toMatchObject({ motivo: "risco" });
    expect(screen.getByRole("alert")).toHaveTextContent(TEXTO_ORIENTACAO_RISCO);
  });

  it("mantém orientação e aviso se a nova tentativa falhar", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 503 })));
    const armazem = novoArmazem();
    render(<Tela armazem={armazem} />);
    act(() => armazem.registrarRespostaServidor(jornada({ contato_cs: "nao_registrado" })));
    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(await screen.findByText(/Não foi possível registrar o contato agora/)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(TEXTO_ORIENTACAO_RISCO);
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeEnabled();
  });

  it("useRisco permite a uma tela informar uma resposta do servidor", () => {
    const armazem = novoArmazem();
    function Pagina() {
      const { registrarRespostaServidor } = useRisco();
      return (
        <button type="button" onClick={() => registrarRespostaServidor(jornada({ contato_cs: "confirmado" }))}>
          simular resposta
        </button>
      );
    }
    render(
      <RiscoProvider armazem={armazem}>
        <AlertaRisco />
        <Pagina />
      </RiscoProvider>,
    );
    act(() => screen.getByRole("button", { name: "simular resposta" }).click());
    expect(screen.getByRole("alert")).toHaveTextContent(TEXTO_ORIENTACAO_RISCO);
  });

  describe("sincronização ao abrir", () => {
    beforeEach(() => window.sessionStorage.setItem("tres.jornada_id", "J1"));
    afterEach(() => window.sessionStorage.clear());

    it("consulta a Jornada no servidor e mostra o alerta marcado nela", async () => {
      const fetchMock = vi.fn(async () => new Response(JSON.stringify(jornada({ contato_cs: "confirmado" })), { status: 200 }));
      vi.stubGlobal("fetch", fetchMock);
      render(<Tela armazem={novoArmazem()} />);
      expect(await screen.findByRole("alert")).toHaveTextContent(TEXTO_ORIENTACAO_RISCO);
      expect((fetchMock.mock.calls[0] as unknown as [string])[0]).toBe("/api/pub/jornadas/J1");
    });
  });

  it("não tem violações de acessibilidade (com e sem aviso de contato)", async () => {
    for (const contato of ["confirmado", "nao_registrado"]) {
      const armazem = novoArmazem();
      const { container, unmount } = render(<Tela armazem={armazem} />);
      act(() => armazem.registrarRespostaServidor(jornada({ contato_cs: contato })));
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(await axe(container)).toHaveNoViolations();
      unmount();
    }
  });

  it("fica no topo do Layout e permanece ao navegar entre telas", async () => {
    const roteador = createMemoryRouter(
      [
        {
          path: "/",
          Component: Layout,
          children: [
            { index: true, element: <Link to="/outra">ir</Link> },
            { path: "outra", element: <h1>Outra tela</h1> },
          ],
        },
      ],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={roteador} />);
    act(() => armazemRisco.registrarRespostaServidor(jornada({ contato_cs: "confirmado" }, "escalada")));
    expect(screen.getByRole("alert")).toHaveTextContent(TEXTO_ORIENTACAO_RISCO);
    await userEvent.click(screen.getByRole("link", { name: "ir" }));
    expect(await screen.findByRole("heading", { name: "Outra tela" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(TEXTO_ORIENTACAO_RISCO);
    act(() => armazemRisco.registrarRespostaServidor(jornada({}, "encerrada_ia")));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
