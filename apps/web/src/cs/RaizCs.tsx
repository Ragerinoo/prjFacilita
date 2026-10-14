import { Outlet } from "react-router";
import { SessaoCsProvider } from "./SessaoCs";
import "./painel.css";

/**
 * Raiz do Painel_CS (`/cs/*`). É independente do Layout do Portal: não tem o alerta
 * de risco do Consumidor nem o rodapé de privacidade. Só provê a sessão às telas.
 */
export function Component() {
  return (
    <SessaoCsProvider>
      <a className="pular-conteudo" href="#conteudo">
        Ir para o conteúdo
      </a>
      <Outlet />
    </SessaoCsProvider>
  );
}
