import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { INTERVALO_ACOMPANHAMENTO_MS } from "../api/chamado";
import {
  MENSAGEM_AVALIACAO_ENVIADA,
  MENSAGEM_NOTA_OBRIGATORIA,
} from "../componentes/AvaliacaoEstrelas";
import { Component, MENSAGEM_CHAMADO_NAO_ENCONTRADO } from "./Chamado";
import { MENSAGEM_NUMERO_VAZIO } from "./chamado/ConsultaChamado";
import {
  MENSAGEM_ENCERRADO,
  MENSAGEM_FALHA_RESPOSTA,
  MENSAGEM_RESPOSTA_ENVIADA,
  MENSAGEM_SEM_MENSAGENS,
} from "./chamado/MensagensChamado";
import { MENSAGEM_TEXTO_LONGO, MENSAGEM_TEXTO_VAZIO } from "../api/chamado";

const NUMERO = "TRES-7K3M9QX2PD";
const CAMINHO = `/api/pub/chamados/${NUMERO}`;

const json = (corpo: unknown, status = 200) =>
  new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });

type Manipulador = (url: string, init: RequestInit) => Response | Promise<Response>;

function simularApi(rotas: Record<string, Manipulador>) {
  const fetchMock = vi.fn(async (url: string, init: RequestInit = {}) => {
    const manipulador = rotas[`${init.method ?? "GET"} ${url.split("?")[0]}`];
    return manipulador ? manipulador(url, init) : json({ erro: { codigo: "chamado_nao_encontrado", mensagem: "x" } }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const chamado = (extra: Record<string, unknown> = {}) => ({
  numero: NUMERO,
  status: "em_atendimento",
  prioridade: "P3",
  anexos_total: 0,
  dados_solicitados: [],
  ...extra,
});

const atendente = (texto: string, em: string) => ({ autor: "atendente", texto, em });
const consumidor = (texto: string, em: string) => ({ autor: "consumidor", texto, em });

function renderizar(caminho = `/chamado/${NUMERO}`) {
  const router = createMemoryRouter(
    [
      { path: "/chamado", Component },
      { path: "/chamado/:numero", Component },
    ],
    { initialEntries: [caminho] },
  );
  return render(<RouterProvider router={router} />);
}

const chamadas = (fetchMock: ReturnType<typeof simularApi>, metodo: string, caminho: string) =>
  fetchMock.mock.calls.filter(([url, init]) => url.split("?")[0] === caminho && (init?.method ?? "GET") === metodo);
const corpoJson = (chamada: [string, RequestInit?] | undefined) => JSON.parse(String(chamada?.[1]?.body));

function definirVisibilidade(valor: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => valor });
  document.dispatchEvent(new Event("visibilitychange"));
}

/** Deixa as promessas pendentes (fetch simulado, leitura do corpo) se resolverem. */
async function esvaziar() {
  for (let i = 0; i < 5; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
      await new Promise((r) => setImmediate(r));
    });
  }
}
async function avancar(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
  await esvaziar();
}

beforeEach(() => sessionStorage.clear());
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(document, "visibilityState");
});

