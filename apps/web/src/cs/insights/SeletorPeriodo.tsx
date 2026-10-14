import { useId, useState, type ChangeEvent, type FormEvent } from "react";
import { validarIntervalo } from "./formatar";
import type { IdPeriodo } from "./tipos";

/** Período escolhido; `inicio` e `fim` (AAAA-MM-DD) só existem no personalizado. */
export interface ConsultaPeriodo {
  periodo: IdPeriodo;
  inicio?: string;
  fim?: string;
}

interface Props {
  consulta: ConsultaPeriodo;
  /** Chamado ao escolher Hoje, 7 dias ou 30 dias, ou ao aplicar um intervalo personalizado válido. */
  aoMudar: (consulta: ConsultaPeriodo) => void;
}

const OPCOES: { valor: IdPeriodo; rotulo: string }[] = [
  { valor: "hoje", rotulo: "Hoje" },
  { valor: "7d", rotulo: "7 dias" },
  { valor: "30d", rotulo: "30 dias" },
  { valor: "personalizado", rotulo: "Personalizado" },
];

function ehIdPeriodo(valor: string): valor is IdPeriodo {
  return OPCOES.some((o) => o.valor === valor);
}

export function SeletorPeriodo({ consulta, aoMudar }: Props) {
  const idSeletor = useId();
  const idInicio = useId();
  const idFim = useId();
  const idErro = useId();
  const [escolha, setEscolha] = useState<IdPeriodo>(consulta.periodo);
  const [inicio, setInicio] = useState(consulta.inicio ?? "");
  const [fim, setFim] = useState(consulta.fim ?? "");
  const [erro, setErro] = useState<string | null>(null);

  function aoEscolher(evento: ChangeEvent<HTMLSelectElement>) {
    const valor = evento.target.value;
    if (!ehIdPeriodo(valor)) return;
    setEscolha(valor);
    setErro(null);
    if (valor !== "personalizado") aoMudar({ periodo: valor });
  }

  function aoAplicar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const mensagem = validarIntervalo(inicio, fim);
    setErro(mensagem);
    if (mensagem === null) aoMudar({ periodo: "personalizado", inicio, fim });
  }

  const personalizado = escolha === "personalizado";

  return (
    <form className="insights-seletor" onSubmit={aoAplicar} noValidate>
      <div className="insights-seletor__campo">
        <label htmlFor={idSeletor}>Período</label>
        <select id={idSeletor} value={escolha} onChange={aoEscolher}>
          {OPCOES.map((o) => (
            <option key={o.valor} value={o.valor}>
              {o.rotulo}
            </option>
          ))}
        </select>
      </div>
      {personalizado && (
        <>
          <div className="insights-seletor__campo">
            <label htmlFor={idInicio}>Data inicial</label>
            <input
              id={idInicio}
              type="date"
              value={inicio}
              onChange={(e) => setInicio(e.target.value)}
              aria-invalid={erro !== null}
              aria-describedby={erro !== null ? idErro : undefined}
            />
          </div>
          <div className="insights-seletor__campo">
            <label htmlFor={idFim}>Data final</label>
            <input
              id={idFim}
              type="date"
              value={fim}
              onChange={(e) => setFim(e.target.value)}
              aria-invalid={erro !== null}
              aria-describedby={erro !== null ? idErro : undefined}
            />
          </div>
          <button type="submit">Aplicar</button>
          {erro !== null && (
            <p id={idErro} role="alert" className="insights-seletor__erro">
              {erro}
            </p>
          )}
        </>
      )}
    </form>
  );
}
