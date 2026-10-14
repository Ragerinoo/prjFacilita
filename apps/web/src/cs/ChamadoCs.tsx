import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router";
import { ErroApi } from "../api/cliente";
import { apiCs } from "./clienteCs";
import { AcoesChamado } from "./chamado/AcoesChamado";
import { AnexosChamado } from "./chamado/AnexosChamado";
import { AssumirChamado } from "./chamado/AssumirChamado";
import { CabecalhoChamado } from "./chamado/CabecalhoChamado";
import { DadosPessoaisChamado } from "./chamado/DadosPessoaisChamado";
import { HistoricoChamado } from "./chamado/HistoricoChamado";
import { ResumoPacote } from "./chamado/ResumoPacote";
import type { CardChamado } from "./chamado/tipos";
import "./chamado/chamado.css";

type Estado = { tipo: "carregando" } | { tipo: "erro"; mensagem: string } | { tipo: "ok"; card: CardChamado };

function CardDoChamado({ numero }: { numero: string }) {
  const [estado, setEstado] = useState<Estado>({ tipo: "carregando" });

  const carregar = useCallback(
    async (sinal?: AbortSignal) => {
      try {
        // Abrir o card de um P1 reconhece o alerta no servidor (Req 14.5).
        const card = await apiCs.get<CardChamado>(`/chamados/${encodeURIComponent(numero)}`, { sinal });
        if (!sinal?.aborted) setEstado({ tipo: "ok", card });
      } catch (e) {
        if (sinal?.aborted) return;
        const naoEncontrado = e instanceof ErroApi && e.status === 404;
        setEstado({
          tipo: "erro",
          mensagem: naoEncontrado
            ? "Chamado não encontrado."
            : "Não foi possível carregar o Chamado. Tente de novo.",
        });
      }
    },
    [numero],
  );

  useEffect(() => {
    const controle = new AbortController();
    void carregar(controle.signal);
    return () => controle.abort();
  }, [carregar]);

  if (estado.tipo === "carregando") {
    return (
      <section>
        <h1>Chamado {numero}</h1>
        <p role="status">Carregando…</p>
      </section>
    );
  }
  if (estado.tipo === "erro") {
    return (
      <section>
        <h1>Chamado {numero}</h1>
        <p role="alert">{estado.mensagem}</p>
        <button type="button" onClick={() => void carregar()}>
          Tentar novamente
        </button>
      </section>
    );
  }

  const { card } = estado;
  const atualizar = () => void carregar();
  return (
    <article>
      <CabecalhoChamado card={card} />
      <AssumirChamado card={card} aoAtualizar={atualizar} />
      <ResumoPacote card={card} />
      <HistoricoChamado card={card} />
      <AnexosChamado numero={card.numero} anexos={card.anexos} />
      <DadosPessoaisChamado numero={card.numero} />
      <AcoesChamado card={card} aoAtualizar={atualizar} />
    </article>
  );
}

export function Component() {
  const { numero = "" } = useParams();
  // `key` zera o estado local (inclusive dados pessoais) ao trocar de Chamado.
  return <CardDoChamado key={numero} numero={numero} />;
}
