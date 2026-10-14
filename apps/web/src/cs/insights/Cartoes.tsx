import { useId } from "react";
import { formatarDecimal, formatarPercentual } from "./formatar";
import type { RespostaInsights } from "./tipos";

interface Props {
  dados: RespostaInsights;
}

interface Cartao {
  chave: string;
  rotulo: string;
  valor: string;
  detalhe?: string;
}

function textoQuantidade(quantidade: number, singular: string, plural: string): string {
  return `${quantidade} ${quantidade === 1 ? singular : plural}`;
}

function montarCartoes(dados: RespostaInsights): Cartao[] {
  const { satisfacao, atendimento, p1_risco, desfecho } = dados;
  const falso = desfecho.itens.find((i) => i.desfecho === "falso_defeito");
  return [
    {
      chave: "nota",
      rotulo: "Nota média",
      valor: formatarDecimal(satisfacao.nota_media),
    },
    {
      chave: "avaliacoes",
      rotulo: "Avaliações",
      valor: String(satisfacao.total),
    },
    {
      chave: "assumir",
      rotulo: "Tempo até assumir (média)",
      valor: atendimento.ate_assumir.media,
      detalhe: `Mediana: ${atendimento.ate_assumir.mediana} (${textoQuantidade(
        atendimento.ate_assumir.quantidade,
        "chamado",
        "chamados",
      )})`,
    },
    {
      chave: "encerrar",
      rotulo: "Tempo até encerrar (média)",
      valor: atendimento.ate_encerrar.media,
      detalhe: `Mediana: ${atendimento.ate_encerrar.mediana} (${textoQuantidade(
        atendimento.ate_encerrar.quantidade,
        "chamado",
        "chamados",
      )})`,
    },
    {
      chave: "p1",
      rotulo: "Chamados P1 de risco",
      valor: String(p1_risco.total),
      detalhe: `Ainda não encerrados: ${p1_risco.nao_encerrados}`,
    },
    {
      chave: "falso",
      rotulo: "Falso defeito",
      valor: formatarPercentual(falso?.percentual ?? "sem dados"),
    },
  ];
}

/** Cards de satisfação e atendimento; só exibe valores devolvidos pela API. */
export function Cartoes({ dados }: Props) {
  const idTitulo = useId();
  const cartoes = montarCartoes(dados);

  return (
    <section aria-labelledby={idTitulo} className="insights-secao">
      <h2 id={idTitulo} className="insights-somente-leitor">
        Resumo do período
      </h2>
      <dl className="insights-cartoes">
        {cartoes.map((c) => (
          <div key={c.chave} className="insights-cartao">
            <dt>{c.rotulo}</dt>
            <dd className="insights-cartao__valor">{c.valor}</dd>
            {c.detalhe !== undefined && <dd className="insights-cartao__detalhe">{c.detalhe}</dd>}
          </div>
        ))}
      </dl>
    </section>
  );
}
