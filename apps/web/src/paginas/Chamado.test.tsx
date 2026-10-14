import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MENSAGEM_FALHA_FOTO } from "../api/chamado";
import {
  MENSAGEM_CEP_INVALIDO,
  MENSAGEM_FOTO_FORMATO,
  MENSAGEM_FOTO_LIMITE,
  MENSAGEM_FOTO_TAMANHO,
  MENSAGEM_TELEFONE_INVALIDO,
} from "../api/validacaoContato";
import { Component, MENSAGEM_CHAMADO_NAO_ENCONTRADO, MENSAGEM_ERRO_CHAMADO } from "./Chamado";
import { FINALIDADES, MENSAGEM_CONTATO_ENVIADO, MENSAGEM_FALHA_CONTATO } from "./chamado/ContatoChamado";

const NUMERO = "TRES-7K3M9QX2PD";
const URL_S3 = "https://bucket.s3.amazonaws.com/";

const json = (corpo: unknown, status = 200) =>
  new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });
const erro = (status: number, mensagem = "falhou", campos?: unknown) =>
  json({ erro: { codigo: "x", mensagem, campos } }, status);

type Manipulador = (url: string, init: RequestInit) => Response | Promise<Response>;

function simularApi(rotas: Record<string, Manipulador>) {
  const fetchMock = vi.fn(async (url: string, init: RequestInit = {}) => {
    const manipulador = rotas[`${init.method ?? "GET"} ${url.split("?")[0]}`];
    return manipulador ? manipulador(url, init) : json({}, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const chamado = (extra: Record<string, unknown> = {}) => ({
  numero: NUMERO,
  status: "aberto",
  prioridade: "P2",
  canal: "chat ou ligação, à escolha do Consumidor",
  anexos_total: 0,
  ...extra,
});
const rotaChamado = (corpo: unknown, status = 200): Record<string, Manipulador> => ({
  [`GET /api/pub/chamados/${NUMERO}`]: () => json(corpo, status),
});

function renderizar() {
  const router = createMemoryRouter(
    [
      { path: "/chamado/:numero", Component },
      { path: "/privacidade", element: <h1>Aviso de privacidade</h1> },
    ],
    { initialEntries: [`/chamado/${NUMERO}`] },
  );
  return render(<RouterProvider router={router} />);
}

const chamadas = (fetchMock: ReturnType<typeof simularApi>, metodo: string, caminho: string) =>
  fetchMock.mock.calls.filter(([url, init]) => url.split("?")[0] === caminho && (init?.method ?? "GET") === metodo);
const corpoJson = (chamada: [string, RequestInit?] | undefined) => JSON.parse(String(chamada?.[1]?.body));

function foto(nome: string, tipo: string, bytes = 1000) {
  const arquivo = new File(["x"], nome, { type: tipo });
  Object.defineProperty(arquivo, "size", { value: bytes });
  return arquivo;
}

afterEach(() => vi.unstubAllGlobals());

describe("confirmação do Chamado", () => {
  it("mostra número, prioridade em linguagem simples, prazo e canal, sem siglas", async () => {
    simularApi(rotaChamado(chamado()));
    renderizar();
    expect(await screen.findByText(NUMERO)).toBeInTheDocument();
    expect(screen.getByText("Atendimento prioritário")).toBeInTheDocument();
    expect(screen.getByText(/em até 4 horas úteis/)).toBeInTheDocument();
    expect(screen.getByText(/chat ou ligação/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\bP[123]\b/);
  });

  it.each([
    ["P1", "Atendimento urgente", /ligar para você em até 15 minutos/],
    ["P3", "Atendimento comum", /em até 1 dia útil/],
  ])("traduz a prioridade %s", async (prioridade, rotulo, prazo) => {
    simularApi(rotaChamado(chamado({ prioridade })));
    renderizar();
    expect(await screen.findByText(rotulo)).toBeInTheDocument();
    expect(screen.getByText(prazo)).toBeInTheDocument();
  });

  it("explica que o Chamado não foi encontrado, sem mostrar dados", async () => {
    simularApi(rotaChamado({ erro: { codigo: "chamado_nao_encontrado", mensagem: "x" } }, 404));
    renderizar();
    expect(await screen.findByText(MENSAGEM_CHAMADO_NAO_ENCONTRADO)).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.queryByText(NUMERO)).not.toBeInTheDocument();
  });

  it("oferece 'Tentar novamente' em falha do servidor", async () => {
    let falhar = true;
    simularApi({
      [`GET /api/pub/chamados/${NUMERO}`]: () => (falhar ? erro(500) : json(chamado())),
    });
    renderizar();
    expect(await screen.findByText(MENSAGEM_ERRO_CHAMADO)).toBeInTheDocument();
    falhar = false;
    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(await screen.findByText(NUMERO)).toBeInTheDocument();
  });
});

describe("formulário de contato", () => {
  it("P2 pede telefone e CEP, com finalidade, consentimento desmarcado e link de privacidade", async () => {
    simularApi(rotaChamado(chamado({ dados_solicitados: ["telefone", "cep"] })));
    renderizar();
    const telefone = await screen.findByLabelText("Telefone com DDD");
    expect(telefone).toHaveAccessibleDescription(FINALIDADES.telefone);
    expect(screen.getByLabelText("CEP")).toHaveAccessibleDescription(FINALIDADES.cep);
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Enviar" })).toBeDisabled();
    const link = screen.getByRole("link", { name: /aviso de privacidade/ });
    expect(link).toHaveAttribute("href", "/privacidade");
    expect(screen.getByTestId("aviso-prazo")).toHaveTextContent(/não conseguimos garantir o contato no prazo/);
  });

  it("P1 pede só o telefone", async () => {
    simularApi(rotaChamado(chamado({ prioridade: "P1", dados_solicitados: ["telefone"] })));
    renderizar();
    await screen.findByLabelText("Telefone com DDD");
    expect(screen.queryByLabelText("CEP")).not.toBeInTheDocument();
  });

  it("não pede de novo o dado já informado (só o CEP)", async () => {
    simularApi(rotaChamado(chamado({ dados_solicitados: ["cep"] })));
    renderizar();
    await screen.findByLabelText("CEP");
    expect(screen.queryByLabelText("Telefone com DDD")).not.toBeInTheDocument();
  });

  it("calcula pela prioridade quando a resposta não traz dados_solicitados", async () => {
    simularApi(rotaChamado(chamado({ dados_informados: ["telefone"] })));
    renderizar();
    await screen.findByLabelText("CEP");
    expect(screen.queryByLabelText("Telefone com DDD")).not.toBeInTheDocument();
  });

  it("P3 e nada faltando não mostram formulário nem aviso de prazo", async () => {
    simularApi(rotaChamado(chamado({ prioridade: "P3", dados_solicitados: [] })));
    renderizar();
    await screen.findByText(NUMERO);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByTestId("aviso-prazo")).not.toBeInTheDocument();
  });

  it("rejeita telefone e CEP inválidos, mostra o formato junto ao campo e mantém o digitado", async () => {
    const api = simularApi(rotaChamado(chamado({ dados_solicitados: ["telefone", "cep"] })));
    renderizar();
    const usuario = userEvent.setup();
    const telefone = await screen.findByLabelText("Telefone com DDD");
    const cep = screen.getByLabelText("CEP");
    await usuario.type(telefone, "1199");
    await usuario.type(cep, "0131x-100");
    await usuario.click(screen.getByRole("checkbox"));
    await usuario.click(screen.getByRole("button", { name: "Enviar" }));
    expect(telefone).toHaveAccessibleDescription(new RegExp(MENSAGEM_TELEFONE_INVALIDO.slice(0, 30)));
    expect(screen.getByText(MENSAGEM_TELEFONE_INVALIDO)).toBeInTheDocument();
    expect(screen.getByText(MENSAGEM_CEP_INVALIDO)).toBeInTheDocument();
    expect(telefone).toHaveValue("1199");
    expect(cep).toHaveValue("0131x-100");
    expect(telefone).toHaveFocus();
    expect(chamadas(api, "POST", `/api/pub/chamados/${NUMERO}/contato`)).toHaveLength(0);
  });

  it("envia só com consentimento, com os campos pedidos, e confirma", async () => {
    const api = simularApi({
      ...rotaChamado(chamado({ dados_solicitados: ["telefone", "cep"] })),
      [`POST /api/pub/chamados/${NUMERO}/contato`]: () => json({ dados_solicitados: [] }),
    });
    renderizar();
    const usuario = userEvent.setup();
    await usuario.type(await screen.findByLabelText("Telefone com DDD"), "(11) 91234-5678");
    await usuario.type(screen.getByLabelText("CEP"), "01310-100");
    await usuario.click(screen.getByRole("checkbox"));
    await usuario.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByText(MENSAGEM_CONTATO_ENVIADO)).toBeInTheDocument();
    const corpo = corpoJson(chamadas(api, "POST", `/api/pub/chamados/${NUMERO}/contato`)[0]);
    expect(corpo).toMatchObject({ telefone: "(11) 91234-5678", cep: "01310-100", consentimento: true });
    expect(screen.queryByLabelText("CEP")).not.toBeInTheDocument();
    expect(screen.queryByTestId("aviso-prazo")).not.toBeInTheDocument();
  });

  it("aceita enviar só o telefone e continua pedindo o CEP, com o aviso de prazo", async () => {
    simularApi({
      ...rotaChamado(chamado({ dados_solicitados: ["telefone", "cep"] })),
      [`POST /api/pub/chamados/${NUMERO}/contato`]: () => json({ dados_solicitados: ["cep"] }),
    });
    renderizar();
    const usuario = userEvent.setup();
    await usuario.type(await screen.findByLabelText("Telefone com DDD"), "11912345678");
    await usuario.click(screen.getByRole("checkbox"));
    await usuario.click(screen.getByRole("button", { name: "Enviar" }));
    await waitFor(() => expect(screen.queryByLabelText("Telefone com DDD")).not.toBeInTheDocument());
    expect(screen.getByLabelText("CEP")).toBeInTheDocument();
    expect(screen.getByTestId("aviso-prazo")).toHaveTextContent("Sem o CEP");
  });

  it("mostra o erro do servidor junto ao campo e mantém o digitado", async () => {
    simularApi({
      ...rotaChamado(chamado({ prioridade: "P1", dados_solicitados: ["telefone"] })),
      [`POST /api/pub/chamados/${NUMERO}/contato`]: () =>
        erro(422, "inválido", [{ campo: "telefone", motivo: "Telefone inválido no servidor." }]),
    });
    renderizar();
    const usuario = userEvent.setup();
    const telefone = await screen.findByLabelText("Telefone com DDD");
    await usuario.type(telefone, "11912345678");
    await usuario.click(screen.getByRole("checkbox"));
    await usuario.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByText("Telefone inválido no servidor.")).toBeInTheDocument();
    expect(telefone).toHaveValue("11912345678");
  });

  it("avisa de falha de rede e mantém o digitado", async () => {
    simularApi({
      ...rotaChamado(chamado({ prioridade: "P1", dados_solicitados: ["telefone"] })),
      [`POST /api/pub/chamados/${NUMERO}/contato`]: () => erro(503),
    });
    renderizar();
    const usuario = userEvent.setup();
    const telefone = await screen.findByLabelText("Telefone com DDD");
    await usuario.type(telefone, "11912345678");
    await usuario.click(screen.getByRole("checkbox"));
    await usuario.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByText(MENSAGEM_FALHA_CONTATO)).toBeInTheDocument();
    expect(telefone).toHaveValue("11912345678");
    expect(screen.getByRole("checkbox")).toBeChecked();
  });
});

