/**
 * Abas WAI-ARIA do Dashboard (spec insights-gestor, D11; Req 25.1, 25.9 a 25.13, 25.16).
 *
 * Os dois `tabpanel` existem sempre (para `aria-controls` apontar para um elemento real), mas
 * só o painel selecionado recebe conteúdo; o outro fica `hidden` e vazio. Assim há no máximo um
 * painel visível e o conteúdo de uma aba (como o `lazy` do Recharts) só é montado quando ela abre.
 *
 * Ativação automática: a seta, Home e End movem o foco e a seleção juntos. A aba selecionada se
 * distingue por `aria-selected` e por estilo que não depende só de cor (classes em `dashboard.css`).
 */
import { useId, useRef } from "react";
import type { KeyboardEvent, ReactNode } from "react";

/** Uma aba e o conteúdo do seu painel (renderizado só quando a aba está selecionada). */
export interface AbaDeclarada<Id extends string> {
  id: Id;
  rotulo: string;
  painel: ReactNode;
}

export interface PropsSeletorDeAbas<Id extends string> {
  /** As abas, na ordem de exibição. */
  abas: readonly AbaDeclarada<Id>[];
  /** Aba selecionada. */
  selecionada: Id;
  /** Chamado ao selecionar uma aba (clique ou teclado). */
  aoSelecionar: (id: Id) => void;
}

/**
 * Aba de destino de uma tecla, ou `null` se a tecla não navega entre abas.
 * Setas com volta circular; Home vai à primeira; End, à última.
 */
export function proximaAba<Id extends string>(
  abas: readonly Id[],
  atual: Id,
  tecla: string,
): Id | null {
  const total = abas.length;
  if (total === 0) return null;
  const indice = abas.indexOf(atual);
  switch (tecla) {
    case "ArrowRight":
      return abas[(indice + 1) % total] ?? null;
    case "ArrowLeft":
      return abas[(indice - 1 + total) % total] ?? null;
    case "Home":
      return abas[0] ?? null;
    case "End":
      return abas[total - 1] ?? null;
    default:
      return null;
  }
}

export function SeletorDeAbas<Id extends string>({
  abas,
  selecionada,
  aoSelecionar,
}: PropsSeletorDeAbas<Id>) {
  const base = useId();
  const botoes = useRef(new Map<Id, HTMLButtonElement>());
  const ids = abas.map((aba) => aba.id);

  const idDaAba = (id: Id) => `${base}-aba-${id}`;
  const idDoPainel = (id: Id) => `${base}-painel-${id}`;

  function aoTeclar(evento: KeyboardEvent<HTMLButtonElement>, atual: Id) {
    const destino = proximaAba(ids, atual, evento.key);
    if (destino === null) return;
    evento.preventDefault();
    aoSelecionar(destino);
    botoes.current.get(destino)?.focus();
  }

  return (
    <div className="dashboard-abas">
      <div role="tablist" aria-label="Seções do Dashboard" className="dashboard-abas__lista">
        {abas.map((aba) => {
          const ativa = aba.id === selecionada;
          return (
            <button
              key={aba.id}
              type="button"
              role="tab"
              id={idDaAba(aba.id)}
              aria-selected={ativa}
              aria-controls={idDoPainel(aba.id)}
              tabIndex={ativa ? 0 : -1}
              className="dashboard-abas__aba"
              ref={(elemento) => {
                if (elemento) botoes.current.set(aba.id, elemento);
                else botoes.current.delete(aba.id);
              }}
              onClick={() => aoSelecionar(aba.id)}
              onKeyDown={(evento) => aoTeclar(evento, aba.id)}
            >
              {aba.rotulo}
            </button>
          );
        })}
      </div>
      {abas.map((aba) => {
        const ativa = aba.id === selecionada;
        return (
          <div
            key={aba.id}
            role="tabpanel"
            id={idDoPainel(aba.id)}
            aria-labelledby={idDaAba(aba.id)}
            hidden={!ativa}
            className="dashboard-abas__painel"
          >
            {ativa ? aba.painel : null}
          </div>
        );
      })}
    </div>
  );
}
