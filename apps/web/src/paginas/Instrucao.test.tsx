import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { createMemoryRouter, useLocation } from "react-router";
import { RouterProvider } from "react-router/dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  Component,
  MENSAGEM_ERRO_INSTRUCAO,
  MENSAGEM_FALHA_RESPOSTA,
  MENSAGEM_REPASSE_NAO_INICIADO,
  MENSAGEM_SEM_INSTRUCAO,
  TEXTO_PREFIRO_ASSISTENTE,
} from "./Instrucao";
import { MENSAGEM_AVALIACAO_ENVIADA, MENSAGEM_AVALIACAO_FALHOU, MENSAGEM_NOTA_OBRIGATORIA } from "../componentes/AvaliacaoEstrelas";

const passo = (n: number, extra: Record<string, unknown> = {}) => ({
  n,
  texto: `Faça a ação ${n}.`,
  alt: `Ilustração da ação ${n}`,
  texto_equivalente: `Passo ${n}: faça a ação ${n}. (ilustração)`,
  midia_url: `/midia/${n}.svg`,
  midia_tipo: "imagem",
  ...extra,
});
const INSTRUCAO = { problema_id: 1, variante: "padrao", passos: [passo(1), passo(2), passo(3)] };

function json(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
}
const erro = (status: number) => json({ erro: { codigo: "x", mensagem: "falhou" } }, status);

type Manipulador = (url: string, init: RequestInit) => Response | Promise<Response>;

/** Simula a API por "METODO caminho" (sem a consulta); o que não está na tabela devolve 201. */
function simularApi(rotas: Record<string, Manipulador> = {}) {
  const fetchMock = vi.fn(async (url: string, init: RequestInit = {}) => {
    const chave = `${init.method ?? "GET"} ${url.split("?")[0]}`;
    const manipulador = rotas[chave];
    if (manipulador) return manipulador(url, init);
    if (chave === "GET /api/pub/jornadas/J1/instrucao") return json(INSTRUCAO);
    return json({}, 201);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const chamadas = (fetchMock: ReturnType<typeof simularApi>, metodo: string, caminho: string) =>
  fetchMock.mock.calls.filter(([url, init]) => url.split("?")[0] === caminho && (init?.method ?? "GET") === metodo);
const corpoDe = (chamada: [string, RequestInit?] | undefined) =>
  JSON.parse((chamada?.[1]?.body as string | undefined) ?? "null");

function Maquina() {
  return <h1>Página da máquina</h1>;
}
function AbrirChamado() {
  const estado = useLocation().state as { contexto?: string } | null;
  return (
    <div>
      <h1>Abrir um chamado</h1>
      <p>{estado?.contexto}</p>
    </div>
  );
}

function renderizar(caminho = "/m/tres-passione/p/1") {
  const router = createMemoryRouter(
    [
      { path: "/m/:modeloId", Component: Maquina },
      { path: "/m/:modeloId/p/:problemaId", Component },
      { path: "/chamado/:numero", element: <h1>Chamado</h1> },
      { path: "/abrir-chamado", Component: AbrirChamado },
    ],
    { initialEntries: [caminho] },
  );
  const resultado = render(<RouterProvider router={router} />);
  return { ...resultado, router };
}

function definirMovimentoReduzido(reduzido: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: (consulta: string) => ({
      matches: reduzido && consulta.includes("reduce"),
      media: consulta,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }),
  });
}

beforeEach(() => {
  sessionStorage.clear();
  sessionStorage.setItem("tres.jornada_id", "J1");
  simularApi();
});
afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(window, "matchMedia");
  sessionStorage.clear();
});

