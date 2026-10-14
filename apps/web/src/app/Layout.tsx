import { Link, Outlet, useNavigation } from "react-router";
import { AlertaRisco } from "../componentes/AlertaRisco";
import { RiscoProvider } from "../risco/RiscoContext";

export function Layout() {
  const navegacao = useNavigation();
  const carregando = navegacao.state === "loading";

  return (
    <RiscoProvider>
      <a className="pular-conteudo" href="#conteudo">
        Ir para o conteúdo
      </a>
      <header className="cabecalho">
        <Link to="/" className="cabecalho__marca">
          TRES Autoatendimento
        </Link>
      </header>
      {/* Req 8.3: no topo, em todas as telas, enquanto o servidor mantiver o risco da Jornada. */}
      <AlertaRisco />
      <main id="conteudo" tabIndex={-1} aria-busy={carregando}>
        <Outlet />
      </main>
      <footer className="rodape">
        <Link to="/privacidade">Aviso de privacidade</Link>
      </footer>
    </RiscoProvider>
  );
}
