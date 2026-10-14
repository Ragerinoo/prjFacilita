import { useState } from "react";
import { ErroApi } from "../../api/cliente";
import { apiCs } from "../clienteCs";
import type { CardChamado } from "./tipos";

/** Botão "Assumir". No 409 mostra a mensagem do servidor, que já traz o nome do vencedor. */
export function AssumirChamado({ card, aoAtualizar }: { card: CardChamado; aoAtualizar: () => void }) {
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const encerrado = card.status === "encerrado";
  const assumido = card.responsavel !== null;

  async function assumir() {
    setEnviando(true);
    setErro(null);
    try {
      await apiCs.post(`/chamados/${encodeURIComponent(card.numero)}/assumir`);
      aoAtualizar();
    } catch (e) {
      if (e instanceof ErroApi && e.status === 409) {
        setErro(e.message);
        aoAtualizar(); // mostra quem ficou com o Chamado
      } else {
        setErro("Não foi possível assumir o Chamado. Tente de novo.");
      }
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section aria-labelledby="chamado-assumir">
      <h2 id="chamado-assumir">Responsável</h2>
      <button type="button" onClick={assumir} disabled={assumido || encerrado || enviando}>
        {enviando ? "Assumindo…" : "Assumir"}
      </button>
      {encerrado && <p>Este Chamado já foi encerrado.</p>}
      {!encerrado && assumido && <p>Assumido por {card.responsavel?.nome}.</p>}
      {erro && <p role="alert">{erro}</p>}
    </section>
  );
}