describe("consulta por número", () => {
  it("em /chamado pede o número, recusa vazio e abre o chamado digitado em maiúsculas", async () => {
    simularApi({ [`GET ${CAMINHO}`]: () => json(chamado()) });
    renderizar("/chamado");
    const usuario = userEvent.setup();
    expect(screen.getByRole("heading", { level: 1, name: "Acompanhe o seu chamado" })).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: "Consultar chamado" }));
    expect(screen.getByRole("alert")).toHaveTextContent(MENSAGEM_NUMERO_VAZIO);
    expect(screen.getByLabelText("Número do chamado")).toHaveAttribute("aria-invalid", "true");
    await usuario.type(screen.getByLabelText("Número do chamado"), "  tres-7k3m9qx2pd ");
    await usuario.click(screen.getByRole("button", { name: "Consultar chamado" }));
    expect(await screen.findByText(NUMERO)).toBeInTheDocument();
  });

  it("número inexistente: mostra o erro sem dados e mantém o campo para nova tentativa", async () => {
    const api = simularApi({ [`GET ${CAMINHO}`]: () => json(chamado()) });
    renderizar("/chamado/TRES-NAOEXISTE");
    expect(await screen.findByText(MENSAGEM_CHAMADO_NAO_ENCONTRADO)).toBeInTheDocument();
    expect(screen.queryByText(/Situação do chamado|Mensagens|Recebemos o seu pedido/)).not.toBeInTheDocument();
    const campo = screen.getByLabelText("Número do chamado");
    expect(campo).toHaveValue("TRES-NAOEXISTE");
    const usuario = userEvent.setup();
    await usuario.clear(campo);
    await usuario.type(campo, NUMERO);
    await usuario.click(screen.getByRole("button", { name: "Consultar chamado" }));
    expect(await screen.findByText("Recebemos o seu pedido")).toBeInTheDocument();
    expect(chamadas(api, "GET", `/api/pub/chamados/TRES-NAOEXISTE`)).toHaveLength(1);
  });

  it("repetir o mesmo número inexistente consulta de novo", async () => {
    const api = simularApi({});
    renderizar("/chamado/TRES-NAOEXISTE");
    await screen.findByText(MENSAGEM_CHAMADO_NAO_ENCONTRADO);
    await userEvent.click(screen.getByRole("button", { name: "Consultar chamado" }));
    expect(await screen.findByText(MENSAGEM_CHAMADO_NAO_ENCONTRADO)).toBeInTheDocument();
    expect(chamadas(api, "GET", `/api/pub/chamados/TRES-NAOEXISTE`)).toHaveLength(2);
  });
});

describe("status, mensagens e agendamento", () => {
  it("mostra o status e as mensagens em ordem cronológica, com data e hora de Brasília", async () => {
    simularApi({
      [`GET ${CAMINHO}`]: () =>
        json(
          chamado({
            mensagens: [
              consumidor("Já tentei isso.", "2025-01-02T18:30:00Z"),
              atendente("Olá, vamos ajudar.", "2025-01-02T17:00:00Z"),
              { autor: "sistema", texto: "ignorada", em: "2025-01-02T17:30:00Z" },
            ],
          }),
        ),
    });
    renderizar();
    await screen.findByText(NUMERO);
    expect(screen.getByTestId("status-chamado")).toHaveTextContent(/Em atendimento/);
    const itens = within(screen.getByRole("list", { name: /Mensagens do chamado/ })).getAllByRole("listitem");
    expect(itens).toHaveLength(2);
    expect(itens[0]).toHaveTextContent(/Atendente\s+02\/01\/2025,? 14:00/);
    expect(itens[0]).toHaveTextContent("Olá, vamos ajudar.");
    expect(itens[1]).toHaveTextContent(/Você\s+02\/01\/2025,? 15:30/);
    expect(itens[1]).toHaveTextContent("Já tentei isso.");
  });

  it("sem mensagens, avisa; sem agendamento, não mostra a seção", async () => {
    simularApi({ [`GET ${CAMINHO}`]: () => json(chamado({ agendamento: null })) });
    renderizar();
    expect(await screen.findByText(MENSAGEM_SEM_MENSAGENS)).toBeInTheDocument();
    expect(screen.queryByText("Ligação agendada")).not.toBeInTheDocument();
  });

  it("mostra a ligação agendada com data e hora de Brasília", async () => {
    simularApi({
      [`GET ${CAMINHO}`]: () => json(chamado({ agendamento: { data_hora: "2025-01-02T14:00:00-03:00" } })),
    });
    renderizar();
    const secao = (await screen.findByRole("heading", { name: "Ligação agendada" })).closest("section")!;
    expect(secao).toHaveTextContent(/2 de janeiro de 2025/);
    expect(secao).toHaveTextContent(/14:00/);
    expect(secao).toHaveTextContent(/horário de Brasília/);
  });
});

