import { useState } from "react";
import { Cartoes } from "./Cartoes";
import { Comentarios } from "./Comentarios";
import { Funil } from "./Funil";
import { montarConsulta } from "./formatar";
import { GraficoDesfecho } from "./GraficoDesfecho";
import { GraficoDistribuicao } from "./GraficoDistribuicao";
import { Ranking } from "./Ranking";
import { SeletorPeriodo, type ConsultaPeriodo } from "./SeletorPeriodo";
import type { FonteInsights, RespostaInsights } from "./tipos";
import { CONSULTA_7D, useBuscaInsights } from "./useInsights";
import "../insights.css";

const CONSULTA_INICIAL: ConsultaPeriodo = { periodo: "7d" };

interface Props {
  /**
   * Busca de 7 dias já feita pelo pai (Dashboard). Enquanto o Período for 7 dias,
   * o conteúdo usa esta fonte e não envia outra requisição (design D12).
   */
  fonte7d?: FonteInsights;
  /** Omite o aviso "Dados de demonstração" quando a tela hospedeira já o mostra. */
  semAvisoDemo?: boolean;
}

/**
 * Conteúdo da Tela_Insights: seletor de Período, estados carregando/erro/pronto e
 * todas as seções. Usado por `/cs/insights` e pela aba "Insights" do Dashboard.
 * É o único ponto de entrada do Recharts (via `GraficoDistribuicao` e `GraficoDesfecho`).
 * Quem o usa fornece o `h1`; os títulos de seção daqui são `h2`.
 */
export function ConteudoInsights({ fonte7d, semAvisoDemo = false }: Props) {
  const [selecao, setSelecao] = useState<ConsultaPeriodo>(CONSULTA_INICIAL);
  const consulta = montarConsulta(selecao);
  const usaFonteDoPai = fonte7d !== undefined && consulta === CONSULTA_7D;
  const propria = useBuscaInsights(consulta, !usaFonteDoPai);
  const { estado, recarregar } = usaFonteDoPai ? fonte7d : propria;

  return (
    <>
      {!semAvisoDemo && estado.fase === "pronto" && estado.dados.modo_local && (
        <p className="insights-aviso">Dados de demonstração</p>
      )}
      <SeletorPeriodo consulta={selecao} aoMudar={setSelecao} />
      {estado.fase === "carregando" && <p role="status">Carregando os insights…</p>}
      {estado.fase === "erro" && (
        <div role="alert" className="insights-erro">
          <p>Não foi possível carregar os insights.</p>
          <button type="button" onClick={recarregar}>
            Tentar novamente
          </button>
        </div>
      )}
      {estado.fase === "pronto" && <ConteudoCompleto dados={estado.dados} />}
    </>
  );
}

function ConteudoCompleto({ dados }: { dados: RespostaInsights }) {
  return (
    <>
      <Cartoes dados={dados} />
      <GraficoDistribuicao distribuicao={dados.satisfacao.distribuicao} />
      <GraficoDesfecho desfecho={dados.desfecho} />
      <Ranking itens={dados.ranking_problemas} />
      <p className="insights-nota">Ranking por dia de calendário; datas em UTC.</p>
      <Comentarios comentarios={dados.comentarios} />
      {dados.funil !== null && <Funil funil={dados.funil} />}
    </>
  );
}
