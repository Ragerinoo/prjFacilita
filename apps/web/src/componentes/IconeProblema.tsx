import type { ReactNode } from "react";

/**
 * Ícones dos Problemas_Catalogados (Req 3.1). Desenhos simples em SVG inline,
 * sem requisição extra (Req 19.2). O traço usa `currentColor`; cores de aviso
 * ficam só no preenchimento, então o sentido nunca depende apenas da cor.
 */
const TRACO = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2.5,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

const VERMELHO = "#d32f2f";
const AMARELO = "#f9c80e";

const DESENHOS: Record<string, ReactNode> = {
  power: (
    <>
      <path d="M24 6v16" {...TRACO} />
      <path d="M14 13a15 15 0 1 0 20 0" {...TRACO} />
    </>
  ),
  "luz-vermelha": (
    <>
      <circle cx="24" cy="24" r="10" fill={VERMELHO} stroke="currentColor" strokeWidth={2.5} />
      <path d="M24 5v5M24 38v5M5 24h5M38 24h5" {...TRACO} />
    </>
  ),
  alerta: (
    <>
      <path d="M24 7 5 40h38z" fill={VERMELHO} stroke="currentColor" strokeWidth={2.5} strokeLinejoin="round" />
      <path d="M24 18v10M24 33v1" stroke="#fff" strokeWidth={3} strokeLinecap="round" />
    </>
  ),
  teclas: (
    <>
      <rect x="5" y="14" width="16" height="20" rx="4" {...TRACO} />
      <rect x="27" y="14" width="16" height="20" rx="4" {...TRACO} />
      <circle cx="13" cy="24" r="3" fill={VERMELHO} />
      <circle cx="35" cy="24" r="3" fill={VERMELHO} />
    </>
  ),
  "luz-amarela": (
    <>
      <circle cx="24" cy="24" r="10" fill={AMARELO} stroke="currentColor" strokeWidth={2.5} />
      <path d="M24 5v5M24 38v5M5 24h5M38 24h5" {...TRACO} />
    </>
  ),
  "xicara-vazia": (
    <>
      <path d="M9 17h24v11a9 9 0 0 1-9 9h-6a9 9 0 0 1-9-9z" {...TRACO} />
      <path d="M33 20h3a4 4 0 0 1 0 8h-3" {...TRACO} />
      <path d="M8 41h26" {...TRACO} />
    </>
  ),
  gota: (
    <>
      <path d="M9 17h24v11a9 9 0 0 1-9 9h-6a9 9 0 0 1-9-9z" {...TRACO} />
      <path d="M33 20h3a4 4 0 0 1 0 8h-3" {...TRACO} />
      <path d="M14 25h14" {...TRACO} strokeDasharray="2 5" />
      <path d="M21 4s5 5 5 8a5 5 0 0 1-10 0c0-3 5-8 5-8z" fill="#9ecbf5" stroke="currentColor" strokeWidth={2} />
    </>
  ),
  termometro: (
    <>
      <path d="M20 29V9a4 4 0 0 1 8 0v20a8 8 0 1 1-8 0z" {...TRACO} />
      <path d="M24 17v14" {...TRACO} />
      <path d="M36 12v8M32 16h8" {...TRACO} />
    </>
  ),
  alavanca: (
    <>
      <path d="M10 38V22a14 14 0 0 1 28 0" {...TRACO} />
      <path d="M10 38h-3M41 38h-3" {...TRACO} />
      <rect x="18" y="30" width="12" height="12" rx="3" {...TRACO} />
      <path d="M36 8 12 32" stroke={VERMELHO} strokeWidth={3} strokeLinecap="round" />
    </>
  ),
  vazamento: (
    <>
      <path d="M24 5s11 11 11 19a11 11 0 0 1-22 0c0-8 11-19 11-19z" fill="#9ecbf5" stroke="currentColor" strokeWidth={2.5} strokeLinejoin="round" />
      <path d="M8 43h32" {...TRACO} />
    </>
  ),
  reservatorio: (
    <>
      <path d="M12 8h24l-2 32a3 3 0 0 1-3 3H17a3 3 0 0 1-3-3z" {...TRACO} />
      <path d="M14 24h20" {...TRACO} />
      <path d="M17 31h14" {...TRACO} />
    </>
  ),
  bico: (
    <>
      <path d="M8 8h32v10H8z" {...TRACO} />
      <path d="M20 18v10h8V18" {...TRACO} />
      <path d="M24 33v4M20 40v2M28 40v2" {...TRACO} />
    </>
  ),
  capsula: (
    <>
      <path d="M12 12h24l-4 26a4 4 0 0 1-4 3h-8a4 4 0 0 1-4-3z" {...TRACO} />
      <path d="M12 12a12 5 0 0 1 24 0" {...TRACO} />
      <path d="M18 24h12" {...TRACO} />
    </>
  ),
};

/** Ícone genérico para um nome desconhecido: ponto de interrogação num círculo. */
const PADRAO = (
  <>
    <circle cx="24" cy="24" r="17" {...TRACO} />
    <path d="M19 19a5 5 0 1 1 7 4.5c-1.5.8-2 1.8-2 3.5M24 33v1" {...TRACO} />
  </>
);

interface Props {
  nome: string;
  /** Texto alternativo do ícone (Req 3.1). */
  alt: string;
}

export function IconeProblema({ nome, alt }: Props) {
  return (
    <svg
      className="icone-problema"
      viewBox="0 0 48 48"
      width="48"
      height="48"
      role="img"
      aria-label={alt}
      focusable="false"
    >
      {DESENHOS[nome] ?? PADRAO}
    </svg>
  );
}
