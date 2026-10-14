import { PRIORIDADES, type ChamadoPublico } from "../../api/chamado";

/** Confirmação do Chamado: número, prioridade em linguagem simples, prazo e canal (Req 12.1). */
export function ConfirmacaoChamado({ chamado }: { chamado: ChamadoPublico }) {
  const prioridade = PRIORIDADES[chamado.prioridade];
  return (
    <section aria-labelledby="titulo-confirmacao" className="chamado__secao">
      <h2 id="titulo-confirmacao">Recebemos o seu pedido</h2>
      <p>
        Número do chamado: <strong className="chamado__numero">{chamado.numero}</strong>
      </p>
      <p>Guarde este número para acompanhar o atendimento.</p>
      <dl className="chamado__dados">
        <dt>Tipo de atendimento</dt>
        <dd>{prioridade.rotulo}</dd>
        <dt>Próximo passo</dt>
        <dd>{prioridade.proximoPasso}</dd>
        {chamado.canal ? (
          <>
            <dt>Como vamos falar com você</dt>
            <dd>{chamado.canal}</dd>
          </>
        ) : null}
      </dl>
    </section>
  );
}