describe("resposta do Consumidor", () => {
  const rotas = (post: Manipulador): Record<string, Manipulador> => ({
    [`GET ${CAMINHO}`]: () => json(chamado()),
    [`POST ${CAMINHO}/mensagens`]: post,
  });

  it("recusa vazio, só espaços e mais de 2000 caracteres, mantendo o texto", async () => {
    const api = simularApi(rotas(() => json({}, 201)));
    renderizar();
    const usuario = userEvent.setup();
    const campo = await screen.findByLabelText("Sua resposta");
    await usuario.click(screen.getByRole("button", { name: "Enviar resposta" }));
    expect(screen.getByText(MENSAGEM_TEXTO_VAZIO)).toBeInTheDocument();
    await usuario.type(campo, "   ");
    await usuario.click(screen.getByRole("button", { name: "Enviar resposta" }));
    expect(screen.getByText(MENSAGEM_TEXTO_VAZIO)).toBeInTheDocument();
    expect(campo).toHaveValue("   ");
    await usuario.clear(campo);
    await usuario.click(campo);
    await usuario.paste("a".repeat(2001));
    await usuario.click(screen.getByRole("button", { name: "Enviar resposta" }));
    expect(screen.getByText(MENSAGEM_TEXTO_LONGO)).toBeInTheDocument();
    expect(campo).toHaveValue("a".repeat(2001));
    expect(campo).toHaveFocus();
    expect(chamadas(api, "POST", `${CAMINHO}/mensagens`)).toHaveLength(0);
  });

  it("envia o texto aparado, limpa o campo e atualiza a lista na hora", async () => {
    let enviadas: unknown[] = [];
    const api = simularApi({
      [`GET ${CAMINHO}`]: () =>
        json(chamado({ mensagens: enviadas.length ? [consumidor("Obrigado!", "2025-01-02T18:30:00Z")] : [] })),
      [`POST ${CAMINHO}/mensagens`]: (_url, init) => {
        enviadas = [JSON.parse(String(init.body))];
        return json({}, 201);
      },
    });
    renderizar();
    const usuario = userEvent.setup();
    await usuario.type(await screen.findByLabelText("Sua resposta"), "  Obrigado!  ");
    await usuario.click(screen.getByRole("button", { name: "Enviar resposta" }));
    expect(await screen.findByText(MENSAGEM_RESPOSTA_ENVIADA)).toBeInTheDocument();
    const corpo = corpoJson(chamadas(api, "POST", `${CAMINHO}/mensagens`)[0]);
    expect(corpo.texto).toBe("Obrigado!");
    expect(typeof corpo.evento_id).toBe("string");
    expect(screen.getByLabelText("Sua resposta")).toHaveValue("");
    expect(await screen.findByText("Obrigado!", { selector: "p" })).toBeInTheDocument();
  });

  it("em falha do servidor mantém o texto e permite novo envio", async () => {
    let falhar = true;
    simularApi(rotas(() => (falhar ? json({ erro: { codigo: "x", mensagem: "falhou" } }, 503) : json({}, 201))));
    renderizar();
    const usuario = userEvent.setup();
    const campo = await screen.findByLabelText("Sua resposta");
    await usuario.type(campo, "Minha resposta");
    await usuario.click(screen.getByRole("button", { name: "Enviar resposta" }));
    expect(await screen.findByText(MENSAGEM_FALHA_RESPOSTA)).toBeInTheDocument();
    expect(campo).toHaveValue("Minha resposta");
    falhar = false;
    await usuario.click(screen.getByRole("button", { name: "Enviar resposta" }));
    expect(await screen.findByText(MENSAGEM_RESPOSTA_ENVIADA)).toBeInTheDocument();
    expect(screen.queryByText(MENSAGEM_FALHA_RESPOSTA)).not.toBeInTheDocument();
  });

  it("mostra o motivo do servidor junto ao campo", async () => {
    simularApi(
      rotas(() => json({ erro: { codigo: "dados_invalidos", mensagem: "x", campos: [{ campo: "texto", motivo: "Texto inválido." }] } }, 422)),
    );
    renderizar();
    const usuario = userEvent.setup();
    const campo = await screen.findByLabelText("Sua resposta");
    await usuario.type(campo, "oi");
    await usuario.click(screen.getByRole("button", { name: "Enviar resposta" }));
    expect(await screen.findByText("Texto inválido.")).toBeInTheDocument();
    expect(campo).toHaveAccessibleDescription(/Texto inválido\./);
    expect(campo).toHaveValue("oi");
  });

  it("não oferece resposta quando o chamado está encerrado", async () => {
    simularApi({ [`GET ${CAMINHO}`]: () => json(chamado({ status: "encerrado", avaliacao_pendente: false })) });
    renderizar();
    expect(await screen.findByText(MENSAGEM_ENCERRADO)).toBeInTheDocument();
    expect(screen.queryByLabelText("Sua resposta")).not.toBeInTheDocument();
  });
});

