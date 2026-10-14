import { useState } from "react";
import { caminhoAvaliacao, STATUS_ENCERRADO, type AgendamentoChamado, type ChamadoPublico } from "../../api/chamado";
import { AvaliacaoEstrelas } from "../../componentes/AvaliacaoEstrelas";
import { formatarDataHoraExtenso } from "./formatacao";

const ROTULOS_STATUS: Record<string, string> = {
  aberto: "Aberto. Estamos aguardando um atendente.",
  em_atendimento: "Em atendimento. Uma pessoa da nossa equipe está cuidando do seu chamado.",
  encerrado: "Encerrado.",
};

/** Situação atual do chamado (Req 12.8). Mudanças são anunciadas por leitores de tela. */
export function StatusChamado({ status }: { status?: string }) {
  const rotulo = status ? ROTULOS_STATUS[status] : undefined;
  if (!rotulo) return null;
  return (
    <section aria-labelledby="titulo-status" className="chamado__secao">
      <h2 id="titulo-status">Situação do chamado</h2>
      <p role="status" data-testid="status-chamado">
        {rotulo}
      </p>
    </section>
  );
}

/** Ligação agendada pelo Atendente (Req 15.6). Sem agendamento, não mostra nada. */
export function AgendamentoLigacao({ agendamento }: { agendamento: AgendamentoChamado | null }) {
  if (!agendamento) return null;
  return (
    <section aria-labelledby="titulo-agendamento" className="chamado__secao">
      <h2 id="titulo-agendamento">Ligação agendada</h2>
      <p>
        Vamos ligar para você em <time dateTime={agendamento.dataHora}>{formatarDataHoraExtenso(agendamento.dataHora)}</time>{" "}
        (horário de Brasília).
      </p>
    </section>
  );
}

/**
 * Avaliação de 1 a 5 estrelas ao encerrar (Req 16.5). A seção, uma vez exibida, fica na tela até a
 * página ser fechada, para a confirmação de envio não sumir quando o servidor passar a informar
 * `avaliacao_pendente: false`.
 */
export function AvaliacaoChamado({ chamado }: { chamado: ChamadoPublico }) {
  const oferecer = chamado.status === STATUS_ENCERRADO && chamado.avaliacaoPendente;
  const [exibir, setExibir] = useState(oferecer);
  if (oferecer && !exibir) setExibir(true);
  if (!exibir) return null;
  return (
    <section aria-labelledby="titulo-avaliacao" className="chamado__secao">
      <h2 id="titulo-avaliacao">Seu chamado foi encerrado</h2>
      <p>Conte para a gente como foi o atendimento.</p>
      <AvaliacaoEstrelas caminho={caminhoAvaliacao(chamado.numero)} />
    </section>
  );
}
