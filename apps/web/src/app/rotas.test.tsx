import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { describe, expect, it, vi } from "vitest";
import { Layout } from "./Layout";
import { PaginaErro } from "./PaginaErro";
import { rotas } from "./rotas";

function renderizar(caminho: string) {
  const router = createMemoryRouter(rotas, { initialEntries: [caminho] });
  return render(<RouterProvider router={router} />);
}

describe("rotas do front-end", () => {
  it.each([
    ["/", "Escolha a sua máquina"],
    ["/m/abc", "Sua máquina"],
    ["/m/abc/p/travou", "Como resolver"],
    ["/chamado", "Acompanhe o seu chamado"],
    ["/chamado/123", "Acompanhe o seu chamado"],
    ["/privacidade", "Aviso de privacidade"],
    ["/cs/fila", "Entrar no painel de atendimento"], // sem sessão, o Painel redireciona ao login
    ["/nao-existe", "Página não encontrada"],
  ])("carrega a página de %s por importação dinâmica", async (caminho, titulo) => {
    renderizar(caminho);
    expect(await screen.findByRole("heading", { level: 1, name: titulo })).toBeInTheDocument();
  });

  it("mostra a tela 'tentar novamente' quando uma página falha ao carregar", async () => {
    const erroConsole = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const router = createMemoryRouter(
      [
        {
          path: "/",
          Component: Layout,
          children: [
            {
              ErrorBoundary: PaginaErro,
              children: [{ index: true, lazy: () => Promise.reject(new Error("chunk")) }],
            },
          ],
        },
      ],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={router} />);
    expect(await screen.findByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
    erroConsole.mockRestore();
  });

  it("não tem violações de acessibilidade na página inicial", async () => {
    const { container } = renderizar("/");
    await screen.findByRole("heading", { level: 1 });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("declara viewport mobile-first sem bloquear o zoom", () => {
    const html = readFileSync(resolve(process.cwd(), "index.html"), "utf-8");
    expect(html).toContain('name="viewport" content="width=device-width, initial-scale=1"');
    expect(html).not.toMatch(/user-scalable\s*=\s*no|maximum-scale/);
    expect(html).toContain('lang="pt-BR"');
  });
});
