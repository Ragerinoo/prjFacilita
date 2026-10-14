import { useCallback, useEffect, useId, useRef, useState } from "react";
import { apiCs } from "./clienteCs";
import "./metricas.css";

export interface LinhaContagem {
  chave: string;
  rotulo: string;
  quantidade: number;
}

export interface RespostaMetricas {
  totais: { abertos: number; encerrados: number };
  por_problema: LinhaContagem[];
  por_modelo: LinhaContagem[];
  por_prioridade: LinhaContagem[];
  por_desfecho: LinhaContagem[];
}

const ROTULOS_CONHECIDOS: Record<string, string> = {
  nao_informado: "Não informado",
  falso_defeito: "Falso defeito",
  defeito_real: "Defeito real",
};

/** Texto de exibição de um rótulo da API; o que não é conhecido segue como veio. */
export function formatarRotulo(rotulo: string): string {
  return ROTULOS_CONHECIDOS[rotulo] ?? rotulo;
}

type Estado = { fase: "carregando" } | { fase: "erro" } | { fase: "pronto"; dados: RespostaMetricas };

export function Component() {
  const [estado, setEstado] = useState<Estado>({ fase: "carregando" });
  const montado = useRef(true);

  const carregar = useCallback(async () => {
    try {
      const dados = await apiCs.get<RespostaMetricas>("/metricas");
      if (!montado.current) return;
      setEstado({ fase: "pronto", dados });
    } catch {
      if (!montado.current) return;
      setEstado({ fase: "erro" });
    }
  }, []);

  const tentarDeNovo = useCallback(() => {
    setEstado({ fase: "carregando" });
    void carregar();
  }, [carregar]);

  useEffect(() => {
    montado.current = true;
    void carregar();
    return () => {
      montado.current = false;
    };
  }, [carregar]);

  return (
    <section aria-labelledby="titulo-metricas" className="metricas">
      <h1 id="titulo-metricas">Métricas</h1>
      {estado.fase === "carregando" && <p role="status">Carregando as métricas…</p>}
      {estado.fase === "erro" && (
        <div role="alert" className="metricas__erro">
          <p>Não foi possível carregar as métricas.</p>
          <button type="button" onClick={tentarDeNovo}>
            Tentar de novo
          </button>
        </div>
      )}
      {estado.fase === "pronto" && <ConteudoMetricas dados={estado.dados} />}
    </section>
  );
}

function ConteudoMetricas({ dados }: { dados: RespostaMetricas }) {
  return (
    <>
      <dl className="metricas__totais">
        <div className="metricas__total">
          <dt>Chamados abertos</dt>
          <dd>{dados.totais.abertos}</dd>
        </div>
        <div className="metricas__total">
          <dt>Chamados encerrados</dt>
          <dd>{dados.totais.encerrados}</dd>
        </div>
      </dl>
      <SecaoDimensao titulo="Por problema" linhas={dados.por_problema} />
      <SecaoDimensao titulo="Por modelo" linhas={dados.por_modelo} />
      <SecaoDimensao titulo="Por prioridade" linhas={dados.por_prioridade} />
      <SecaoDimensao titulo="Por desfecho" linhas={dados.por_desfecho} />
    </>
  );
}

function SecaoDimensao({ titulo, linhas }: { titulo: string; linhas: LinhaContagem[] }) {
  const idTitulo = useId();
  const maior = linhas.reduce((max, l) => Math.max(max, l.quantidade), 0);

  return (
    <section aria-labelledby={idTitulo} className="metricas__secao">
      <h2 id={idTitulo}>{titulo}</h2>
      {maior <= 0 ? (
        <p>Não há chamados para esta dimensão.</p>
      ) : (
        <table className="metricas__tabela" aria-labelledby={idTitulo}>
          <thead>
            <tr>
              <th scope="col">Rótulo</th>
              <th scope="col">Quantidade</th>
              <th scope="col">Proporção</th>
            </tr>
          </thead>
          <tbody>
            {linhas.map((linha) => (
              <tr key={linha.chave}>
                <td>{formatarRotulo(linha.rotulo)}</td>
                <td className="metricas__numero">{linha.quantidade}</td>
                <td>
                  {linha.quantidade > 0 && (
                    <span
                      className="metricas__barra"
                      style={{ width: `${(linha.quantidade / maior) * 100}%` }}
                      aria-hidden="true"
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
