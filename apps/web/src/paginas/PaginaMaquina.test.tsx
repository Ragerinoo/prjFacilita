import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { createMemoryRouter, useLocation } from "react-router";
import { RouterProvider } from "react-router/dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  Component,
  MENSAGEM_CODIGO_ILEGIVEL,
  MENSAGEM_FALHA_SELECAO,
  MENSAGEM_INDISPONIVEL,
  MENSAGEM_MODELO_NAO_RECONHECIDO,
  TEXTO_OUTRO_PROBLEMA,
} from "./PaginaMaquina";

const TITULOS = [
  "Máquina não está ligando",
  "Luz vermelha fixa",
  "Alerta vermelho piscando",
  "Teclas das xícaras e sensor vermelho piscando",
  "Luz amarela acesa",
  "Não extrai bebidas",
  "Bebida aguada",
  "Bebida fria",
  "Alavanca travada",
  "Vazamento",
  "Não puxa água",
  "Bico entupido",
  "Alavanca não fecha com cápsula",
];
const ICONES = [
  "power",
  "luz-vermelha",
  "alerta",
  "teclas",
  "luz-amarela",
  "xicara-vazia",
  "gota",
  "termometro",
  "alavanca",
  "vazamento",
  "reservatorio",
  "bico",
  "capsula",
];

const MAQUINA = {
  modelo: { modelo_id: "tres-passione", nome: "TRES Passione", foto_url: "/p.svg" },
  // Fora de ordem de propósito: a página precisa ordenar por `ordem`.
  problemas: TITULOS.map((titulo, i) => ({
    problema_id: i + 1,
    ordem: i + 1,
    titulo,
    icone: ICONES[i],
    icone_alt: `Ícone ${i + 1}: ${titulo}`,
  })).reverse(),
  seletor: null,
};

function json(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
}

type Manipulador = (url: string, init: RequestInit) => Response | Promise<Response>;