describe("fotos do Chamado", () => {
  const rotasFoto = (extra: Record<string, Manipulador> = {}): Record<string, Manipulador> => {
    let total = 0;
    return {
      ...rotaChamado(chamado({ prioridade: "P3", dados_solicitados: [] })),
      [`POST /api/pub/chamados/${NUMERO}/anexos`]: () =>
        json({ anexo_id: `A${total + 1}`, upload: { url: URL_S3, campos: { key: `fotos/${total + 1}`, "Content-Type": "image/png" } } }, 201),
      [`POST ${URL_S3}`]: () => new Response(null, { status: 204 }),
      [`POST /api/pub/chamados/${NUMERO}/anexos/A1/confirmacao`]: () => json({ anexos_total: ++total }),
      [`POST /api/pub/chamados/${NUMERO}/anexos/A2/confirmacao`]: () => json({ anexos_total: ++total }),
      [`POST /api/pub/chamados/${NUMERO}/anexos/A3/confirmacao`]: () => json({ anexos_total: ++total }),
      ...extra,
    };
  };

  it("pede o destino, envia ao S3 com o arquivo por último e confirma", async () => {
    const api = simularApi(rotasFoto());
    renderizar();
    const usuario = userEvent.setup();
    await usuario.upload(await screen.findByLabelText("Escolher fotos"), foto("pia.png", "image/png"));
    expect(await screen.findByText(/pia\.png: anexada/)).toBeInTheDocument();
    expect(screen.getByText("Fotos anexadas: 1 de 3")).toBeInTheDocument();
    const pedido = corpoJson(chamadas(api, "POST", `/api/pub/chamados/${NUMERO}/anexos`)[0]);
    expect(pedido).toMatchObject({ mime: "image/png", bytes: 1000 });
    const envio = chamadas(api, "POST", URL_S3)[0];
    const campos = [...(envio[1]?.body as FormData).keys()];
    expect(campos).toEqual(["key", "Content-Type", "file"]);
  });

  it("rejeita só a foto de formato ou tamanho inválido e mantém as anexadas", async () => {
    simularApi(rotasFoto());
    renderizar();
    const usuario = userEvent.setup({ applyAccept: false });
    await usuario.upload(await screen.findByLabelText("Escolher fotos"), [
      foto("boa.jpg", "image/jpeg"),
      foto("animada.gif", "image/gif"),
      foto("enorme.png", "image/png", 5 * 1024 * 1024 + 1),
    ]);
    expect(await screen.findByText(/boa\.jpg: anexada/)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`animada\\.gif: não anexada. ${MENSAGEM_FOTO_FORMATO}`))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`enorme\\.png: não anexada. ${MENSAGEM_FOTO_TAMANHO}`))).toBeInTheDocument();
    expect(screen.getByText("Fotos anexadas: 1 de 3")).toBeInTheDocument();
    expect(screen.getByText(NUMERO)).toBeInTheDocument();
  });

  it("recusa a quarta foto", async () => {
    simularApi(rotasFoto());
    renderizar();
    const usuario = userEvent.setup();
    await usuario.upload(
      await screen.findByLabelText("Escolher fotos"),
      ["a", "b", "c", "d"].map((n) => foto(`${n}.png`, "image/png")),
    );
    expect(await screen.findByText(new RegExp(`d\\.png: não anexada. ${MENSAGEM_FOTO_LIMITE}`))).toBeInTheDocument();
    expect(screen.getByText("Fotos anexadas: 3 de 3")).toBeInTheDocument();
  });

  it("rejeita só a foto cujo envio falha", async () => {
    simularApi(rotasFoto({ [`POST ${URL_S3}`]: () => new Response("", { status: 500 }) }));
    renderizar();
    const usuario = userEvent.setup();
    await usuario.upload(await screen.findByLabelText("Escolher fotos"), foto("pia.png", "image/png"));
    const item = await screen.findByText(/pia\.png: não anexada/);
    expect(item).toHaveTextContent(MENSAGEM_FALHA_FOTO);
    expect(screen.getByText("Fotos anexadas: 0 de 3")).toBeInTheDocument();
    expect(screen.getByText(NUMERO)).toBeInTheDocument();
  });

  it("mostra o motivo dado pelo servidor ao recusar a foto", async () => {
    simularApi(
      rotasFoto({
        [`POST /api/pub/chamados/${NUMERO}/anexos`]: () => erro(422, "A foto parece corrompida."),
      }),
    );
    renderizar();
    const usuario = userEvent.setup();
    await usuario.upload(await screen.findByLabelText("Escolher fotos"), foto("pia.png", "image/png"));
    expect(await screen.findByText(/A foto parece corrompida\./)).toBeInTheDocument();
  });
});

describe("acessibilidade", () => {
  it("a página com formulário e fotos não tem violações", async () => {
    simularApi(rotaChamado(chamado({ dados_solicitados: ["telefone", "cep"] })));
    const { container } = renderizar();
    await screen.findByLabelText("Telefone com DDD");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("a página com erros de campo não tem violações", async () => {
    simularApi(rotaChamado(chamado({ dados_solicitados: ["telefone"], prioridade: "P1" })));
    const { container } = renderizar();
    const usuario = userEvent.setup();
    await usuario.type(await screen.findByLabelText("Telefone com DDD"), "1");
    await usuario.click(screen.getByRole("checkbox"));
    await usuario.click(screen.getByRole("button", { name: "Enviar" }));
    const secao = (await screen.findByText(MENSAGEM_TELEFONE_INVALIDO)).closest("section");
    expect(secao && within(secao).getByLabelText("Telefone com DDD")).toHaveAttribute("aria-invalid", "true");
    expect(await axe(container)).toHaveNoViolations();
  });
});
