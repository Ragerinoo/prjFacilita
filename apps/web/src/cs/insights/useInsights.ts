import { useCallback, useEffect, useState } from "react";
import { apiCs } from "../clienteCs";
import { montarConsulta } from "./formatar";
import type { EstadoInsights, FonteInsights, RespostaInsights } from "./tipos";

/** Consulta dos 7 dias: usada pelos cards do Dashboard e pelo Período inicial da aba. */
export const CONSULTA_7D = montarConsulta({ periodo: "7d" });

type Resultado = { chave: string; fase: "erro" } | { chave: string; fase: "pronto"; dados: RespostaInsights };

/**
 * Busca `GET /api/cs/insights?<consulta>` (design D12).
 *
 * O estado é derivado da chave `consulta#tentativa`: um resultado só vale se a chave
 * dele é a da consulta atual. Assim, valores de outro Período ou de antes de
 * "Tentar novamente" nunca aparecem (Req 13.5) e não há `setState` síncrono no efeito.
 * Uma resposta atrasada não sobrescreve a nova: o cleanup aborta o pedido anterior.
 *
 * Com `ativo` falso o hook não envia nenhuma requisição (o Atendente nunca busca).
 */
export function useBuscaInsights(consulta: string, ativo = true): FonteInsights {
  const [tentativa, setTentativa] = useState(0);
  const chave = `${consulta}#${tentativa}`;
  const [resultado, setResultado] = useState<Resultado | null>(null);

  const estado: EstadoInsights =
    resultado !== null && resultado.chave === chave ? resultado : { fase: "carregando" };

  useEffect(() => {
    if (!ativo) return;
    const controle = new AbortController();
    apiCs
      .get<RespostaInsights>(`/insights?${consulta}`, { sinal: controle.signal })
      .then((dados) => {
        if (!controle.signal.aborted) setResultado({ chave, fase: "pronto", dados });
      })
      .catch(() => {
        if (!controle.signal.aborted) setResultado({ chave, fase: "erro" });
      });
    return () => controle.abort();
  }, [chave, consulta, ativo]);

  const recarregar = useCallback(() => setTentativa((n) => n + 1), []);
  return { estado, recarregar };
}
