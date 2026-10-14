import { useId } from "react";
import { Bar, BarChart, LabelList, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { formatarPercentual } from "./formatar";
import type { LinhaDistribuicao } from "./tipos";

interface Props {
  /** Sempre 5 linhas (notas 1 a 5), zeros incluídos. */
  distribuicao: LinhaDistribuicao[];
}

/**
 * Distribuição das notas de 1 a 5 (Req 13.8, 14.1 a 14.3).
 *
 * O gráfico é só reforço visual: o SVG fica em `aria-hidden` e a Alternativa_Textual é a
 * tabela visível logo abaixo, com os mesmos rótulos e números. Os valores também aparecem
 * sobre as barras (`LabelList`), então nada depende só de cor.
 * Este é, junto com `GraficoDesfecho`, o único módulo que importa `recharts`.
 */
export function GraficoDistribuicao({ distribuicao }: Props) {
  const idTitulo = useId();
  const idLegenda = useId();
  const idDescricao = useId();
  const total = distribuicao.reduce((soma, linha) => soma + linha.quantidade, 0);
  const dados = distribuicao.map((linha) => ({
    rotulo: `Nota ${linha.nota}`,
    quantidade: linha.quantidade,
  }));

  return (
    <section aria-labelledby={idTitulo} className="insights-secao">
      <h2 id={idTitulo}>Distribuição das notas</h2>
      {total <= 0 ? (
        <p>Não há dados para esta seção no período.</p>
      ) : (
        <>
          <figure
            className="insights-grafico"
            aria-labelledby={idLegenda}
            aria-describedby={idDescricao}
          >
            <figcaption id={idLegenda}>Gráfico de barras: quantidade de avaliações por nota, de 1 a 5</figcaption>
            <p id={idDescricao} className="insights-grafico__descricao">
              Cada barra mostra quantas avaliações receberam aquela nota no período. Os mesmos
              valores estão na tabela abaixo.
            </p>
            <div aria-hidden="true" className="insights-grafico__area">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart
                  data={dados}
                  accessibilityLayer={false}
                  margin={{ top: 24, right: 8, bottom: 0, left: 0 }}
                >
                  <XAxis dataKey="rotulo" />
                  <YAxis allowDecimals={false} />
                  <Bar
                    dataKey="quantidade"
                    fill="currentColor"
                    isAnimationActive={false}
                  >
                    <LabelList dataKey="quantidade" position="top" />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </figure>
          <table className="insights-tabela" aria-labelledby={idTitulo}>
            <thead>
              <tr>
                <th scope="col">Nota</th>
                <th scope="col">Avaliações</th>
                <th scope="col">Percentual</th>
              </tr>
            </thead>
            <tbody>
              {distribuicao.map((linha) => (
                <tr key={linha.nota}>
                  <td>{linha.nota}</td>
                  <td className="insights-tabela__numero">{linha.quantidade}</td>
                  <td className="insights-tabela__numero">{formatarPercentual(linha.percentual)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
