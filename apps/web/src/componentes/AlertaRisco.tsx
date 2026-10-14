import { useEffect, useState } from "react";
import { PRAZO_CONFIRMACAO_CONTATO_MS } from "../risco/armazemRisco";
import { tentarNovamenteContato } from "../risco/contato";
import { useRisco } from "../risco/RiscoContext";
import "./AlertaRisco.css";

export const TEXTO_ORIENTACAO_RISCO = "Desligue a máquina da tomada e não a utilize";
export const MENSAGEM_CONTATO_NAO_REGISTRADO =
  "O contato com a nossa equipe ainda não foi registrado. Os seus dados foram guardados.";
export const MENSAGEM_NOVA_TENTATIVA_FALHOU = "Não foi possível registrar o contato agora. Tente novamente.";

/**
 * Bloco de alerta de risco de segurança (Req 8.3, 8.6).
 *
 * Aparece no topo de todas as telas enquanto o servidor mantiver a Jornada marcada
 * com risco. Não tem botão de fechar: só uma resposta do servidor o remove.
 */
export function AlertaRisco() {
  const { ativo, jornadaId, contato, contatoDesde, armazem } = useRisco();
  const [prazoVencidoDesde, setPrazoVencidoDesde] = useState<number | null>(null);
  const [tentando, setTentando] = useState(false);
  const [falhou, setFalhou] = useState(false);

  // Req 8.6: contato ainda não confirmado em 10 s conta como "não registrado".
  const aguardando = ativo && contato === "pendente";
  useEffect(() => {
    if (!aguardando) return;
    const restante = Math.max(0, PRAZO_CONFIRMACAO_CONTATO_MS - (Date.now() - contatoDesde));
    const temporizador = setTimeout(() => setPrazoVencidoDesde(contatoDesde), restante);
    return () => clearTimeout(temporizador);
  }, [aguardando, contatoDesde]);

  if (!ativo) return null;

  const naoRegistrado = contato === "nao_registrado" || (aguardando && prazoVencidoDesde === contatoDesde);

  async function tentarNovamente() {
    if (!jornadaId || tentando) return;
    setTentando(true);
    setFalhou(false);
    try {
      await tentarNovamenteContato(jornadaId, armazem);
    } catch {
      setFalhou(true);
    } finally {
      setTentando(false);
    }
  }

  return (
    <div role="alert" className="alerta-risco">
      <p className="alerta-risco__orientacao">{TEXTO_ORIENTACAO_RISCO}</p>
      {naoRegistrado ? (
        <div className="alerta-risco__contato">
          <p>{MENSAGEM_CONTATO_NAO_REGISTRADO}</p>
          {falhou ? <p>{MENSAGEM_NOVA_TENTATIVA_FALHOU}</p> : null}
          <button type="button" className="botao" onClick={() => void tentarNovamente()} disabled={tentando}>
            {tentando ? "Tentando…" : "Tentar novamente"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
