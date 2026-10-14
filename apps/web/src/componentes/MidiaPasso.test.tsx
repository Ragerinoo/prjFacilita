import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it } from "vitest";
import type { PassoInstrucao } from "../api/instrucao";
import { MidiaPasso } from "./MidiaPasso";

const PASSO: PassoInstrucao = {
  n: 1,
  texto: "Encaixe o plugue na tomada.",
  alt: "Mão encaixando o plugue na tomada",
  texto_equivalente: "Passo 1: encaixe o plugue na tomada.",
  midia_url: "/midia/passo.svg",
  midia_tipo: "imagem",
};

describe("MidiaPasso", () => {
  it("mostra a imagem com texto alternativo e sem violações de acessibilidade", async () => {
    const { container } = render(<MidiaPasso passo={PASSO} reduzido={false} />);
    const imagem = screen.getByRole("img", { name: PASSO.alt });
    expect(imagem).toHaveAttribute("src", "/midia/passo.svg");
    fireEvent.load(imagem);
    expect(screen.queryByText("Carregando imagem…")).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("troca a imagem pelo texto alternativo se não carregar em 5 s (aqui, 40 ms)", async () => {
    render(<MidiaPasso passo={PASSO} reduzido={false} tempoMs={40} />);
    expect(screen.getByRole("img")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("img")).not.toBeInTheDocument());
    expect(screen.getByText(`Descrição da imagem: ${PASSO.alt}`)).toBeInTheDocument();
  });

  it("não troca depois que a imagem carregou", async () => {
    render(<MidiaPasso passo={PASSO} reduzido={false} tempoMs={40} />);
    fireEvent.load(screen.getByRole("img"));
    await new Promise((r) => setTimeout(r, 120));
    expect(screen.getByRole("img")).toBeInTheDocument();
  });

  it("troca pelo texto alternativo quando a imagem dá erro", () => {
    render(<MidiaPasso passo={PASSO} reduzido={false} />);
    fireEvent.error(screen.getByRole("img"));
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText(`Descrição da imagem: ${PASSO.alt}`)).toBeInTheDocument();
  });

  it("com movimento reduzido, usa a imagem estática no lugar da animação e do vídeo", () => {
    const animacao = { ...PASSO, midia_tipo: "animacao" as const, midia_url: "/a.gif", midia_estatica_url: "/a.png" };
    const { container, rerender } = render(<MidiaPasso passo={animacao} reduzido />);
    expect(screen.getByRole("img")).toHaveAttribute("src", "/a.png");
    rerender(<MidiaPasso passo={{ ...animacao, midia_tipo: "video", midia_url: "/v.mp4" }} reduzido />);
    expect(container.querySelector("video")).toBeNull();
    expect(screen.getByRole("img")).toHaveAttribute("src", "/a.png");
  });

  it("com movimento reduzido e sem imagem estática, mostra só o texto", () => {
    const video = { ...PASSO, midia_tipo: "video" as const, midia_url: "/v.mp4" };
    const { container } = render(<MidiaPasso passo={video} reduzido />);
    expect(container.querySelector("video")).toBeNull();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText(`Descrição da imagem: ${PASSO.alt}`)).toBeInTheDocument();
  });

  it("sem movimento reduzido, o vídeo tem controles e começa mudo", () => {
    const video = { ...PASSO, midia_tipo: "video" as const, midia_url: "/v.mp4" };
    const { container } = render(<MidiaPasso passo={video} reduzido={false} />);
    const elemento = container.querySelector("video");
    expect(elemento).not.toBeNull();
    expect(elemento).toHaveAttribute("controls");
    expect(elemento?.muted).toBe(true);
  });
});
