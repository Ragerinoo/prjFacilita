import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { filaEventos } from "./api/filaEventos";
import { rotas } from "./app/rotas";
import "./estilos.css";

// Retoma eventos que ficaram pendentes antes de uma recarga (Req 3.12, 5.7).
filaEventos.retomar();

const container = document.getElementById("root");
if (!container) throw new Error("Elemento #root não encontrado.");

createRoot(container).render(
  <StrictMode>
    <RouterProvider router={createBrowserRouter(rotas)} />
  </StrictMode>,
);
