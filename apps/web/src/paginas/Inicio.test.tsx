import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Component, MENSAGEM_CATALOGO_INDISPONIVEL, MENSAGEM_SEM_RESULTADO } from "./Inicio";

const CATALOGO = {
  modelos: [
    { modelo_id: "tres-passione", nome: "TRES Passione", foto_url: "/p.svg" },
    { modelo_id: "tres-circo", nome: "TRES Circo", foto_url: "/c.svg" },
    { modelo_id: "tres-mimo", nome: "TRES Mimo" },
  ],
};

function json(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
}

function renderizar(estado?: unknown) {
  const router = createMemoryRouter(
    [
      { path: "/", Component },
      { path: "/m/:modeloId", element: <p>Página da máquina</p> },
    ],
    { initialEntries: [{ pathname: "/", state: estado }] },
  );
  const resultado = render(<RouterProvider router={router} />);
  return { ...resultado, router };
}

const nomesNaGrade = () => screen.getAllByRole("button").map((b) => b.textContent?.trim());

beforeEach(() => sessionStorage.clear());
afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("página inicial e busca", () => {
  it("mostra a grade em ordem alfabética, campo com limite de 50 e sem violações de acessibilidade", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(CATALOGO)));
    const { container } = renderizar();
    await screen.findByRole("button", { name: "TRES Circo" });
    expect(nomesNaGrade()).toEqual(["TRES Circo", "TRES Mimo", "TRES Passione"]);
    expect(screen.getByLabelText("Nome da máquina")).toHaveAttribute("maxlength", "50");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("filtra a partir de 2 caracteres sem diferenciar caixa e acento e volta à grade completa ao apagar", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(CATALOGO)));
    renderizar();
    await screen.findByRole("button", { name: "TRES Circo" });
    const campo = screen.getByLabelText("Nome da máquina");

    await userEvent.type(campo, "p");
    expect(nomesNaGrade()).toHaveLength(3);

    await userEvent.type(campo, "ÁSSI");
    expect(nomesNaGrade()).toEqual(["TRES Passione"]);

    await userEvent.clear(campo);
    expect(nomesNaGrade()).toHaveLength(3);
  });

  it("sem resultado mostra a grade completa, a mensagem e mantém o texto digitado", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(CATALOGO)));
    renderizar();
    await screen.findByRole("button", { name: "TRES Circo" });
    const campo = screen.getByLabelText("Nome da máquina");
    await userEvent.type(campo, "xyz");
    expect(screen.getByText(MENSAGEM_SEM_RESULTADO)).toBeInTheDocument();
    expect(campo).toHaveValue("xyz");
    expect(nomesNaGrade()).toHaveLength(3);
  });

  it("troca a foto que não carrega por imagem substituta, mantendo nome e seleção", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(CATALOGO)));
    const { container } = renderizar();
    const botao = await screen.findByRole("button", { name: "TRES Circo" });
    const imagem = botao.querySelector("img");
    expect(imagem).not.toBeNull();
    imagem!.dispatchEvent(new Event("error"));
    await waitFor(() => expect(botao.querySelector("img")).toBeNull());
    expect(botao.querySelector('[data-testid="foto-substituta"]')).not.toBeNull();
    expect(screen.getByRole("button", { name: "TRES Circo" })).toBeEnabled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("catálogo indisponível desabilita o campo e permite tentar novamente", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("falha de rede"))
      .mockResolvedValueOnce(json(CATALOGO));
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderizar();

    expect(await screen.findByText(MENSAGEM_CATALOGO_INDISPONIVEL)).toBeInTheDocument();
    expect(screen.getByLabelText("Nome da máquina")).toBeDisabled();
    expect(await axe(container)).toHaveNoViolations();

    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    await screen.findByRole("button", { name: "TRES Circo" });
    expect(screen.getByLabelText("Nome da máquina")).toBeEnabled();
    expect(screen.queryByText(MENSAGEM_CATALOGO_INDISPONIVEL)).not.toBeInTheDocument();
  });

  it("ao selecionar um modelo registra a origem 'busca' e abre a página da máquina", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(CATALOGO))
      .mockResolvedValueOnce(json({ jornada_id: "J1" }, 201));
    vi.stubGlobal("fetch", fetchMock);
    const { router } = renderizar();
    await userEvent.click(await screen.findByRole("button", { name: "TRES Mimo" }));
    expect(await screen.findByText("Página da máquina")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/m/tres-mimo");
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/pub/jornadas");
    expect(JSON.parse(init.body)).toEqual({ modelo_id: "tres-mimo", origem: "busca" });
  });

  it("se o registro na Jornada falhar, avisa e permanece na busca", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(CATALOGO))
      .mockResolvedValueOnce(json({ erro: { codigo: "x", mensagem: "falhou" } }, 500));
    vi.stubGlobal("fetch", fetchMock);
    renderizar();
    await userEvent.click(await screen.findByRole("button", { name: "TRES Mimo" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível abrir essa máquina");
    expect(screen.getByRole("button", { name: "TRES Mimo" })).toBeEnabled();
  });

  it("exibe a mensagem recebida da Pagina_Maquina (QR não reconhecido)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(CATALOGO)));
    renderizar({ mensagem: "Não reconhecemos esse modelo." });
    expect(await screen.findByText("Não reconhecemos esse modelo.")).toBeInTheDocument();
  });
});
