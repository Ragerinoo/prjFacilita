import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { carregarChamado, chamadoNaoEncontrado, type ChamadoPublico, type DadoPessoal } from "../api/chamado";
import { AgendamentoLigacao, AvaliacaoChamado, StatusChamado } from "./chamado/AcompanhamentoChamado";
import { ConfirmacaoChamado } from "./chamado/ConfirmacaoChamado";
import { ConsultaChamado } from "./chamado/ConsultaChamado";
import { ContatoChamado } from "./chamado/ContatoChamado";
import { FotosChamado } from "./chamado/FotosChamado";
import { MensagensChamado } from "./chamado/MensagensChamado";
import { useAcompanhamento } from "./chamado/useAcompanhamento";
import "./Chamado.css";

export const MENSAGEM_CHAMADO_NAO_ENCONTRADO = "Não encontramos esse chamado. Confira o número e tente de novo.";
export const MENSAGEM_ERRO_CHAMADO = "Não foi possível abrir o seu chamado agora. Tente de novo.";

type Estado =
  | { tipo: "carregando" }
  | { tipo: "erro" }
  | { tipo: "nao_encontrado" }
  | { tipo: "pronto"; chamado: ChamadoPublico };

/**
 * `chamado` é atualizado a cada 5 s (status, mensagens e agendamento). Os formulários de contato e de fotos
 * só usam o valor inicial: o que o Consumidor digita ou anexa não muda por causa da atualização.
 */
function ChamadoCarregado({ chamado, atualizarAgora }: { chamado: ChamadoPublico; atualizarAgora: () => void }) {
  const [solicitados, setSolicitados] = useState<DadoPessoal[]>(chamado.dadosSolicitados);
  return (
    <>
      <ConfirmacaoChamado chamado={chamado} />
      <StatusChamado status={chamado.status} />
      <AgendamentoLigacao agendamento={chamado.agendamento} />
      <MensagensChamado
        numero={chamado.numero}
        status={chamado.status}
        mensagens={chamado.mensagens}
        aoEnviar={atualizarAgora}
      />
      <AvaliacaoChamado chamado={chamado} />
      <ContatoChamado numero={chamado.numero} solicitados={solicitados} aoAtualizar={setSolicitados} />
      <FotosChamado numero={chamado.numero} anexosIniciais={chamado.anexosTotal} />
    </>
  );
}

export function Component() {
  const { numero = "" } = useParams();
  if (!numero) return <PaginaConsulta />;
  return <PaginaChamado key={numero} numero={numero} />;
}

/** `/chamado` sem número: só o campo para consultar (Req 12.8, 12.11). */
function PaginaConsulta() {
  return (
    <section className="chamado">
      <h1>Acompanhe o seu chamado</h1>
      <p>Digite o número que você recebeu ao abrir o chamado.</p>
      <ConsultaChamado />
    </section>
  );
}

function PaginaChamado({ numero }: { numero: string }) {
  const [estado, setEstado] = useState<Estado>({ tipo: "carregando" });
  const [tentativa, setTentativa] = useState(0);

  useEffect(() => {
    const controle = new AbortController();
    carregarChamado(numero, undefined, controle.signal).then(
      (chamado) => {
        if (!controle.signal.aborted) setEstado({ tipo: "pronto", chamado });
      },
      (erro: unknown) => {
        if (controle.signal.aborted) return;
        setEstado({ tipo: chamadoNaoEncontrado(erro) ? "nao_encontrado" : "erro" });
      },
    );
    return () => controle.abort();
    // `tentativa` repete a consulta depois de "Tentar novamente".
  }, [numero, tentativa]);

  const atualizarAgora = useAcompanhamento(
    numero,
    estado.tipo === "pronto",
    useCallback((chamado: ChamadoPublico) => setEstado({ tipo: "pronto", chamado }), []),
  );

  const tentarNovamente = useCallback(() => {
    setEstado({ tipo: "carregando" });
    setTentativa((t) => t + 1);
  }, []);

  return (
    <section className="chamado">
      <h1>Acompanhe o seu chamado</h1>
      {estado.tipo === "carregando" ? <p role="status">Carregando o seu chamado…</p> : null}
      {estado.tipo === "nao_encontrado" ? (
        <div role="alert" className="chamado__aviso">
          <p>{MENSAGEM_CHAMADO_NAO_ENCONTRADO}</p>
        </div>
      ) : null}
      {estado.tipo === "nao_encontrado" ? (
        <>
          <p>Quer tentar outro número?</p>
          <ConsultaChamado numeroInicial={numero} numeroAtual={numero} aoRepetir={tentarNovamente} />
          <Link to="/">Voltar ao início</Link>
        </>
      ) : null}
      {estado.tipo === "erro" ? (
        <div role="alert" className="chamado__aviso">
          <p>{MENSAGEM_ERRO_CHAMADO}</p>
          <button type="button" className="botao" onClick={tentarNovamente}>
            Tentar novamente
          </button>
        </div>
      ) : null}
      {estado.tipo === "pronto" ? <ChamadoCarregado chamado={estado.chamado} atualizarAgora={atualizarAgora} /> : null}
    </section>
  );
}