describe("passos da instrução", () => {
  it("mostra um passo numerado por vez, com mídia, alternativa e texto equivalente", async () => {
    const { container } = renderizar();

    expect(await screen.findByRole("heading", { level: 2, name: "Passo 1 de 3" })).toHaveFocus();
    expect(screen.getByText("Faça a ação 1.")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Ilustração da ação 1" })).toHaveAttribute("src", "/midia/1.svg");
    expect(screen.getByText("Passo 1: faça a ação 1. (ilustração)")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("avança passo a passo, registra exibido e concluído e termina na pergunta", async () => {
    const fetchMock = simularApi();
    renderizar();
    const usuario = userEvent.setup();

    await screen.findByRole("heading", { name: "Passo 1 de 3" });
    await usuario.click(screen.getByRole("button", { name: /Fiz este passo/ }));
    expect(await screen.findByRole("heading", { name: "Passo 2 de 3" })).toHaveFocus();
    await usuario.click(screen.getByRole("button", { name: /Fiz este passo/ }));
    await screen.findByRole("heading", { name: "Passo 3 de 3" });
    await usuario.click(screen.getByRole("button", { name: "Fiz o último passo" }));

    expect(await screen.findByRole("heading", { name: "O problema foi solucionado?" })).toBeInTheDocument();
    await waitFor(() => expect(chamadas(fetchMock, "POST", "/api/pub/jornadas/J1/eventos")).toHaveLength(6));
    const eventos = chamadas(fetchMock, "POST", "/api/pub/jornadas/J1/eventos").map((c) => corpoDe(c));
    expect(eventos.map((e) => `${e.tipo}:${e.passo}`)).toEqual([
      "exibido:1",
      "concluido:1",
      "exibido:2",
      "concluido:2",
      "exibido:3",
      "concluido:3",
    ]);
    expect(eventos[0]).toMatchObject({ problema_id: 1, evento_id: expect.any(String) });
    expect(Number.isNaN(Date.parse(eventos[0].ocorrido_em))).toBe(false);
    expect(chamadas(fetchMock, "GET", "/api/pub/jornadas/J1/instrucao")[0]?.[0]).toBe(
      "/api/pub/jornadas/J1/instrucao?problema_id=1",
    );
  });

  it("se a mídia falhar, mostra o texto e a alternativa e o avanço continua liberado", async () => {
    renderizar();
    const usuario = userEvent.setup();
    fireEvent.error(await screen.findByRole("img", { name: "Ilustração da ação 1" }));

    expect(screen.getByText("Descrição da imagem: Ilustração da ação 1")).toBeInTheDocument();
    expect(screen.getByText("Faça a ação 1.")).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: /Fiz este passo/ }));
    expect(await screen.findByRole("heading", { name: "Passo 2 de 3" })).toBeInTheDocument();
  });

  it("com movimento reduzido, usa a imagem estática e não inicia nenhum vídeo", async () => {
    definirMovimentoReduzido(true);
    simularApi({
      "GET /api/pub/jornadas/J1/instrucao": () =>
        json({
          passos: [passo(1, { midia_tipo: "video", midia_url: "/v.mp4", midia_estatica_url: "/v.png" })],
        }),
    });
    const { container } = renderizar();
    expect(await screen.findByRole("img", { name: "Ilustração da ação 1" })).toHaveAttribute("src", "/v.png");
    expect(container.querySelector("video")).toBeNull();
    expect(screen.getByText(/Passo 1: faça a ação 1/)).toBeInTheDocument();
  });

  it("instrução inexistente mostra mensagem com opções e preserva a Jornada", async () => {
    const fetchMock = simularApi({ "GET /api/pub/jornadas/J1/instrucao": () => erro(404) });
    const { router, container } = renderizar();

    expect(await screen.findByText(MENSAGEM_SEM_INSTRUCAO)).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
    expect(screen.getByRole("link", { name: "Voltar para a página da máquina" })).toHaveAttribute("href", "/m/tres-passione");
    await userEvent.click(screen.getByRole("button", { name: "Abrir chamado" }));

    expect(await screen.findByText("Fluxo 1 - modelo tres-passione")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/abrir-chamado");
    expect(sessionStorage.getItem("tres.jornada_id")).toBe("J1");
    expect(chamadas(fetchMock, "POST", "/api/pub/jornadas")).toHaveLength(0);
  });

  it("falha do servidor oferece tentar novamente", async () => {
    let tentativas = 0;
    simularApi({
      "GET /api/pub/jornadas/J1/instrucao": () => (++tentativas === 1 ? erro(503) : json(INSTRUCAO)),
    });
    renderizar();
    expect(await screen.findByText(MENSAGEM_ERRO_INSTRUCAO)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(await screen.findByRole("heading", { name: "Passo 1 de 3" })).toBeInTheDocument();
  });

  it("sem Jornada guardada, abre uma nova antes de buscar a instrução", async () => {
    sessionStorage.clear();
    const fetchMock = simularApi({
      "POST /api/pub/jornadas": () => json({ jornada_id: "J1" }, 201),
    });
    renderizar();
    expect(await screen.findByRole("heading", { name: "Passo 1 de 3" })).toBeInTheDocument();
    expect(chamadas(fetchMock, "POST", "/api/pub/jornadas")).toHaveLength(1);
  });
});

describe("vazamento", () => {
  const ROTA = "/m/tres-passione/p/10";

  it("pergunta externo ou interno com duas opções antes de qualquer passo", async () => {
    const fetchMock = simularApi();
    const { container } = renderizar(ROTA);
    expect(await screen.findByRole("heading", { name: "O vazamento é externo ou interno?" })).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(2);
    expect(chamadas(fetchMock, "GET", "/api/pub/jornadas/J1/instrucao")).toHaveLength(0);
    expect(screen.queryByText(/Passo 1/)).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("externo: abre a variante externa já no segundo toque e registra a resposta", async () => {
    const fetchMock = simularApi();
    renderizar(ROTA);
    await userEvent.click(await screen.findByRole("button", { name: /^Externo/ }));

    expect(await screen.findByRole("heading", { name: "Passo 1 de 3" })).toBeInTheDocument();
    expect(chamadas(fetchMock, "GET", "/api/pub/jornadas/J1/instrucao")[0]?.[0]).toBe(
      "/api/pub/jornadas/J1/instrucao?problema_id=10&variante=externo",
    );
    await waitFor(() => expect(chamadas(fetchMock, "POST", "/api/pub/jornadas/J1/vazamento")).toHaveLength(1));
    expect(corpoDe(chamadas(fetchMock, "POST", "/api/pub/jornadas/J1/vazamento")[0])).toMatchObject({ tipo: "externo" });
  });

  it("interno: não mostra passos, escala e não oferece o assistente", async () => {
    const fetchMock = simularApi({
      "POST /api/pub/jornadas/J1/vazamento": () => json({ numero: "TRES-77" }, 201),
    });
    renderizar(ROTA);
    await userEvent.click(await screen.findByRole("button", { name: /^Interno/ }));

    expect(await screen.findByText("TRES-77")).toBeInTheDocument();
    expect(corpoDe(chamadas(fetchMock, "POST", "/api/pub/jornadas/J1/vazamento")[0])).toMatchObject({ tipo: "interno" });
    expect(chamadas(fetchMock, "GET", "/api/pub/jornadas/J1/instrucao")).toHaveLength(0);
    expect(screen.queryByText(/Passo 1/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: TEXTO_PREFIRO_ASSISTENTE })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Acompanhar o meu chamado" })).toHaveAttribute("href", "/chamado/TRES-77");
  });

  it("interno que falha permite tentar de novo; recarregar depois do sucesso não mostra passos", async () => {
    let chamadasInterno = 0;
    simularApi({
      "POST /api/pub/jornadas/J1/vazamento": () => (++chamadasInterno === 1 ? erro(500) : json({ numero: "TRES-5" }, 201)),
    });
    const primeira = renderizar(ROTA);
    await userEvent.click(await screen.findByRole("button", { name: /^Interno/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(MENSAGEM_REPASSE_NAO_INICIADO);
    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(await screen.findByText("TRES-5")).toBeInTheDocument();
    primeira.unmount();

    renderizar(ROTA);
    expect(await screen.findByRole("heading", { name: /Por segurança/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Externo/ })).not.toBeInTheDocument();
  });
});

describe("O problema foi solucionado?", () => {
  async function chegarNaPergunta() {
    const usuario = userEvent.setup();
    await screen.findByRole("heading", { name: "Passo 1 de 1" });
    await usuario.click(screen.getByRole("button", { name: "Fiz o último passo" }));
    await screen.findByRole("heading", { name: "O problema foi solucionado?" });
    return usuario;
  }
  const UM_PASSO = { "GET /api/pub/jornadas/J1/instrucao": () => json({ passos: [passo(1)] }) };

  it("mostra exatamente Sim e Não e não registra resposta antes da escolha", async () => {
    const fetchMock = simularApi(UM_PASSO);
    const { container } = renderizar();
    await chegarNaPergunta();

    const grupo = screen.getByRole("region", { name: "O problema foi solucionado?" });
    expect(within(grupo).getAllByRole("button").map((b) => b.textContent)).toEqual(["Sim", "Não"]);
    expect(chamadas(fetchMock, "POST", "/api/pub/jornadas/J1/resolucao")).toHaveLength(0);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("Sim: marca como resolvida e permite avaliar com nota de 1 a 5 e comentário", async () => {
    const fetchMock = simularApi(UM_PASSO);
    const { container } = renderizar();
    const usuario = await chegarNaPergunta();
    await usuario.click(screen.getByRole("button", { name: "Sim" }));

    expect(await screen.findByRole("heading", { name: "Que bom que deu certo!" })).toBeInTheDocument();
    expect(corpoDe(chamadas(fetchMock, "POST", "/api/pub/jornadas/J1/resolucao")[0])).toMatchObject({
      resolvido: true,
      problema_id: 1,
      evento_id: expect.any(String),
    });
    expect(screen.getAllByRole("radio")).toHaveLength(5);
    expect(await axe(container)).toHaveNoViolations();

    await usuario.click(screen.getByRole("button", { name: "Enviar avaliação" }));
    expect(screen.getByRole("alert")).toHaveTextContent(MENSAGEM_NOTA_OBRIGATORIA);

    await usuario.click(screen.getByRole("radio", { name: "4 estrelas" }));
    await usuario.type(screen.getByLabelText("Comentário (opcional)"), "Ajudou muito");
    await usuario.click(screen.getByRole("button", { name: "Enviar avaliação" }));

    expect(await screen.findByText(MENSAGEM_AVALIACAO_ENVIADA)).toBeInTheDocument();
    expect(corpoDe(chamadas(fetchMock, "POST", "/api/pub/jornadas/J1/avaliacao")[0])).toMatchObject({
      nota: 4,
      comentario: "Ajudou muito",
    });
  });

  it("avaliação que não é registrada avisa, mantém a nota e não reabre a Jornada", async () => {
    simularApi({ ...UM_PASSO, "POST /api/pub/jornadas/J1/avaliacao": () => erro(422) });
    renderizar();
    const usuario = await chegarNaPergunta();
    await usuario.click(screen.getByRole("button", { name: "Sim" }));
    await usuario.click(await screen.findByRole("radio", { name: "5 estrelas" }));
    await usuario.click(screen.getByRole("button", { name: "Enviar avaliação" }));

    expect(await screen.findByText(MENSAGEM_AVALIACAO_FALHOU)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "5 estrelas" })).toBeChecked();
    expect(screen.queryByRole("heading", { name: "O problema foi solucionado?" })).not.toBeInTheDocument();
  });

  it("falha ao registrar o Sim mantém a pergunta com aviso", async () => {
    simularApi({ ...UM_PASSO, "POST /api/pub/jornadas/J1/resolucao": () => erro(500) });
    renderizar();
    const usuario = await chegarNaPergunta();
    await usuario.click(screen.getByRole("button", { name: "Sim" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(MENSAGEM_FALHA_RESPOSTA);
    expect(screen.getByRole("button", { name: "Não" })).toBeInTheDocument();
  });

  it("Não: inicia o repasse, mostra o chamado e oferece descrever ao assistente com o mesmo jornada_id", async () => {
    const fetchMock = simularApi({
      ...UM_PASSO,
      "POST /api/pub/jornadas/J1/resolucao": () => json({ chamado: { numero: "TRES-12" } }, 201),
    });
    const { router, container } = renderizar();
    const usuario = await chegarNaPergunta();
    await usuario.click(screen.getByRole("button", { name: "Não" }));

    expect(await screen.findByText("TRES-12")).toBeInTheDocument();
    expect(corpoDe(chamadas(fetchMock, "POST", "/api/pub/jornadas/J1/resolucao")[0])).toMatchObject({ resolvido: false });
    expect(screen.getByRole("link", { name: "Acompanhar o meu chamado" })).toHaveAttribute("href", "/chamado/TRES-12");
    expect(await axe(container)).toHaveNoViolations();

    await usuario.click(screen.getByRole("button", { name: TEXTO_PREFIRO_ASSISTENTE }));
    expect(await screen.findByText("Fluxo 1 - modelo tres-passione")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/abrir-chamado");
    expect(sessionStorage.getItem("tres.jornada_id")).toBe("J1");
  });

  it("Não com falha: avisa, deixa tentar novamente até 3 vezes e mantém o assistente", async () => {
    let tentativas = 0;
    const fetchMock = simularApi({
      ...UM_PASSO,
      "POST /api/pub/jornadas/J1/resolucao": () => {
        tentativas += 1;
        return erro(500);
      },
    });
    renderizar();
    const usuario = await chegarNaPergunta();
    await usuario.click(screen.getByRole("button", { name: "Não" }));

    for (let i = 0; i < 3; i++) {
      expect(await screen.findByRole("alert")).toHaveTextContent(MENSAGEM_REPASSE_NAO_INICIADO);
      await usuario.click(screen.getByRole("button", { name: "Tentar novamente" }));
      await waitFor(() => expect(tentativas).toBe(i + 2));
    }
    await waitFor(() => expect(screen.queryByRole("button", { name: "Tentar novamente" })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: TEXTO_PREFIRO_ASSISTENTE })).toBeInTheDocument();
    // Mesma ação, mesmo evento_id: o servidor ignora duplicatas.
    const ids = chamadas(fetchMock, "POST", "/api/pub/jornadas/J1/resolucao").map((c) => corpoDe(c).evento_id);
    expect(new Set(ids).size).toBe(1);
  });
});
