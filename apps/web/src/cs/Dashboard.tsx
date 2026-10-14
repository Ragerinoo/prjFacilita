/**
 * Tela_Dashboard: rota índice de `/cs` (spec insights-gestor, D11 a D13; Req 20, 24, 25, 26).
 *
 * Isolamento do Recharts: este arquivo e `cs/dashboard/` só importam de `cs/insights/` os módulos
 * `tipos`, `formatar` e `useInsights`. O `ConteudoInsights` (que arrasta o Recharts) entra
 * apenas pelo `import()` abaixo, disparado quando o painel "Insights" é desenhado.
 */
import { lazy, Suspense, useId } from "react";
import { useSearchParams } from "react-router";
import { CartoesSatisfacao } from "./dashboard/CartoesSatisfacao";
import { abaEfetiva } from "./dashboard/formatar";
import { ListaEmFoco } from "./dashboard/ListaEmFoco";
import { SeletorDeAbas, type AbaDeclarada } from "./dashboard/SeletorDeAbas";
import type { AbaDashboard, PerfilDashboard } from "./dashboard/tipos";
import { useDashboard } from "./dashboard/useDashboard";
import { VisaoGeral } from "./dashboard/VisaoGeral";
import { CONSULTA_7D, useBuscaInsights } from "./insights/useInsights";
import { useSessaoCs } from "./SessaoCs";
import "./dashboard.css";
import "./insights.css";

const ConteudoInsights = lazy(() =>
  import("./insights/ConteudoInsights").then((m) => ({ default: m.ConteudoInsights })),
);

/** "14:32:10" na hora local do navegador, ou `null` se `gerado_em` não for uma data válida. */
function horaDe(geradoEm: string): string | null {
  const data = new Date(geradoEm);
  if (Number.isNaN(data.getTime())) return null;
  const dois = (n: number) => String(n).padStart(2, "0");
  return `${dois(data.getHours())}:${dois(data.getMinutes())}:${dois(data.getSeconds())}`;
}

/** Converte o perfil da sessão: `gestor` ou, em qualquer outro caso, `atendente` (expõe menos). */
export function Component() {
  const { perfil } = useSessaoCs();
  return <TelaDashboard perfil={perfil === "gestor" ? "gestor" : "atendente"} />;
}

export function TelaDashboard({ perfil }: { perfil: PerfilDashboard }) {
  const idVisaoGeral = useId();
  const [parametros, setParametros] = useSearchParams();
  const { estado, tentarDeNovo } = useDashboard();
  // O Atendente nunca solicita a API_Insights (Req 24.4, 25.7).
  const insights7d = useBuscaInsights(CONSULTA_7D, perfil === "gestor");
  const aba = abaEfetiva(parametros.get("aba"), perfil);

  function selecionar(id: AbaDashboard) {
    setParametros(
      (anterior) => {
        const novo = new URLSearchParams(anterior);
        novo.set("aba", id);
        return novo;
      },
      { replace: true },
    );
  }

  const lista = <ListaEmFoco estado={estado} aoTentarDeNovo={tentarDeNovo} />;
  const abas: readonly AbaDeclarada<AbaDashboard>[] = [
    {
      id: "insights",
      rotulo: "Insights",
      painel: (
        <Suspense fallback={<p role="status">Carregando os insights…</p>}>
          <ConteudoInsights fonte7d={insights7d} semAvisoDemo />
        </Suspense>
      ),
    },
    { id: "chamados", rotulo: "Chamados em foco", painel: lista },
  ];

  const hora = estado.fase === "pronto" ? horaDe(estado.dados.gerado_em) : null;

  return (
    <div className="dashboard">
      <h1>Dashboard</h1>

      {estado.fase === "pronto" && estado.dados.modo_local && (
        <p className="insights-aviso">Dados de demonstração</p>
      )}
      {hora !== null && <p className="dashboard-atualizado">Atualizado às {hora}</p>}
      {estado.fase === "pronto" && estado.falhaAtualizacao && (
        <p role="status" className="dashboard-aviso-falha">
          Não foi possível atualizar o Dashboard. Mostrando os últimos dados recebidos; nova
          tentativa em instantes.
        </p>
      )}

      <section aria-labelledby={idVisaoGeral} className="dashboard-secao">
        <h2 id={idVisaoGeral}>Visão geral</h2>
        <VisaoGeral estado={estado} aoTentarDeNovo={tentarDeNovo} />
        {perfil === "gestor" && (
          <>
            <h3>Satisfação</h3>
            <CartoesSatisfacao fonte={insights7d} />
          </>
        )}
      </section>

      {perfil === "gestor" ? (
        <SeletorDeAbas abas={abas} selecionada={aba} aoSelecionar={selecionar} />
      ) : (
        lista
      )}
    </div>
  );
}
