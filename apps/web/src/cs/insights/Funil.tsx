import { useId } from "react";
import { formatarPercentual } from "./formatar";
import type { Funil as DadosFunil } from "./tipos";

interface Props {
  funil: DadosFunil;
}

const ROTULOS_ORIGEM: Record<string, string> = {
  qr: "QR code",
  busca: "Busca",
};

const ROTULOS_CAMADA: Record<string, string> = {
  guia: "Resolvido no guia",
  humano: "Atendimento humano",
  abandonada: "Abandonada",
};

/** Contexto secundário: origem das Jornadas encerradas, abandono e deflexão por camada. */
export function Funil({ funil }: Props) {
  const idTitulo = useId();
  const idOrigem = useId();
  const idDeflexao = useId();

  return (
    <section aria-labelledby={idTitulo} className="insights-secao insights-secao--secundaria">
      <h2 id={idTitulo}>Funil da jornada</h2>
      {funil.total_encerradas === 0 ? (
        <p>Não há dados para esta seção no período.</p>
      ) : (
        <>
          <p>
            Jornadas encerradas: <strong>{funil.total_encerradas}</strong>. Abandono:{" "}
            <strong>{formatarPercentual(funil.abandono_pct)}</strong>.
          </p>
          <h3 id={idOrigem}>Origem</h3>
          <table className="insights-tabela" aria-labelledby={idOrigem}>
            <thead>
              <tr>
                <th scope="col">Origem</th>
                <th scope="col">Jornadas</th>
                <th scope="col">Proporção</th>
              </tr>
            </thead>
            <tbody>
              {funil.por_origem.map((linha) => (
                <tr key={linha.origem}>
                  <td>{ROTULOS_ORIGEM[linha.origem] ?? linha.origem}</td>
                  <td className="insights-tabela__numero">{linha.quantidade}</td>
                  <td className="insights-tabela__numero">{formatarPercentual(linha.percentual)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3 id={idDeflexao}>Como terminaram</h3>
          <table className="insights-tabela" aria-labelledby={idDeflexao}>
            <thead>
              <tr>
                <th scope="col">Camada</th>
                <th scope="col">Jornadas</th>
                <th scope="col">Proporção</th>
              </tr>
            </thead>
            <tbody>
              {funil.deflexao.map((linha) => (
                <tr key={linha.camada}>
                  <td>{ROTULOS_CAMADA[linha.camada] ?? linha.camada}</td>
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
