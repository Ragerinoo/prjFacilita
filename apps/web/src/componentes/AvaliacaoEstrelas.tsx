import { useEffect, useRef, useState, type FormEvent } from "react";
import { filaEventos } from "../api/filaEventos";
import "./AvaliacaoEstrelas.css";

export const MAX_COMENTARIO = 500;
export const MENSAGEM_NOTA_OBRIGATORIA = "Escolha uma nota de 1 a 5 estrelas.";
export const MENSAGEM_AVALIACAO_ENVIADA = "Obrigado! Sua avaliação foi enviada.";
export const MENSAGEM_AVALIACAO_FALHOU =
  "Não foi possível registrar a sua avaliação. O seu problema continua marcado como resolvido.";

type Estado = "preenchendo" | "enviando" | "enviada" | "falhou";

/**
 * Avaliação de 1 a 5 estrelas com comentário opcional (Req 5.2, 5.5, 5.7).
 *
 * O envio passa pela fila local: ela tenta de novo até 3 vezes, de 5 em 5 s,
 * sem travar a tela. A nota e o comentário ficam na tela mesmo se o envio
 * falhar, e a Jornada nunca é reaberta.
 */
export type PropsAvaliacaoEstrelas =
  /** Avaliação da Jornada: `POST /jornadas/{id}/avaliacao` (Req 5.2). */
  | { jornadaId: string; caminho?: undefined }
  /** Rota própria, por exemplo `POST /chamados/{numero}/avaliacao` no acompanhamento (Req 16.5). */
  | { caminho: string; jornadaId?: undefined };

export function AvaliacaoEstrelas(props: PropsAvaliacaoEstrelas) {
  const destino =
    props.caminho !== undefined ? props.caminho : `/jornadas/${encodeURIComponent(props.jornadaId)}/avaliacao`;
  const [nota, setNota] = useState<number | null>(null);
  const [comentario, setComentario] = useState("");
  const [estado, setEstado] = useState<Estado>("preenchendo");
  const [semNota, setSemNota] = useState(false);
  const eventoId = useRef<string | null>(null);

  useEffect(() => {
    const desligarSucesso = filaEventos.aoEnviar((evento) => {
      if (evento.evento_id === eventoId.current) setEstado("enviada");
    });
    const desligarFalha = filaEventos.aoFalharDefinitivamente((evento) => {
      if (evento.evento_id === eventoId.current) setEstado("falhou");
    });
    return () => {
      desligarSucesso();
      desligarFalha();
    };
  }, []);

  function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (estado === "enviando" || estado === "enviada") return;
    if (nota === null) {
      setSemNota(true);
      return;
    }
    setSemNota(false);
    setEstado("enviando");
    const corpo: Record<string, unknown> = { nota };
    const texto = comentario.trim();
    if (texto) corpo.comentario = texto;
    eventoId.current = filaEventos.enfileirar(destino, corpo);
  }

  if (estado === "enviada") {
    return (
      <p role="status" className="avaliacao__confirmacao">
        {MENSAGEM_AVALIACAO_ENVIADA}
      </p>
    );
  }

  return (
    <form className="avaliacao" onSubmit={enviar} noValidate aria-busy={estado === "enviando"}>
      <fieldset className="avaliacao__notas">
        <legend>Dê uma nota de 1 a 5 estrelas para esta ajuda</legend>
        <div className="grupo-alvos">
          {[1, 2, 3, 4, 5].map((valor) => (
            <label key={valor} className="avaliacao__estrela">
              <input
                type="radio"
                name="nota"
                value={valor}
                checked={nota === valor}
                onChange={() => setNota(valor)}
              />
              <span aria-hidden="true">{"★".repeat(valor)}</span>
              <span className="so-leitor">{valor === 1 ? "1 estrela" : `${valor} estrelas`}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className="avaliacao__comentario">
        <label htmlFor="avaliacao-comentario">Comentário (opcional)</label>
        <textarea
          id="avaliacao-comentario"
          rows={3}
          maxLength={MAX_COMENTARIO}
          value={comentario}
          onChange={(e) => setComentario(e.target.value)}
        />
        <small>Até {MAX_COMENTARIO} caracteres.</small>
      </div>
      {semNota ? (
        <p role="alert" className="instrucao__aviso">
          {MENSAGEM_NOTA_OBRIGATORIA}
        </p>
      ) : null}
      {estado === "falhou" ? (
        <p role="alert" className="instrucao__aviso">
          {MENSAGEM_AVALIACAO_FALHOU}
        </p>
      ) : null}
      <button type="submit" className="botao instrucao__acao" disabled={estado === "enviando"}>
        {estado === "enviando" ? "Enviando…" : "Enviar avaliação"}
      </button>
    </form>
  );
}
