import { useId, useRef, useState, type FormEvent } from "react";
import {
  enviarMensagem,
  errosPorCampo,
  STATUS_ENCERRADO,
  validarMensagem,
  type MensagemChamado,
} from "../../api/chamado";
import { formatarDataHora } from "./formatacao";

export const MENSAGEM_FALHA_RESPOSTA = "Não foi possível enviar agora. O que você escreveu foi mantido. Tente de novo.";
export const MENSAGEM_RESPOSTA_ENVIADA = "Mensagem enviada.";
export const MENSAGEM_SEM_MENSAGENS = "Ainda não há mensagens neste chamado.";
export const MENSAGEM_ENCERRADO = "Este chamado foi encerrado.";

const AUTORES = { atendente: "Atendente", consumidor: "Você" } as const;

interface Props {
  numero: string;
  status?: string;
  mensagens: MensagemChamado[];
  /** Chamado depois de enviar, para a resposta aparecer sem esperar o próximo ciclo. */
  aoEnviar: () => void;
}

/**
 * Mensagens do chamado em ordem cronológica, cada uma com data e hora (Req 12.8, 15.4), e a resposta do
 * Consumidor (Req 15.5). Mensagens novas do Atendente são anunciadas numa região `aria-live` educada;
 * as que já estavam na tela quando a página abriu não são anunciadas.
 */
export function MensagensChamado({ numero, status, mensagens, aoEnviar }: Props) {
  const doAtendente = mensagens.filter((m) => m.autor === "atendente");
  const [vistas, setVistas] = useState(doAtendente.length);
  const [aviso, setAviso] = useState("");
  if (doAtendente.length !== vistas) {
    // Ajuste de estado durante a renderização: anuncia só o que chegou depois da abertura.
    setVistas(doAtendente.length);
    if (doAtendente.length > vistas) {
      const ultima = doAtendente[doAtendente.length - 1];
      setAviso(`Nova mensagem do atendente, ${formatarDataHora(ultima.em)}: ${ultima.texto}`);
    }
  }

  return (
    <section aria-labelledby="titulo-mensagens" className="chamado__secao">
      <h2 id="titulo-mensagens">Mensagens</h2>
      <div role="status" aria-live="polite" aria-atomic="true" className="so-leitor" data-testid="anuncio-mensagem">
        {aviso}
      </div>
      {mensagens.length === 0 ? (
        <p>{MENSAGEM_SEM_MENSAGENS}</p>
      ) : (
        <ol className="chamado__mensagens" aria-label="Mensagens do chamado, da mais antiga para a mais recente">
          {mensagens.map((m, indice) => (
            <li key={`${m.em}-${indice}`} className={`chamado__mensagem chamado__mensagem--${m.autor}`}>
              <p className="chamado__mensagem-cabecalho">
                <strong>{AUTORES[m.autor]}</strong> <time dateTime={m.em}>{formatarDataHora(m.em)}</time>
              </p>
              <p className="chamado__mensagem-texto">{m.texto}</p>
            </li>
          ))}
        </ol>
      )}
      {status === STATUS_ENCERRADO ? (
        <p>{MENSAGEM_ENCERRADO}</p>
      ) : (
        <RespostaConsumidor numero={numero} aoEnviar={aoEnviar} />
      )}
    </section>
  );
}

function RespostaConsumidor({ numero, aoEnviar }: { numero: string; aoEnviar: () => void }) {
  const id = useId();
  const [texto, setTexto] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [enviada, setEnviada] = useState(false);
  const campo = useRef<HTMLTextAreaElement>(null);

  async function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (enviando) return;
    setEnviada(false);
    const invalido = validarMensagem(texto);
    setErro(invalido);
    if (invalido) {
      campo.current?.focus();
      return;
    }
    setEnviando(true);
    try {
      await enviarMensagem(numero, texto);
      setTexto("");
      setEnviada(true);
      aoEnviar();
    } catch (falha) {
      // Em qualquer falha o texto fica no campo, para novo envio (Req 15.8, do lado do Consumidor).
      setErro(errosPorCampo(falha).texto ?? MENSAGEM_FALHA_RESPOSTA);
      campo.current?.focus();
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form onSubmit={(e) => void enviar(e)} noValidate aria-busy={enviando} className="chamado__resposta">
      <div className="chamado__campo">
        <label htmlFor={`${id}-texto`}>Sua resposta</label>
        <textarea
          id={`${id}-texto`}
          ref={campo}
          rows={4}
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          aria-invalid={erro ? true : undefined}
          aria-describedby={`${id}-ajuda${erro ? ` ${id}-erro` : ""}`}
        />
        <small id={`${id}-ajuda`}>Até 2000 caracteres.</small>
        {erro ? (
          <p id={`${id}-erro`} role="alert" className="chamado__erro">
            {erro}
          </p>
        ) : null}
      </div>
      <p role="status">{enviada && !erro ? MENSAGEM_RESPOSTA_ENVIADA : ""}</p>
      <button type="submit" className="botao chamado__enviar" disabled={enviando}>
        {enviando ? "Enviando…" : "Enviar resposta"}
      </button>
    </form>
  );
}