describe("atualização a cada 5 segundos", () => {
  beforeEach(() => vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] }));

  it("traz mensagem e agendamento novos, anunciando só a mensagem nova do Atendente", async () => {
    let corpo: Record<string, unknown> = chamado({ mensagens: [atendente("Primeira.", "2025-01-02T17:00:00Z")] });
    const api = simularApi({ [`GET ${CAMINHO}`]: () => json(corpo) });
    renderizar();
    await esvaziar();
    expect(screen.getByText("Primeira.")).toBeInTheDocument();
    expect(screen.getByTestId("anuncio-mensagem")).toBeEmptyDOMElement();
    expect(chamadas(api, "GET", CAMINHO)).toHaveLength(1);

    corpo = chamado({
      mensagens: [atendente("Primeira.", "2025-01-02T17:00:00Z"), atendente("Segunda.", "2025-01-02T17:05:00Z")],
      agendamento: { data_hora: "2025-01-03T10:00:00-03:00" },
    });
    await avancar(INTERVALO_ACOMPANHAMENTO_MS - 1);
    expect(chamadas(api, "GET", CAMINHO)).toHaveLength(1);
    await avancar(1);
    expect(chamadas(api, "GET", CAMINHO)).toHaveLength(2);
    expect(screen.getByText("Segunda.")).toBeInTheDocument();
    expect(screen.getByText("Ligação agendada")).toBeInTheDocument();
    const anuncio = screen.getByTestId("anuncio-mensagem");
    expect(anuncio).toHaveAttribute("aria-live", "polite");
    expect(anuncio).toHaveTextContent(/Nova mensagem do atendente, 02\/01\/2025,? 14:05: Segunda\./);

    await avancar(INTERVALO_ACOMPANHAMENTO_MS);
    expect(chamadas(api, "GET", CAMINHO)).toHaveLength(3);
  });

  it("pausa com a página oculta e retoma, consultando na hora, ao ficar visível", async () => {
    const api = simularApi({ [`GET ${CAMINHO}`]: () => json(chamado()) });
    renderizar();
    await esvaziar();
    definirVisibilidade("hidden");
    await avancar(INTERVALO_ACOMPANHAMENTO_MS * 4);
    expect(chamadas(api, "GET", CAMINHO)).toHaveLength(1);
    definirVisibilidade("visible");
    await esvaziar();
    expect(chamadas(api, "GET", CAMINHO)).toHaveLength(2);
    await avancar(INTERVALO_ACOMPANHAMENTO_MS);
    expect(chamadas(api, "GET", CAMINHO)).toHaveLength(3);
  });

  it("para ao sair da página", async () => {
    const api = simularApi({ [`GET ${CAMINHO}`]: () => json(chamado()) });
    const { unmount } = renderizar();
    await esvaziar();
    unmount();
    await avancar(INTERVALO_ACOMPANHAMENTO_MS * 4);
    expect(chamadas(api, "GET", CAMINHO)).toHaveLength(1);
  });

  it("mantém o que está na tela quando uma atualização falha e segue tentando", async () => {
    let falhar = false;
    const api = simularApi({
      [`GET ${CAMINHO}`]: () => (falhar ? json({}, 503) : json(chamado({ mensagens: [atendente("Oi.", "2025-01-02T17:00:00Z")] }))),
    });
    renderizar();
    await esvaziar();
    falhar = true;
    await avancar(INTERVALO_ACOMPANHAMENTO_MS);
    expect(screen.getByText("Oi.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await avancar(INTERVALO_ACOMPANHAMENTO_MS);
    expect(chamadas(api, "GET", CAMINHO)).toHaveLength(3);
  });

  it("não perde o que o Consumidor digitou quando a atualização chega", async () => {
    simularApi({ [`GET ${CAMINHO}`]: () => json(chamado()) });
    renderizar();
    await esvaziar();
    const campo = screen.getByLabelText("Sua resposta");
    fireInput(campo, "rascunho");
    await avancar(INTERVALO_ACOMPANHAMENTO_MS);
    expect(screen.getByLabelText("Sua resposta")).toHaveValue("rascunho");
  });
});

