import { useState } from "react";
import { ErroApi } from "../../api/cliente";
import { apiCs } from "../clienteCs";

interface DadosPessoais {
  telefone: string | null;
  cep: string | null;
}

export const MENSAGEM_LOG_INDISPONIVEL = "Não foi possível registrar o acesso; dados não exibidos.";

/**
 * "Ver dados pessoais": só busca após clique explícito (o servidor grava o acesso antes de
 * responder, Req 18.6/18.9). O estado é local: ao sair do card, os dados somem.
 */
export function DadosPessoaisChamado({ numero }: { numero: string }) {
  const [dados, setDados] = useState<DadosPessoais | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function ver() {
    setCarregando(true);
    setErro(null);
    setDados(null);
    try {
      const r = await apiCs.get<DadosPessoais>(`/chamados/${encodeURIComponent(numero)}/dados-pessoais`);
      setDados({ telefone: r.telefone ?? null, cep: r.cep ?? null });
    } catch (e) {
      setErro(
        e instanceof ErroApi && e.codigo === "log_acesso_indisponivel"
          ? MENSAGEM_LOG_INDISPONIVEL
          : "Não foi possível carregar os dados pessoais. Tente de novo.",
      );
    } finally {
      setCarregando(false);
    }
  }

  return (
    <section aria-labelledby="chamado-pessoais">
      <h2 id="chamado-pessoais">Dados pessoais</h2>
      {dados === null && (
        <button type="button" onClick={ver} disabled={carregando}>
          {carregando ? "Carregando…" : "Ver dados pessoais"}
        </button>
      )}
      {dados && (
        <>
          <p>Este acesso foi registrado.</p>
          <dl className="chamado__campos">
            <dt>Telefone</dt>
            <dd>{dados.telefone ?? "não informado"}</dd>
            <dt>CEP</dt>
            <dd>{dados.cep ?? "não informado"}</dd>
          </dl>
        </>
      )}
      {erro && <p role="alert">{erro}</p>}
    </section>
  );
}
