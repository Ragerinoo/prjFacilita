import { useId } from "react";
import { formatarData } from "./formatar";
import type { ComentarioInsights } from "./tipos";

interface Props {
  comentarios: ComentarioInsights[];
}

/**
 * Amostra dos comentários já mascarados pela API.
 * O texto é sempre texto simples do React (escapado); a quebra de linha vem do CSS (`pre-wrap`).
 */
export function Comentarios({ comentarios }: Props) {
  const idTitulo = useId();

  return (
    <section aria-labelledby={idTitulo} className="insights-secao">
      <h2 id={idTitulo}>Comentários recentes</h2>
      {comentarios.length === 0 ? (
        <p>Não há dados para esta seção no período.</p>
      ) : (
        <ul className="insights-comentarios">
          {comentarios.map((c, indice) => (
            <li key={`${c.em}-${indice}`} className="insights-comentario">
              <p className="insights-comentario__meta">
                <span>Nota {c.nota} de 5</span> · <time dateTime={c.em}>{formatarData(c.em)}</time>
              </p>
              <p className="insights-comentario__texto">{c.texto}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
