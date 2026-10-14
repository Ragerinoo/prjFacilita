import { useId } from "react";
import { formatarPercentual } from "./formatar";
import { SEM_DADOS, type ItemRanking } from "./tipos";

interface Props {
  itens: ItemRanking[];
}

function textoSolucao(solucao: ItemRanking["solucao_mais_registrada"]): string {
  if (solucao === SEM_DADOS) return SEM_DADOS;
  return `${solucao.solucao} (${solucao.solucao_tipo}, ${solucao.quantidade}×)`;
}

/** Ranking dos problemas mais selecionados, com Chamados e solução mais registrada. */
export function Ranking({ itens }: Props) {
  const idTitulo = useId();

  return (
    <section aria-labelledby={idTitulo} className="insights-secao">
      <h2 id={idTitulo}>Problemas mais frequentes</h2>
      {itens.length === 0 ? (
        <p>Não há dados para esta seção no período.</p>
      ) : (
        <table className="insights-tabela" aria-labelledby={idTitulo}>
          <thead>
            <tr>
              <th scope="col">Problema</th>
              <th scope="col">Seleções</th>
              <th scope="col">Chamados</th>
              <th scope="col">Falso defeito</th>
              <th scope="col">Solução mais registrada</th>
            </tr>
          </thead>
          <tbody>
            {itens.map((item) => (
              <tr key={item.problema_id}>
                <td>{item.titulo}</td>
                <td className="insights-tabela__numero">{item.selecoes}</td>
                <td className="insights-tabela__numero">{item.chamados}</td>
                <td className="insights-tabela__numero">{formatarPercentual(item.falso_defeito_pct)}</td>
                <td className="insights-tabela__texto">{textoSolucao(item.solucao_mais_registrada)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
