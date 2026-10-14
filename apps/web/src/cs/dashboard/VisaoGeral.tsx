import type { EstadoDashboard } from "./useDashboard";
import type { VisaoGeralDashboard } from "./tipos";

interface Props {
  estado: EstadoDashboard;
  /** Repete a solicitação do Dashboard (mostra o carregamento). */
  aoTentarDeNovo(): void;
}

interface Cartao {
  chave: keyof VisaoGeralDashboard;
  rotulo: string;
}

const CARTOES: readonly Cartao[] = [
  { chave: "abertos", rotulo: "Chamados abertos" },
  { chave: "em_atendimento", rotulo: "Em atendimento" },
  { chave: "encerrados", rotulo: "Encerrados" },
  { chave: "p1_risco_abertos", rotulo: "P1 de risco abertos" },
  { chave: "sem_responsavel", rotulo: "Sem responsável" },
  { chave: "respostas_nao_lidas", rotulo: "Respostas não lidas" },
];

/**
 * Seis cards com as contagens de `visao_geral`; os valores vêm todos da API do Dashboard.
 * O título da seção ("Visão geral") fica a cargo da tela que a contém.
 */
export function VisaoGeral({ estado, aoTentarDeNovo }: Props) {
  if (estado.fase === "carregando") {
    return (
      <p role="status" className="dashboard-estado">
        Carregando a visão geral…
      </p>
    );
  }

  if (estado.fase === "erro") {
    return (
      <div role="alert" className="dashboard-erro">
        <p>Não foi possível carregar a visão geral.</p>
        <button type="button" className="dashboard-botao" onClick={aoTentarDeNovo}>
          Tentar novamente
        </button>
      </div>
    );
  }

  const { visao_geral } = estado.dados;
  return (
    <dl className="dashboard-cartoes">
      {CARTOES.map((c) => (
        <div key={c.chave} className="dashboard-cartao">
          <dt>{c.rotulo}</dt>
          <dd className="dashboard-cartao__valor">{visao_geral[c.chave]}</dd>
        </div>
      ))}
    </dl>
  );
}
