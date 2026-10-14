import { ConteudoInsights } from "./insights/ConteudoInsights";

/** Tela de Insights do Gestor (rota `/cs/insights`): `h1` mais o Conteudo_Insights. */
export function Component() {
  return (
    <section aria-labelledby="titulo-insights" className="insights">
      <h1 id="titulo-insights">Insights</h1>
      <ConteudoInsights />
    </section>
  );
}
