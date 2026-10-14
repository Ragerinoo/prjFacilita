import { Outlet } from "react-router";
import { AcessoNegado } from "./AcessoNegado";
import { useSessaoCs } from "./SessaoCs";

/**
 * Rotas só do Gestor (Painel_Metricas, Req 13.3 e 13.4). O Atendente não vê o link
 * no menu e, se digitar o endereço, recebe a tela de acesso negado sem nenhum dado.
 * O servidor também responde 403: esta guarda é só a camada de apresentação.
 */
export function Component() {
  const { perfil } = useSessaoCs();
  if (perfil !== "gestor") return <AcessoNegado />;
  return <Outlet />;
}
