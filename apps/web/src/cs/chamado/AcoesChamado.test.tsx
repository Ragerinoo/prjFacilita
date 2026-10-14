import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AcoesChamado } from "./AcoesChamado";
import type { CardChamado } from "./tipos";

function json(corpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
}

const CARD = {
  numero: "TRES-ABC123",
  status: "aberto",
  os_status: null,
  agendamento: null,
} as unknown as CardChamado;

function simular(rotas: Record<string, () => Response>) {
  const f = vi.fn(async (entrada: RequestInfo | URL, init?: RequestInit) => {
    const chave = `${init?.method ?? "GET"} ${String(entrada)}`;
    const r = rotas[chave];
    return r ? r() : json({ erro: { codigo: "nao_encontrado", mensagem: "?" } }, 404);
  });
  vi.stubGlobal("fetch", f);
  return f;
}

afterEach(() => vi.unstubAllGlobals());

describe("AcoesChamado", () => {
  it("mostra sugestão editável e mantém o texto quando o envio falha com 409", async () => {
    simular({
      "GET /api/cs/chamados/TRES-ABC123/sugestao": () => json({ sugestao: "Olá, vamos ajudar", origem: "ia", mensagem: null }),
      "POST /api/cs/chamados/TRES-ABC123/mensagens": () =>
        json({ erro: { codigo: "outro_responsavel", mensagem: "Este Chamado está com Ana." } }, 409),
    });
    const aoAtualizar = vi.fn();
    render(<AcoesChamado card={CARD} aoAtualizar={aoAtualizar} />);
    const campo = await screen.findByLabelText(/Mensagem \(sugestão/);
    await waitFor(() => expect((campo as HTMLTextAreaElement).value).toBe("Olá, vamos ajudar"));
    await userEvent.click(screen.getByRole("button", { name: "Enviar mensagem" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirmar envio" }));
    expect(await screen.findByText("Este Chamado está com Ana.")).toBeTruthy();
    expect((campo as HTMLTextAreaElement).value).toBe("Olá, vamos ajudar");
  });

  it("deixa o campo vazio quando a sugestão está indisponível", async () => {
    simular({
      "GET /api/cs/chamados/TRES-ABC123/sugestao": () =>
        json({ sugestao: null, origem: null, mensagem: "sugestão indisponível" }),
    });
    render(<AcoesChamado card={CARD} aoAtualizar={vi.fn()} />);
    expect(await screen.findByText("sugestão indisponível")).toBeTruthy();
    expect((screen.getByLabelText(/Mensagem \(sugestão/) as HTMLTextAreaElement).value).toBe("");
  });

  it("oferece o Cache_Respostas após encerrar falso defeito com instrução do manual", async () => {
    simular({
      "GET /api/cs/chamados/TRES-ABC123/sugestao": () => json({ sugestao: null, origem: null, mensagem: "x" }),
      "POST /api/cs/chamados/TRES-ABC123/encerrar": () => json({ oferecer_cache: true }),
      "POST /api/cs/cache": () => json({ criada: true, ja_existe: false }, 201),
    });
    const aoAtualizar = vi.fn();
    render(<AcoesChamado card={CARD} aoAtualizar={aoAtualizar} />);
    await userEvent.selectOptions(screen.getByLabelText("Desfecho"), "falso_defeito");
    await userEvent.selectOptions(screen.getByLabelText("Tipo de solução"), "instrução do manual");
    await userEvent.type(screen.getByLabelText("Descrição da solução"), "Reiniciar");
    await userEvent.click(screen.getByRole("button", { name: "Encerrar Chamado" }));
    await userEvent.type(await screen.findByLabelText("Pergunta"), "Como reiniciar?");
    await userEvent.type(screen.getByLabelText("Resposta"), "Desligue e ligue.");
    await userEvent.click(screen.getByRole("button", { name: "Adicionar ao Cache_Respostas" }));
    expect(await screen.findByText("Adicionado ao Cache_Respostas.")).toBeTruthy();
  });
});
