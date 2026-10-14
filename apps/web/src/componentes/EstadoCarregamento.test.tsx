import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EstadoCarregamento } from "./EstadoCarregamento";

afterEach(() => {
  vi.useRealTimers();
});

describe("EstadoCarregamento", () => {
  it("mostra o conteúdo quando termina de carregar", () => {
    render(
      <EstadoCarregamento carregando={false}>
        <p>Conteúdo</p>
      </EstadoCarregamento>,
    );
    expect(screen.getByText("Conteúdo")).toBeInTheDocument();
  });

  it("mostra o erro com 'Tentar novamente' depois de 10 s carregando", () => {
    vi.useFakeTimers();
    render(
      <EstadoCarregamento carregando>
        <p>Conteúdo</p>
      </EstadoCarregamento>,
    );
    act(() => {
      vi.advanceTimersByTime(9999);
    });
    expect(screen.queryByRole("button", { name: "Tentar novamente" })).not.toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.getByRole("heading", { name: "A página não carregou" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });

  it("chama a ação de nova tentativa e não tem violações de acessibilidade", async () => {
    const aoTentarNovamente = vi.fn();
    const { container } = render(
      <EstadoCarregamento carregando={false} falhou aoTentarNovamente={aoTentarNovamente}>
        <p>Conteúdo</p>
      </EstadoCarregamento>,
    );
    expect(await axe(container)).toHaveNoViolations();
    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(aoTentarNovamente).toHaveBeenCalledTimes(1);
  });
});
