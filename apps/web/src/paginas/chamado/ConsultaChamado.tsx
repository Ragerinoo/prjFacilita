import { useId, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

export const MENSAGEM_NUMERO_VAZIO = "Digite o número do chamado.";

/** Tira espaços e deixa em maiúsculas, como o número é emitido (ex.: TRES-7K3M9QX2PD). */
export function normalizarNumero(texto: string): string {
  return texto.replace(/\s+/g, "").toUpperCase();
}

interface Props {
  /** Valor inicial do campo (por exemplo, o número que não foi encontrado). */
  numeroInicial?: string;
  /** Chamado quando o número digitado é o mesmo da página atual (a rota não muda, então repete a consulta). */
  aoRepetir?: (numero: string) => void;
  /** Número da página atual, para detectar `aoRepetir`. */
  numeroAtual?: string;
}

/**
 * Campo para consultar um Chamado pelo número (Req 12.8, 12.11). Não mostra nenhum dado de Chamado:
 * quem mostra é a página `/chamado/:numero`, que também mantém este campo na tela de "não encontrado".
 */
export function ConsultaChamado({ numeroInicial = "", aoRepetir, numeroAtual }: Props) {
  const id = useId();
  const navegar = useNavigate();
  const [numero, setNumero] = useState(numeroInicial);
  const [erro, setErro] = useState<string | null>(null);
  const campo = useRef<HTMLInputElement>(null);

  function consultar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const normalizado = normalizarNumero(numero);
    if (!normalizado) {
      setErro(MENSAGEM_NUMERO_VAZIO);
      campo.current?.focus();
      return;
    }
    setErro(null);
    if (aoRepetir && normalizado === numeroAtual) {
      aoRepetir(normalizado);
      return;
    }
    void navegar(`/chamado/${encodeURIComponent(normalizado)}`);
  }

  return (
    <form onSubmit={consultar} noValidate className="chamado__consulta">
      <div className="chamado__campo">
        <label htmlFor={`${id}-numero`}>Número do chamado</label>
        <input
          id={`${id}-numero`}
          ref={campo}
          type="text"
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={40}
          value={numero}
          onChange={(e) => setNumero(e.target.value)}
          aria-invalid={erro ? true : undefined}
          aria-describedby={`${id}-ajuda${erro ? ` ${id}-erro` : ""}`}
        />
        <small id={`${id}-ajuda`}>Exemplo: TRES-7K3M9QX2PD</small>
        {erro ? (
          <p id={`${id}-erro`} role="alert" className="chamado__erro">
            {erro}
          </p>
        ) : null}
      </div>
      <button type="submit" className="botao chamado__enviar">
        Consultar chamado
      </button>
    </form>
  );
}
