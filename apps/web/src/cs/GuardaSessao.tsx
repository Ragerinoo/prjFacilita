import { Navigate, Outlet, useLocation } from "react-router";
import { useSessaoCs } from "./SessaoCs";

/**
 * Guarda de rotas do Painel (Req 13.1, 13.5, 13.6): sem sessão confirmada nada do
 * Painel é renderizado. Enquanto o servidor não responde mostra só um aviso; sem
 * sessão (nunca entrou, saiu ou expirou) manda ao login. A tela de login lê
 * `expirou` do contexto para explicar o motivo.
 */
export function Component() {
  const sessao = useSessaoCs();
  const local = useLocation();

  if (sessao.status === "carregando") {
    return (
      <main id="conteudo" tabIndex={-1}>
        <p role="status">Verificando a sua sessão…</p>
      </main>
    );
  }
  if (sessao.status === "anonimo") {
    return <Navigate to="/cs/login" replace state={{ de: `${local.pathname}${local.search}` }} />;
  }
  return <Outlet />;
}