/** Simula a API: modelo por GET, Jornada e eventos por POST. */
function simularApi(opcoes: { modelo?: Manipulador; jornada?: Manipulador } = {}) {
  const fetchMock = vi.fn(async (url: string, init: RequestInit = {}) => {
    if (url.startsWith("/api/pub/modelos/")) return (opcoes.modelo ?? (() => json(MAQUINA)))(url, init);
    if (url === "/api/pub/jornadas") return (opcoes.jornada ?? (() => json({ jornada_id: "J1" }, 201)))(url, init);
    return json({}, 201);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const chamadas = (fetchMock: ReturnType<typeof simularApi>, metodo: string, caminho: string) =>
  fetchMock.mock.calls.filter(([url, init]) => url === caminho && (init?.method ?? "GET") === metodo);

function Busca() {
  const estado = useLocation().state as { mensagem?: string } | null;
  return (
    <div>
      <h1>Busca</h1>
      <p role="status">{estado?.mensagem}</p>
    </div>
  );
}

function renderizar(entradas: string[] = ["/m/tres-passione"], indice?: number) {
  const router = createMemoryRouter(
    [
      { path: "/", Component: Busca },
      { path: "/m/:modeloId", Component },
      { path: "/m/:modeloId/p/:problemaId", element: <h1>Instrução</h1> },
      { path: "/abrir-chamado", element: <h1>Abrir um chamado</h1> },
    ],
    { initialEntries: entradas, initialIndex: indice },
  );
  const resultado = render(<RouterProvider router={router} />);
  return { ...resultado, router };
}

beforeEach(() => sessionStorage.clear());
afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("Pagina_Maquina aberta pelo QR", () => {
  it("abre direto na página da máquina, com os 13 problemas na ordem, ícone com texto alternativo e a opção final", async () => {
    const fetchMock = simularApi();
    const { container } = renderizar();

    expect(await screen.findByRole("heading", { level: 1, name: "TRES Passione" })).toBeInTheDocument();
    const itens = within(screen.getByRole("list", { name: "Problemas" })).getAllByRole("listitem");
    expect(itens).toHaveLength(13);
    itens.forEach((item, i) => {
      expect(within(item).getByText(TITULOS[i])).toBeInTheDocument();
      expect(within(item).getByRole("img", { name: `Ícone ${i + 1}: ${TITULOS[i]}` })).toBeInTheDocument();
    });
    const botoes = screen.getAllByRole("button");
    expect(botoes).toHaveLength(14);
    expect(botoes[13]).toHaveTextContent(TEXTO_OUTRO_PROBLEMA);

    // Nenhuma tela intermediária: o modelo é consultado com timeout curto e a Jornada nasce em seguida.
    await waitFor(() => expect(chamadas(fetchMock, "POST", "/api/pub/jornadas")).toHaveLength(1));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/pub/modelos/tres-passione");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("registra a Jornada com origem qr, modelo e série válida", async () => {
    const fetchMock = simularApi();
    renderizar(["/m/tres-passione?s=AB12cd"]);
    await waitFor(() => expect(chamadas(fetchMock, "POST", "/api/pub/jornadas")).toHaveLength(1));
    const [, init] = chamadas(fetchMock, "POST", "/api/pub/jornadas")[0];
    expect(JSON.parse(init!.body as string)).toEqual({
      origem: "qr",
      modelo_id: "tres-passione",
      numero_serie: "AB12cd",
    });
    await waitFor(() => expect(sessionStorage.getItem("tres.jornada_id")).toBe("J1"));
  });

  it.each([["AB-12"], ["x".repeat(31)], [""]])(
    "descarta em silêncio a série inválida %j e mostra a página normalmente",
    async (serie) => {
      const fetchMock = simularApi();
      renderizar([`/m/tres-passione?s=${serie}`]);
      expect(await screen.findByRole("heading", { level: 1, name: "TRES Passione" })).toBeInTheDocument();
      await waitFor(() => expect(chamadas(fetchMock, "POST", "/api/pub/jornadas")).toHaveLength(1));
      const [, init] = chamadas(fetchMock, "POST", "/api/pub/jornadas")[0];
      expect(JSON.parse(init!.body as string)).toEqual({ origem: "qr", modelo_id: "tres-passione" });
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    },
  );

  it("modelo não reconhecido: cria Jornada sem modelo e leva à busca com mensagem, sem mostrar a página", async () => {
    const fetchMock = simularApi({
      modelo: () => json({ erro: { codigo: "modelo_inexistente", mensagem: "Modelo inexistente." } }, 404),
    });
    const { router } = renderizar(["/m/tres-fantasma?s=ABC"]);

    expect(await screen.findByRole("heading", { level: 1, name: "Busca" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(MENSAGEM_MODELO_NAO_RECONHECIDO);
    expect(router.state.location.pathname).toBe("/");
    const [, init] = chamadas(fetchMock, "POST", "/api/pub/jornadas")[0];
    expect(JSON.parse(init!.body as string)).toEqual({ origem: "qr" });
    expect(screen.queryByRole("heading", { name: "TRES Passione" })).not.toBeInTheDocument();
  });

  it("modelo não reconhecido ainda leva à busca se a criação da Jornada falhar", async () => {
    simularApi({
      modelo: () => json({ erro: { codigo: "modelo_inexistente", mensagem: "x" } }, 404),
      jornada: () => json({ erro: { codigo: "x", mensagem: "falhou" } }, 500),
    });
    renderizar(["/m/tres-fantasma"]);
    expect(await screen.findByRole("heading", { level: 1, name: "Busca" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(MENSAGEM_MODELO_NAO_RECONHECIDO);
  });

  it("código ilegível leva à busca com mensagem, sem consultar a API", async () => {
    const fetchMock = simularApi();
    renderizar(["/m/TRES_Passione"]);
    expect(await screen.findByRole("heading", { level: 1, name: "Busca" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(MENSAGEM_CODIGO_ILEGIVEL);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("catálogo indisponível: avisa, não cria Jornada e permite tentar novamente", async () => {
    let tentativas = 0;
    const fetchMock = simularApi({
      modelo: () => {
        tentativas += 1;
        if (tentativas === 1) throw new TypeError("falha de rede");
        return json(MAQUINA);
      },
    });
    const { container } = renderizar();

    expect(await screen.findByText(MENSAGEM_INDISPONIVEL)).toBeInTheDocument();
    expect(chamadas(fetchMock, "POST", "/api/pub/jornadas")).toHaveLength(0);
    expect(await axe(container)).toHaveNoViolations();

    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(await screen.findByRole("heading", { level: 1, name: "TRES Passione" })).toBeInTheDocument();
    expect(screen.queryByText(MENSAGEM_INDISPONIVEL)).not.toBeInTheDocument();
    await waitFor(() => expect(chamadas(fetchMock, "POST", "/api/pub/jornadas")).toHaveLength(1));
  });

  it("erro do servidor no catálogo também é tratado como indisponibilidade", async () => {
    simularApi({ modelo: () => json({ erro: { codigo: "x", mensagem: "falhou" } }, 503) });
    renderizar();
    expect(await screen.findByText(MENSAGEM_INDISPONIVEL)).toBeInTheDocument();
  });
});

describe("escolha do problema", () => {
  it("registra o evento 'selecionado' e abre a instrução do problema", async () => {
    const fetchMock = simularApi();
    const { router } = renderizar();
    await userEvent.click(await screen.findByRole("button", { name: /Vazamento/ }));

    expect(await screen.findByRole("heading", { name: "Instrução" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/m/tres-passione/p/10");
    await waitFor(() => expect(chamadas(fetchMock, "POST", "/api/pub/jornadas/J1/eventos")).toHaveLength(1));
    const [, init] = chamadas(fetchMock, "POST", "/api/pub/jornadas/J1/eventos")[0];
    const corpo = JSON.parse(init!.body as string);
    expect(corpo).toMatchObject({ tipo: "selecionado", problema_id: 10 });
    expect(corpo.evento_id).toEqual(expect.any(String));
    expect(Number.isNaN(Date.parse(corpo.ocorrido_em))).toBe(false);
  });

  it("falha ao criar a Jornada não bloqueia a página; ao escolher, tenta de novo e avisa se continuar falhando", async () => {
    let criacoes = 0;
    simularApi({
      jornada: () => {
        criacoes += 1;
        return json({ erro: { codigo: "x", mensagem: "falhou" } }, 500);
      },
    });
    const { router } = renderizar();
    await userEvent.click(await screen.findByRole("button", { name: /Bico entupido/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(MENSAGEM_FALHA_SELECAO);
    expect(criacoes).toBe(2);
    expect(router.state.location.pathname).toBe("/m/tres-passione");
  });

  it("navegação dentro do Portal reaproveita a Jornada existente em vez de criar outra", async () => {
    sessionStorage.setItem("tres.jornada_id", "J0");
    const fetchMock = simularApi();
    renderizar(["/", "/m/tres-passione"], 1);

    await userEvent.click(await screen.findByRole("button", { name: /Luz amarela acesa/ }));
    await screen.findByRole("heading", { name: "Instrução" });
    await waitFor(() => expect(chamadas(fetchMock, "POST", "/api/pub/jornadas/J0/eventos")).toHaveLength(1));
    expect(chamadas(fetchMock, "POST", "/api/pub/jornadas")).toHaveLength(0);
  });

  it("'Meu problema não está na lista' leva ao formulário de abrir chamado com o contexto, mantendo a Jornada", async () => {
    const fetchMock = simularApi();
    const { router } = renderizar();
    const opcao = await screen.findByRole("button", { name: TEXTO_OUTRO_PROBLEMA });
    await waitFor(() => expect(sessionStorage.getItem("tres.jornada_id")).toBe("J1"));
    await userEvent.click(opcao);
    expect(await screen.findByRole("heading", { name: "Abrir um chamado" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/abrir-chamado");
    expect(router.state.location.state).toMatchObject({ categoria: "outro" });
    expect(router.state.location.state.contexto).toContain("tres-passione");
    expect(sessionStorage.getItem("tres.jornada_id")).toBe("J1");
    expect(chamadas(fetchMock, "POST", "/api/pub/jornadas")).toHaveLength(1);
  });
  it("recarregar o QR não cria uma segunda Jornada para o mesmo código", async () => {
    const fetchMock = simularApi();
    const primeira = renderizar(["/m/tres-passione?s=ABC"]);
    await waitFor(() => expect(sessionStorage.getItem("tres.jornada_qr")).not.toBeNull());
    primeira.unmount();

    renderizar(["/m/tres-passione?s=ABC"]);
    await screen.findByRole("heading", { level: 1, name: "TRES Passione" });
    expect(chamadas(fetchMock, "POST", "/api/pub/jornadas")).toHaveLength(1);
  });
});
