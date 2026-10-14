import { formatarData, type CardChamado } from "./tipos";

const AUTOR: Record<string, string> = { consumidor: "Consumidor", atendente: "Atendente" };

function resumirDados(dados: unknown): string {
  if (dados === null || dados === undefined) return "";
  if (typeof dados === "string") return dados;
  try {
    return JSON.stringify(dados);
  } catch {
    return "";
  }
}

/** Mensagens e eventos em ordem cronológica (o servidor já ordena e mascara PII). */
export function HistoricoChamado({ card }: { card: CardChamado }) {
  return (
    <>
      <section aria-labelledby="chamado-mensagens">
        <h2 id="chamado-mensagens">Mensagens</h2>
        {card.mensagens.length === 0 ? (
          <p>Nenhuma mensagem trocada ainda.</p>
        ) : (
          <ol className="chamado__lista">
            {card.mensagens.map((m) => (
              <li key={m.ts_ulid}>
                <strong>{AUTOR[m.autor] ?? m.autor}</strong> · {formatarData(m.em)}
                {m.autor === "consumidor" && !m.lida ? " · não lida" : ""}
                <p>{m.texto}</p>
              </li>
            ))}
          </ol>
        )}
      </section>
      <section aria-labelledby="chamado-historico">
        <h2 id="chamado-historico">Histórico da jornada</h2>
        {card.historico.length === 0 ? (
          <p>Sem eventos registrados.</p>
        ) : (
          <ol className="chamado__lista">
            {card.historico.map((e) => (
              <li key={e.evento_id}>
                <strong>{e.tipo}</strong> · {formatarData(e.em)}
                <p>{resumirDados(e.dados)}</p>
              </li>
            ))}
          </ol>
        )}
      </section>
    </>
  );
}
