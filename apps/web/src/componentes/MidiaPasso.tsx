import { useEffect, useState } from "react";
import type { PassoInstrucao } from "../api/instrucao";

/** Tempo máximo para a mídia de um passo carregar (Req 3.4). */
export const TEMPO_MAX_MIDIA_MS = 5000;

type Carga = "carregando" | "carregada" | "falhou";
type Fonte = { tipo: "imagem" | "video"; url: string; poster?: string };

/**
 * Escolhe o que mostrar. Com movimento reduzido (Req 19.7) nada animado é
 * exibido: só a imagem estática, se houver. Sem ela, fica o texto.
 */
function escolherFonte(passo: PassoInstrucao, reduzido: boolean): Fonte | null {
  const { midia_url: url, midia_estatica_url: estatica, midia_tipo: tipo } = passo;
  if (tipo === "imagem") {
    const origem = url ?? estatica;
    return origem ? { tipo: "imagem", url: origem } : null;
  }
  if (reduzido) return estatica ? { tipo: "imagem", url: estatica } : null;
  if (!url) return estatica ? { tipo: "imagem", url: estatica } : null;
  if (tipo === "video") return { tipo: "video", url, poster: estatica };
  return { tipo: "imagem", url }; // animação em GIF/WebP é uma imagem para o navegador
}

interface Props {
  passo: PassoInstrucao;
  reduzido: boolean;
  /** Só para teste; o padrão é 5 s. */
  tempoMs?: number;
}

/**
 * Mídia de um passo. Se não carregar em 5 s (ou der erro), mostra o texto
 * alternativo no lugar, sem bloquear o avanço (Req 3.4): o botão de avançar
 * fica fora deste componente e nunca depende da mídia.
 * Use `key` com o número do passo para reiniciar o estado a cada passo.
 */
export function MidiaPasso({ passo, reduzido, tempoMs = TEMPO_MAX_MIDIA_MS }: Props) {
  const fonte = escolherFonte(passo, reduzido);
  const url = fonte?.url;
  const [carga, setCarga] = useState<Carga>("carregando");

  useEffect(() => {
    if (!url) return;
    const temporizador = setTimeout(() => setCarga((c) => (c === "carregando" ? "falhou" : c)), tempoMs);
    return () => clearTimeout(temporizador);
  }, [url, tempoMs]);

  if (!fonte || carga === "falhou") {
    return (
      <div className="midia midia--texto">
        {fonte ? <p>Não foi possível mostrar a imagem agora.</p> : null}
        <p>Descrição da imagem: {passo.alt}</p>
      </div>
    );
  }

  const aoCarregar = () => setCarga("carregada");
  const aoFalhar = () => setCarga("falhou");
  return (
    <figure className="midia">
      {fonte.tipo === "video" ? (
        <video
          src={fonte.url}
          poster={fonte.poster}
          aria-label={passo.alt}
          controls
          autoPlay
          muted
          loop
          playsInline
          onLoadedData={aoCarregar}
          onError={aoFalhar}
        />
      ) : (
        <img src={fonte.url} alt={passo.alt} onLoad={aoCarregar} onError={aoFalhar} />
      )}
      {carga === "carregando" ? <figcaption className="midia__carregando">Carregando imagem…</figcaption> : null}
    </figure>
  );
}
