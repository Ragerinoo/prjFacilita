import { useEffect, useRef } from "react";
import { carregarChamado, INTERVALO_ACOMPANHAMENTO_MS, type ChamadoPublico } from "../../api/chamado";

const visivel = () => document.visibilityState === "visible";

/**
 * Atualiza o Chamado a cada 5 s enquanto a página está visível (Req 12.8, 15.4, 15.6).
 *
 * - Oculta: não agenda nada. Ao voltar a ficar visível, consulta na hora e retoma o ciclo.
 * - Uma consulta por vez; a próxima só é marcada depois que a anterior termina.
 * - Falha numa consulta (rede, 404, 5xx) mantém o que já está na tela e tenta no ciclo seguinte.
 * - Ao desmontar (ou trocar `numero`/`ativo`), cancela o temporizador e a consulta em andamento.
 *
 * Devolve `atualizarAgora`, para refrescar depois de uma ação (por exemplo, enviar uma resposta).
 */
export function useAcompanhamento(
  numero: string,
  ativo: boolean,
  aoAtualizar: (chamado: ChamadoPublico) => void,
  intervaloMs: number = INTERVALO_ACOMPANHAMENTO_MS,
): () => void {
  const retorno = useRef(aoAtualizar);
  const agora = useRef<() => void>(() => undefined);

  useEffect(() => {
    retorno.current = aoAtualizar;
  });

  useEffect(() => {
    if (!ativo) {
      agora.current = () => undefined;
      return;
    }
    const controle = new AbortController();
    let temporizador: ReturnType<typeof setTimeout> | undefined;
    let emVoo = false;
    let repetir = false;

    const parar = () => {
      if (temporizador !== undefined) clearTimeout(temporizador);
      temporizador = undefined;
    };
    const agendar = () => {
      parar();
      if (!controle.signal.aborted && visivel()) temporizador = setTimeout(() => void consultar(), intervaloMs);
    };
    const consultar = async () => {
      parar();
      if (emVoo || controle.signal.aborted) return;
      emVoo = true;
      try {
        const chamado = await carregarChamado(numero, undefined, controle.signal);
        if (!controle.signal.aborted) retorno.current(chamado);
      } catch {
        // Mantém o último estado conhecido; a próxima tentativa vem no ciclo seguinte.
      } finally {
        emVoo = false;
        // Pedido de atualização imediata feito durante uma consulta antiga: refaz já.
        if (repetir) {
          repetir = false;
          void consultar();
        } else {
          agendar();
        }
      }
    };
    const aoMudarVisibilidade = () => {
      if (visivel()) void consultar();
      else parar();
    };

    agora.current = () => {
      if (emVoo) repetir = true;
      else void consultar();
    };
    document.addEventListener("visibilitychange", aoMudarVisibilidade);
    agendar();
    return () => {
      document.removeEventListener("visibilitychange", aoMudarVisibilidade);
      controle.abort();
      parar();
      agora.current = () => undefined;
    };
  }, [numero, ativo, intervaloMs]);

  return () => agora.current();
}
