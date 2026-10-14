import { useState } from "react";
import { NavLink, Outlet } from "react-router";
import { useSessaoCs, type PerfilCs } from "./SessaoCs";

const ROTULO_PERFIL: Record<PerfilCs, string> = {
  atendente: "Atendente",
  gestor: "Gestor",
};

/** Layout próprio do Painel_CS: cabeçalho com usuário e perfil, menu e saída. */
export function Component() {
  const { usuario, perfil, logout } = useSessaoCs();
  const [saindo, setSaindo] = useState(false);

  async function sair() {
    setSaindo(true);
    await logout();
  }

  return (
    <>
      <header className="painel__cabecalho">
        <p className="painel__marca">Painel de atendimento TRES</p>
        <p className="painel__usuario">
          <span>{usuario}</span> <span>({perfil ? ROTULO_PERFIL[perfil] : ""})</span>
        </p>
        <button type="button" className="botao botao--secundario" onClick={sair} disabled={saindo}>
          Sair
        </button>
        <nav aria-label="Painel" className="painel__menu">
          {/* Req 19: "end" evita que o Dashboard fique ativo nas demais páginas /cs/*. */}
          <NavLink to="/cs" end>
            Dashboard
          </NavLink>
          <NavLink to="/cs/fila">Fila de chamados</NavLink>
          {/* Req 13.3/13.4: o Atendente nem vê o acesso às métricas. */}
          {perfil === "gestor" ? <NavLink to="/cs/metricas">Métricas</NavLink> : null}
          {perfil === "gestor" ? <NavLink to="/cs/insights">Insights</NavLink> : null}
        </nav>
      </header>
      <main id="conteudo" tabIndex={-1} className="painel__conteudo">
        <Outlet />
      </main>
    </>
  );
}
