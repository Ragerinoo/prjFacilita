import type { CardChamado } from "./tipos";

/** Pacote_Repasse no topo do card (Req 14.3) e critério da decisão. */
export function ResumoPacote({ card }: { card: CardChamado }) {
  const p = card.pacote;
  return (
    <section aria-labelledby="chamado-pacote">
      <h2 id="chamado-pacote">Resumo do atendimento</h2>
      <p>{p.resumo}</p>
      <dl className="chamado__campos">
        <dt>Modelo</dt>
        <dd>{p.modelo}</dd>
        <dt>Número de série</dt>
        <dd>{p.numero_serie ?? "não informado"}</dd>
        <dt>Categoria</dt>
        <dd>{p.categoria}</dd>
        <dt>Classificação</dt>
        <dd>{p.classificacao}</dd>
        <dt>Canal recomendado</dt>
        <dd>{p.canal_recomendado}</dd>
        <dt>Sentimento</dt>
        <dd>{p.sentimento}</dd>
        <dt>Próxima ação sugerida</dt>
        <dd>{p.proxima_acao}</dd>
        <dt>Critério da decisão</dt>
        <dd>Critério {card.decisao_criterio}</dd>
      </dl>
      <h3>Já tentado</h3>
      {p.ja_tentado.length === 0 ? (
        <p>Nada foi tentado antes do repasse.</p>
      ) : (
        <ol>
          {p.ja_tentado.map((t, i) => (
            <li key={i}>
              {t.passo} ({t.camada}): {t.resultado}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