function fireInput(campo: HTMLElement, valor: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
  act(() => {
    setter.call(campo, valor);
    campo.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

describe("avaliação ao encerrar", () => {
  const rotas = (extra: Record<string, unknown> = {}): Record<string, Manipulador> => ({
    [`GET ${CAMINHO}`]: () => json(chamado({ status: "encerrado", ...extra })),
    [`POST ${CAMINHO}/avaliacao`]: () => json({}, 201),
  });

  it("não oferece avaliação com o chamado em andamento", async () => {
    simularApi({ [`GET ${CAMINHO}`]: () => json(chamado({ avaliacao_pendente: true })) });
    renderizar();
    await screen.findByText(NUMERO);
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });

  it("não oferece de novo quando já foi avaliada", async () => {
    simularApi(rotas({ avaliacao_pendente: false }));
    renderizar();
    await screen.findByText(NUMERO);
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });

  it("ao encerrar, exige a nota, envia nota e comentário ao chamado e confirma", async () => {
    const api = simularApi(rotas({ avaliacao_pendente: true }));
    renderizar();
    const usuario = userEvent.setup();
    await usuario.click(await screen.findByRole("button", { name: "Enviar avaliação" }));
    expect(screen.getByText(MENSAGEM_NOTA_OBRIGATORIA)).toBeInTheDocument();
    await usuario.click(screen.getByRole("radio", { name: "4 estrelas" }));
    await usuario.type(screen.getByLabelText("Comentário (opcional)"), "Atendimento rápido");
    await usuario.click(screen.getByRole("button", { name: "Enviar avaliação" }));
    expect(await screen.findByText(MENSAGEM_AVALIACAO_ENVIADA)).toBeInTheDocument();
    const envios = chamadas(api, "POST", `${CAMINHO}/avaliacao`);
    expect(envios).toHaveLength(1);
    expect(corpoJson(envios[0])).toMatchObject({ nota: 4, comentario: "Atendimento rápido" });
  });

  it("assume avaliação pendente quando o servidor não informa o campo", async () => {
    simularApi(rotas());
    renderizar();
    expect(await screen.findByRole("radio", { name: "5 estrelas" })).toBeInTheDocument();
  });

  it("mantém a confirmação na tela depois que o servidor marca a avaliação como feita", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    let pendente = true;
    const api = simularApi({
      [`GET ${CAMINHO}`]: () => json(chamado({ status: "encerrado", avaliacao_pendente: pendente })),
      [`POST ${CAMINHO}/avaliacao`]: () => {
        pendente = false;
        return json({}, 201);
      },
    });
    renderizar();
    await esvaziar();
    await act(async () => {
      screen.getByRole("radio", { name: "5 estrelas" }).click();
    });
    await act(async () => {
      screen.getByRole("button", { name: "Enviar avaliação" }).click();
    });
    await esvaziar();
    expect(screen.getByText(MENSAGEM_AVALIACAO_ENVIADA)).toBeInTheDocument();
    await avancar(INTERVALO_ACOMPANHAMENTO_MS);
    expect(chamadas(api, "GET", CAMINHO).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(MENSAGEM_AVALIACAO_ENVIADA)).toBeInTheDocument();
  });
});

describe("acessibilidade", () => {
  it("a página de consulta não tem violações", async () => {
    const { container } = renderizar("/chamado");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("a tela de não encontrado não tem violações", async () => {
    simularApi({});
    const { container } = renderizar("/chamado/TRES-NAOEXISTE");
    await screen.findByText(MENSAGEM_CHAMADO_NAO_ENCONTRADO);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("a página com mensagens, agendamento e avaliação não tem violações", async () => {
    simularApi({
      [`GET ${CAMINHO}`]: () =>
        json(
          chamado({
            status: "encerrado",
            mensagens: [atendente("Olá.", "2025-01-02T17:00:00Z"), consumidor("Oi.", "2025-01-02T17:10:00Z")],
            agendamento: { data_hora: "2025-01-03T10:00:00-03:00" },
          }),
        ),
    });
    const { container } = renderizar();
    await screen.findByRole("radio", { name: "5 estrelas" });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("a página com resposta e erro não tem violações", async () => {
    simularApi({ [`GET ${CAMINHO}`]: () => json(chamado({ mensagens: [atendente("Olá.", "2025-01-02T17:00:00Z")] })) });
    const { container } = renderizar();
    await userEvent.click(await screen.findByRole("button", { name: "Enviar resposta" }));
    expect(await axe(container)).toHaveNoViolations();
  });
});
