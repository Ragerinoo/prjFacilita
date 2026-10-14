import { enviarContato, enviarMensagem } from "./chamado";
import { api, type ClienteApi } from "./cliente";
import { novoUlid } from "./ulid";

/**
 * Abertura de chamado por formulário (sem IA), usando só rotas públicas que já existem:
 * `POST /jornadas` → `POST /jornadas/{id}/escalar` (`pedido_humano`, cria o Chamado na fila do CS)
 * → `POST /chamados/{numero}/mensagens` (respostas do formulário) → `POST /chamados/{numero}/contato`
 * (nome vai na mensagem; telefone vai para `dados_pessoais`, com consentimento).
 * O `progresso` guarda o que já deu certo, então "Tentar novamente" retoma do passo que falhou.
 */
export const CATEGORIAS = {
  nao_liga: "A máquina não liga",
  preparo: "Problema no preparo da bebida",
  vazamento: "Vazamento",
  ruido_cheiro: "Ruído ou cheiro estranho",
  erro_visor: "Erro no visor",
  limpeza: "Limpeza ou manutenção",
  outro: "Outro assunto",
} as const;
export type Categoria = keyof typeof CATEGORIAS;

export const URGENCIAS = {
  baixa: "Baixa (posso esperar)",
  media: "Média (atrapalha o uso)",
  alta: "Alta (não consigo usar a máquina)",
} as const;
export type Urgencia = keyof typeof URGENCIAS;

export const LIMITES = { descricao: 800, inicio: 150, jaTentou: 400, nome: 100 } as const;

export interface DadosAbertura {
  categoria: Categoria | "";
  urgencia: Urgencia | "";
  descricao: string;
  inicio: string;
  jaTentou: string;
  nome: string;
  telefone: string;
  /** De onde o cliente veio (fluxo/modelo); vai na mensagem ao CS, não é editável. */
  contexto?: string;
}

/** Contexto enviado por quem navegou até aqui (fluxo/modelo). Tudo opcional. */
export interface EstadoAbrirChamado {
  contexto?: string;
  categoria?: DadosAbertura["categoria"];
}

export interface ProgressoAbertura {
  chaveJornada: string;
  jornadaId?: string;
  numero?: string;
  mensagemEnviada?: boolean;
}

export function novoProgresso(): ProgressoAbertura {
  return { chaveJornada: novoUlid() };
}

/** Texto enviado ao CS como primeira mensagem do chamado (o servidor mascara PII). */
export function montarMensagem(d: DadosAbertura): string {
  const linhas = [
    `Assunto: ${d.categoria ? CATEGORIAS[d.categoria] : ""}`,
    `Urgência: ${d.urgencia ? URGENCIAS[d.urgencia] : ""}`,
    `Cliente: ${d.nome.trim()}`,
    `Descrição: ${d.descricao.trim()}`,
    `Quando começou: ${d.inicio.trim()}`,
    `O que já tentou: ${d.jaTentou.trim()}`,
  ];
  if (d.contexto?.trim()) linhas.push(`Origem: ${d.contexto.trim()}`);
  return linhas.join("\n");
}

/** Devolve o protocolo (número do chamado). Lança `ErroApi` no passo que falhar; `progresso` é mantido. */
export async function abrirChamado(
  dados: DadosAbertura,
  progresso: ProgressoAbertura,
  cliente: ClienteApi = api,
): Promise<string> {
  if (!progresso.jornadaId) {
    const criada = await cliente.post<{ jornada_id: string }>(
      "/jornadas",
      { origem: "busca" },
      { idempotencyKey: progresso.chaveJornada },
    );
    progresso.jornadaId = criada.jornada_id;
  }
  if (!progresso.numero) {
    const eventoId = novoUlid();
    const escalada = await cliente.post<{ numero: string }>(
      `/jornadas/${encodeURIComponent(progresso.jornadaId)}/escalar`,
      { motivo: "pedido_humano", evento_id: eventoId },
      { idempotencyKey: eventoId },
    );
    progresso.numero = escalada.numero;
  }
  if (!progresso.mensagemEnviada) {
    await enviarMensagem(progresso.numero, montarMensagem(dados), cliente);
    progresso.mensagemEnviada = true;
  }
  // O contato é repetível (upsert idempotente no servidor).
  await enviarContato(progresso.numero, { telefone: dados.telefone.trim() }, cliente);
  return progresso.numero;
}
