import { useId } from "react";
import { Bar, BarChart, LabelList, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { formatarPercentual, rotuloDesfecho } from "./formatar";
import type { ResumoDesfecho } from "./tipos";

interface Props {
  desfecho: ResumoDesfecho;
}

/**
 * Proporção de falso defeito x defeito real (Req 13.8, 14.1 a 14.3).
 *
 * Mesmo padrão de `GraficoDistribuicao`: SVG em `aria-hidden`, valores em `LabelList` e tabela
 * visível equivalente. A linha `nao_informado` só aparece (no gráfico e na tabela) quando a
 * quantidade é maior que 0.
 */
export function GraficoDesfecho({ desfecho }: Props) {
  const idTitulo = useId();
  const idLegenda = useId();
  const idDescricao = useId();
  const linhas = desfecho.itens.filter(
    (linha) => linha.desfecho !== "nao_informado" || linha.quantidade > 0,
  );
  const dados = linhas.map((linha) => ({
    rotulo: rotuloDesfecho(linha.desfecho),
    quantidade: linha.quantidade,
    valor: `${linha.quantidade} (${formatarPercentual(linha.percentual)})`,
  }));

  return (
    <section aria-labelledby={idTitulo} className="insights-secao">
      <h2 id={idTitulo}>Falso defeito x defeito real</h2>
      {desfecho.total <= 0 ? (
        <p>Não há dados para esta seção no período.</p>
      ) : (
        <>
          <figure
            className="insights-grafico"
            aria-labelledby={idLegenda}
            aria-describedby={idDescricao}
          >
            <figcaption id={idLegenda}>
              Gráfico de barras: Chamados encerrados por desfecho, falso defeito e defeito real
            </figcaption>
            <p id={idDescricao} className="insights-grafico__descricao">
              Cada barra mostra quantos Chamados encerrados no período tiveram aquele desfecho, com
              a quantidade e o percentual. Os mesmos valores estão na tabela abaixo.
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
                    <LabelList dataKey="valor" position="top" />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </figure>
          <table className="insights-tabela" aria-labelledby={idTitulo}>
            <thead>
              <tr>
                <th scope="col">Desfecho</th>
                <th scope="col">Chamados</th>
                <th scope="col">Percentual</th>
              </tr>
            </thead>
            <tbody>
              {linhas.map((linha) => (
                <tr key={linha.desfecho}>
                  <td>{rotuloDesfecho(linha.desfecho)}</td>
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
