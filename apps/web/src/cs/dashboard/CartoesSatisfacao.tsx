import { formatarDecimal } from "../insights/formatar";
import type { FonteInsights } from "../insights/tipos";

interface Props {
  /** Resposta de Insights (7 dias) já obtida pelo pai; este componente não faz requisição. */
  fonte: FonteInsights;
}

const PERIODO = "últimos 7 dias";

/**
 * Cards "Nota média" e "Tempo médio até assumir" do Gestor, com o período em texto.
 * `SEM_DADOS` ("sem dados") segue como a API devolveu, tanto na nota quanto no tempo.
 */
export function CartoesSatisfacao({ fonte }: Props) {
  const { estado, recarregar } = fonte;

  if (estado.fase === "carregando") {
    return (
      <p role="status" className="dashboard-estado">
        Carregando a satisfação e o atendimento…
      </p>
    );
  }

  if (estado.fase === "erro") {
    return (
      <div role="alert" className="dashboard-erro">
        <p>Não foi possível carregar a satisfação e o atendimento.</p>
        <button type="button" className="dashboard-botao" onClick={recarregar}>
          Tentar novamente
        </button>
      </div>
    );
  }

  const { satisfacao, atendimento } = estado.dados;
  return (
    <dl className="dashboard-cartoes">
      <div className="dashboard-cartao">
        <dt>Nota média</dt>
        <dd className="dashboard-cartao__valor">{formatarDecimal(satisfacao.nota_media)}</dd>
        <dd className="dashboard-cartao__detalhe">{PERIODO}</dd>
      </div>
      <div className="dashboard-cartao">
        <dt>Tempo médio até assumir</dt>
        <dd className="dashboard-cartao__valor">{atendimento.ate_assumir.media}</dd>
        <dd className="dashboard-cartao__detalhe">{PERIODO}</dd>
      </div>
    </dl>
  );
}
