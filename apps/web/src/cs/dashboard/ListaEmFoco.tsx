/**
 * Lista dos Chamados em foco do Dashboard (spec insights-gestor, D11; Req 24.6 a 24.11, 24.13).
 *
 * - Mantém a ordem recebida da API; não reordena.
 * - Prioridade e motivos saem em texto, nunca só por cor (a borda por prioridade é reforço no CSS).
 * - Todo texto entra como `{valor}` do React (escapado); sem `dangerouslySetInnerHTML`.
 * - A lista não é região `aria-live`: não se narra a lista a cada atualização de 10 s.
 * - `key={numero}` reaproveita os nós na atualização, e o foco num link sobrevive a ela.
 */
import { useId } from "react";
import { Link } from "react-router";
import type { EstadoDashboard } from "./useDashboard";
import {
  formatarIdade,
  rotuloInformacao,
  rotuloMotivo,
  rotuloPrioridade,
  rotuloStatus,
} from "./formatar";

export interface PropsListaEmFoco {
  /** Estado do `useDashboard()`: carregando, erro ou pronto (com `dados`). */
  estado: EstadoDashboard;
  /** "Tentar novamente" do erro; é o `tentarDeNovo` do `useDashboard()`. */
  aoTentarDeNovo: () => void;
}

export function ListaEmFoco({ estado, aoTentarDeNovo }: PropsListaEmFoco) {
  const idTitulo = useId();

  return (
    <section className="dashboard-foco" aria-labelledby={idTitulo}>
      <h2 id={idTitulo} className="dashboard-foco__titulo">
        Chamados em foco
      </h2>

      {estado.fase === "carregando" && (
        <p role="status" className="dashboard-foco__carregando">
          Carregando os chamados em foco…
        </p>
      )}

      {estado.fase === "erro" && (
        <div role="alert" className="dashboard-foco__erro">
          <p>Não foi possível carregar os chamados em foco.</p>
          <button type="button" onClick={aoTentarDeNovo}>
            Tentar novamente
          </button>
        </div>
      )}

      {estado.fase === "pronto" && (
        <>
          {estado.dados.em_foco.itens.length === 0 ? (
            <p className="dashboard-foco__vazio">Nenhum chamado pede atenção agora</p>
          ) : (
            <ul className="dashboard-foco__lista" aria-labelledby={idTitulo}>
              {estado.dados.em_foco.itens.map((item) => (
                <li
                  key={item.numero}
                  className={`dashboard-foco__item dashboard-foco__item--${item.prioridade.toLowerCase()}`}
                >
                  <p className="dashboard-foco__linha">
                    <span className="dashboard-foco__prioridade">
                      {rotuloPrioridade(item.prioridade)}
                    </span>{" "}
                    <Link
                      className="dashboard-foco__numero"
                      to={`/cs/chamados/${encodeURIComponent(item.numero)}`}
                    >
                      {item.numero}
                    </Link>{" "}
                    <span className="dashboard-foco__status">{rotuloStatus(item.status)}</span>
                  </p>
                  <p className="dashboard-foco__detalhe">
                    <span className="dashboard-foco__modelo">{rotuloInformacao(item.modelo)}</span>
                    {" · "}
                    <span className="dashboard-foco__problema">
                      {rotuloInformacao(item.problema)}
                    </span>
                    {" · "}
                    <span className="dashboard-foco__idade">{formatarIdade(item.idade_min)}</span>
                  </p>
                  <ul
                    className="dashboard-foco__motivos"
                    aria-label={`Motivos do chamado ${item.numero}`}
                  >
                    {item.motivos.map((motivo) => (
                      <li key={motivo} className="dashboard-foco__motivo">
                        {rotuloMotivo(motivo)}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          )}

          {estado.dados.em_foco.total > estado.dados.em_foco.itens.length && (
            <p className="dashboard-foco__contagem">
              Mostrando {estado.dados.em_foco.itens.length} de {estado.dados.em_foco.total}{" "}
              chamados em foco
            </p>
          )}
        </>
      )}

      <p className="dashboard-foco__fila">
        <Link to="/cs/fila">Ver fila completa</Link>
      </p>
    </section>
  );
}
