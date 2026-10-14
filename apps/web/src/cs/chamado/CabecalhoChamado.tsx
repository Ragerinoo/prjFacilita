import { ROTULO_PRIORIDADE, ROTULO_STATUS, type CardChamado } from "./tipos";

/** Número, prioridade (texto + cor), status, responsável e indicador de resposta não lida. */
export function CabecalhoChamado({ card }: { card: CardChamado }) {
  return (
    <header className="chamado__cabecalho">
      <h1>Chamado {card.numero}</h1>
      <ul className="chamado__chips">
        <li>
          <span className={`chamado__prioridade chamado__prioridade--${card.prioridade}`}>
            Prioridade: {ROTULO_PRIORIDADE[card.prioridade]}
          </span>
        </li>
        <li>Status: {ROTULO_STATUS[card.status] ?? card.status}</li>
        <li>Responsável: {card.responsavel ? card.responsavel.nome : "ninguém assumiu"}</li>
        <li>Canal: {card.canal}</li>
        {card.resposta_nao_lida && (
          <li>
            <strong>Resposta do consumidor não lida</strong>
          </li>
        )}
      </ul>
    </header>
  );
}
