import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { describe, expect, it } from "vitest";
import { Component, SECOES } from "./Privacidade";

function renderizar() {
  const router = createMemoryRouter([{ path: "/privacidade", Component }, { path: "/", element: <p>Início</p> }], {
    initialEntries: ["/privacidade"],
  });
  return render(<RouterProvider router={router} />);
}

describe("Aviso de privacidade", () => {
  it("explica dados coletados, finalidade, guarda e direitos", () => {
    renderizar();
    expect(screen.getByRole("heading", { level: 1, name: "Aviso de privacidade" })).toBeInTheDocument();
    for (const titulo of [
      "Quais dados pedimos",
      "Para que usamos",
      "Por quanto tempo guardamos",
      "Os seus direitos",
    ]) {
      expect(screen.getByRole("heading", { level: 2, name: titulo })).toBeInTheDocument();
    }
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(SECOES.length);
  });

  it("não tem violações de acessibilidade", async () => {
    const { container } = renderizar();
    expect(await axe(container)).toHaveNoViolations();
  });
});
