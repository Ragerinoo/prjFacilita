import { type RouteObject } from "react-router";
import { Layout } from "./Layout";
import { PaginaErro } from "./PaginaErro";

/**
 * Mapa de rotas do Portal_TRES e do Painel_CS (design.md, seção Components).
 *
 * Divisão de código por rota (Req 19.2): cada página é importada dinamicamente
 * via `lazy`, então o bundle inicial contém apenas o Layout e o roteador.
 */
export const rotas: RouteObject[] = [
  {
    path: "/",
    Component: Layout,
    children: [
      {
        // Rota sem caminho: o erro de uma página (inclusive falha ao baixar o
        // chunk) aparece dentro do Layout, com "Tentar novamente" (Req 19.9).
        ErrorBoundary: PaginaErro,
        children: [
          { index: true, lazy: () => import("../paginas/Inicio") },
          { path: "m/:modeloId", lazy: () => import("../paginas/PaginaMaquina") },
          { path: "m/:modeloId/p/:problemaId", lazy: () => import("../paginas/Instrucao") },
          { path: "abrir-chamado", lazy: () => import("../paginas/AbrirChamado") },
          { path: "chamado", lazy: () => import("../paginas/Chamado") },
          { path: "chamado/:numero", lazy: () => import("../paginas/Chamado") },
          { path: "privacidade", lazy: () => import("../paginas/Privacidade") },
          { path: "*", lazy: () => import("../paginas/NaoEncontrada") },
        ],
      },
    ],
  },
  {
    // Painel_CS: layout e sessão próprios, fora do Layout do Portal (sem o alerta de
    // risco do Consumidor). Nada além do login renderiza sem sessão (Req 13.1, 13.6).
    path: "/cs",
    lazy: () => import("../cs/RaizCs"),
    ErrorBoundary: PaginaErro,
    children: [
      { path: "login", lazy: () => import("../cs/LoginCs") },
      {
        lazy: () => import("../cs/GuardaSessao"),
        children: [
          {
            lazy: () => import("../cs/LayoutPainel"),
            children: [
              // Dashboard é a tela principal do Painel (Req 20.1); o chunk dele não
              // inclui o Recharts, que só vem com ConteudoInsights (D11).
              { index: true, lazy: () => import("../cs/Dashboard") },
              { path: "fila", lazy: () => import("../cs/FilaCs") },
              { path: "chamados/:numero", lazy: () => import("../cs/ChamadoCs") },
              {
                // Só o Gestor (Req 13.3, 13.4).
                lazy: () => import("../cs/GuardaGestor"),
                children: [
                  { path: "metricas", lazy: () => import("../cs/MetricasCs") },
                  { path: "insights", lazy: () => import("../cs/InsightsCs") },
                ],
              },
              { path: "*", lazy: () => import("../paginas/NaoEncontrada") },
            ],
          },
        ],
      },
    ],
  },
];
