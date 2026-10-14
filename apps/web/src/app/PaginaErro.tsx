import { ErroCarregamento } from "../componentes/ErroCarregamento";

/** Limite de erro das rotas: falha de importação da página ou erro ao exibi-la. */
export function PaginaErro() {
  return <ErroCarregamento />;
}
