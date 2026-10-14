import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import type { EstadoAbrirChamado } from "../api/abrirChamado";
import { api } from "../api/cliente";
import { filaEventos } from "../api/filaEventos";
import {
  carregarInstrucao,
  informarVazamento,
  registrarResolucao,
  type Instrucao,
  type VarianteInstrucao,
} from "../api/instrucao";
import { lerJornadaId, lerRascunho, salvarRascunho } from "../api/jornada";
import { iniciarJornadaQr } from "../api/qr";
import { novoUlid } from "../api/ulid";
import { AvaliacaoEstrelas } from "../componentes/AvaliacaoEstrelas";
import { MidiaPasso } from "../componentes/MidiaPasso";
import { useMovimentoReduzido } from "../componentes/useMovimentoReduzido";
import "./Instrucao.css";

/** Posição do "Vazamento" na lista fixa dos 13 problemas (Req 3.1). */
export const ID_PROBLEMA_VAZAMENTO = "10";
/** Quantas vezes "Tentar novamente" pode repetir o repasse (Req 5.6). */
export const MAX_NOVAS_TENTATIVAS_REPASSE = 3;

export const MENSAGEM_ERRO_INSTRUCAO = "Não foi possível abrir a instrução agora. Tente novamente.";
export const MENSAGEM_SEM_INSTRUCAO = "Não temos instrução disponível para esse modelo.";
export const MENSAGEM_FALHA_RESPOSTA = "Não foi possível registrar a sua resposta. Tente novamente.";
export const MENSAGEM_REPASSE_NAO_INICIADO =
  "O encaminhamento para uma pessoa não foi iniciado. Seus dados foram guardados.";
export const TEXTO_PREFIRO_ASSISTENTE = "Prefiro abrir um chamado";

type Repasse = { estado: "enviando" } | { estado: "ok"; numero?: string } | { estado: "erro"; tentativas: number };
type MotivoRepasse = "nao_resolveu" | "vazamento_interno";

type Fase =
  | { tipo: "carregando" }
  | { tipo: "erro"; variante?: VarianteInstrucao }
  | { tipo: "sem_instrucao" }
  | { tipo: "vazamento" }
  | { tipo: "passos"; instrucao: Instrucao }
  | { tipo: "pergunta"; falha: boolean }
  | { tipo: "avaliacao" }
  | { tipo: "repasse"; motivo: MotivoRepasse; repasse: Repasse };

/** Título de seção que recebe o foco ao aparecer, para quem usa teclado ou leitor de tela. */
function Titulo({ id, children }: { id: string; children: ReactNode }) {
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, []);
  return (
    <h2 id={id} ref={ref} tabIndex={-1}>
      {children}
    </h2>
  );
}

function idDoProblema(problemaId: string): string | number {
  return /^\d+$/.test(problemaId) ? Number(problemaId) : problemaId;
}

/* ---------------------------- vistas de cada fase --------------------------- */

function PerguntaVazamento({ aoResponder }: { aoResponder: (tipo: "externo" | "interno") => void }) {
  return (
    <section aria-labelledby="pergunta-vazamento">
      <Titulo id="pergunta-vazamento">O vazamento é externo ou interno?</Titulo>
      <div className="grupo-alvos grupo-alvos--coluna">
        <button type="button" className="botao botao--secundario instrucao__opcao" onClick={() => aoResponder("externo")}>
          Externo: a água escorre por fora da máquina
        </button>
        <button type="button" className="botao botao--secundario instrucao__opcao" onClick={() => aoResponder("interno")}>
          Interno: a água sai de dentro da máquina
        </button>
      </div>
    </section>
  );
}

interface PropsPassos {
  instrucao: Instrucao;
  jornadaId: string;
  problemaId: string;
  aoConcluir: () => void;
}

/** Um passo por vez. A mídia nunca bloqueia o botão de avançar (Req 3.4). */
function Passos({ instrucao, jornadaId, problemaId, aoConcluir }: PropsPassos) {
  const reduzido = useMovimentoReduzido();
  const [indice, setIndice] = useState(0);
  const exibidos = useRef(new Set<number>());
  const passo = instrucao.passos[indice];
  const total = instrucao.passos.length;
  const ultimo = indice === total - 1;

  const registrar = useCallback(
    (tipo: "exibido" | "concluido", numeroPasso: number) => {
      // Req 3.9 e 3.12: vai para a fila local; falha de rede não interrompe o fluxo.
      filaEventos.enfileirar(`/jornadas/${encodeURIComponent(jornadaId)}/eventos`, {
        tipo,
        problema_id: idDoProblema(problemaId),
        passo: numeroPasso,
        ocorrido_em: new Date().toISOString(),
      });
    },
    [jornadaId, problemaId],
  );

  const numeroAtual = passo?.n;
  useEffect(() => {
    if (numeroAtual === undefined || exibidos.current.has(numeroAtual)) return;
    exibidos.current.add(numeroAtual);
    registrar("exibido", numeroAtual);
  }, [numeroAtual, registrar]);

  if (!passo) return null;

  const concluirPasso = () => {
    registrar("concluido", passo.n);
    if (ultimo) aoConcluir();
    else setIndice((i) => i + 1);
  };

  return (
    <article key={passo.n} className="passo" aria-labelledby="passo-titulo">
      <Titulo id="passo-titulo">
        Passo {indice + 1} de {total}
      </Titulo>
      <p className="passo__texto">{passo.texto}</p>
      <MidiaPasso key={`${passo.n}|${reduzido}`} passo={passo} reduzido={reduzido} />
      <p className="passo__equivalente">
        <strong>Em texto:</strong> {passo.texto_equivalente}
      </p>
      <button type="button" className="botao instrucao__acao" onClick={concluirPasso}>
        {ultimo ? "Fiz o último passo" : "Fiz este passo, ir para o próximo"}
      </button>
    </article>
  );
}

interface PropsPergunta {
  falha: boolean;
  aoResponder: (resolvido: boolean) => void;
}

function PerguntaResolvido({ falha, aoResponder }: PropsPergunta) {
  return (
    <section aria-labelledby="pergunta-resolvido">
      <Titulo id="pergunta-resolvido">O problema foi solucionado?</Titulo>
      {falha ? (
        <p role="alert" className="instrucao__aviso">
          {MENSAGEM_FALHA_RESPOSTA}
        </p>
      ) : null}
      <div className="grupo-alvos">
        <button type="button" className="botao instrucao__opcao" onClick={() => aoResponder(true)}>
          Sim
        </button>
        <button type="button" className="botao botao--secundario instrucao__opcao" onClick={() => aoResponder(false)}>
          Não
        </button>
      </div>
    </section>
  );
}

interface PropsRepasse {
  motivo: MotivoRepasse;
  repasse: Repasse;
  aoTentarNovamente: () => void;
  aoPreferirAssistente: () => void;
}

/**
 * Confirmação provisória do repasse (Req 5.3, 5.4, 5.6). A página completa do
 * Chamado (número, prazo, contato) é a tarefa 14.6; aqui só levamos até ela.
 * Vazamento interno é risco de segurança: não oferece o assistente (Req 8.4).
 */
function RepasseVista({ motivo, repasse, aoTentarNovamente, aoPreferirAssistente }: PropsRepasse) {
  const interno = motivo === "vazamento_interno";
  const botaoAssistente = interno ? null : (
    <button type="button" className="botao botao--secundario instrucao__opcao" onClick={aoPreferirAssistente}>
      {TEXTO_PREFIRO_ASSISTENTE}
    </button>
  );
  return (
    <section aria-labelledby="titulo-repasse">
      <Titulo id="titulo-repasse">{interno ? "Por segurança, uma pessoa vai ajudar você" : "Vamos encaminhar você a uma pessoa"}</Titulo>
      {interno ? <p>Não vamos mostrar passos para esse tipo de vazamento.</p> : null}
      {repasse.estado === "enviando" ? (
        <p role="status">Encaminhando o seu caso…</p>
      ) : repasse.estado === "ok" ? (
        <>
          <p role="status">O seu caso foi encaminhado a uma pessoa.</p>
          {repasse.numero ? (
            <>
              <p>
                Número do chamado: <strong>{repasse.numero}</strong>
              </p>
              <div className="grupo-alvos grupo-alvos--coluna">
                <Link className="botao instrucao__opcao" to={`/chamado/${encodeURIComponent(repasse.numero)}`}>
                  Acompanhar o meu chamado
                </Link>
                {botaoAssistente}
              </div>
            </>
          ) : (
            botaoAssistente
          )}
        </>
      ) : (
        <>
          <p role="alert" className="instrucao__aviso">
            {MENSAGEM_REPASSE_NAO_INICIADO}
          </p>
          <div className="grupo-alvos grupo-alvos--coluna">
            {repasse.tentativas < MAX_NOVAS_TENTATIVAS_REPASSE ? (
              <button type="button" className="botao instrucao__opcao" onClick={aoTentarNovamente}>
                Tentar novamente
              </button>
            ) : null}
            {botaoAssistente}
          </div>
        </>
      )}
    </section>
  );
}

function SemInstrucao({ modeloId, aoAbrirAssistente }: { modeloId: string; aoAbrirAssistente: () => void }) {
  return (
    <section aria-labelledby="sem-instrucao">
      <Titulo id="sem-instrucao">{MENSAGEM_SEM_INSTRUCAO}</Titulo>
      <p>Você pode abrir um chamado para a nossa equipe ou voltar e escolher outra opção.</p>
      <div className="grupo-alvos grupo-alvos--coluna">
        <button type="button" className="botao instrucao__opcao" onClick={aoAbrirAssistente}>
          Abrir chamado
        </button>
        <Link className="botao botao--secundario instrucao__opcao" to={`/m/${encodeURIComponent(modeloId)}`}>
          Voltar para a página da máquina
        </Link>
      </div>
    </section>
  );
}

/* --------------------------------- fluxo ----------------------------------- */

interface PropsFluxo {
  jornadaId: string;
  modeloId: string;
  problemaId: string;
}

/** O que mostrar ao abrir a tela. No vazamento, a pergunta vem antes de qualquer passo (Req 3.7). */
function estadoInicial(jornadaId: string, problemaId: string): { fase: Fase; carregar: boolean; variante?: VarianteInstrucao } {
  if (problemaId !== ID_PROBLEMA_VAZAMENTO) return { fase: { tipo: "carregando" }, carregar: true };
  const resposta = lerRascunho<string>(`vazamento.${jornadaId}`);
  if (resposta === "externo") return { fase: { tipo: "carregando" }, carregar: true, variante: "externo" };
  if (resposta === "interno") {
    return { fase: { tipo: "repasse", motivo: "vazamento_interno", repasse: { estado: "ok" } }, carregar: false };
  }
  return { fase: { tipo: "vazamento" }, carregar: false };
}

function Fluxo({ jornadaId, modeloId, problemaId }: PropsFluxo) {
  const navegar = useNavigate();
  const [inicial] = useState(() => estadoInicial(jornadaId, problemaId));
  const [fase, setFase] = useState<Fase>(inicial.fase);
  const ocupado = useRef(false);
  const ids = useRef<Record<string, string>>({});
  /** Mesmo `evento_id` em cada nova tentativa da mesma ação (idempotência no servidor). */
  const idPara = (chave: string) => (ids.current[chave] ??= novoUlid());

  const abrirPassos = useCallback(
    async (variante?: VarianteInstrucao, sinal?: AbortSignal) => {
      try {
        const instrucao = await carregarInstrucao(jornadaId, problemaId, variante, api, sinal);
        if (sinal?.aborted) return;
        setFase(instrucao ? { tipo: "passos", instrucao } : { tipo: "sem_instrucao" });
      } catch {
        if (sinal?.aborted) return;
        setFase({ tipo: "erro", variante });
      }
    },
    [jornadaId, problemaId],
  );

  const { carregar, variante: varianteInicial } = inicial;
  useEffect(() => {
    if (!carregar) return;
    const controle = new AbortController();
    void abrirPassos(varianteInicial, controle.signal);
    return () => controle.abort();
  }, [carregar, varianteInicial, abrirPassos]);

  async function responderVazamento(tipo: "externo" | "interno") {
    if (tipo === "interno") {
      await iniciarRepasse("vazamento_interno", 0);
      return;
    }
    salvarRascunho(`vazamento.${jornadaId}`, tipo);
    // Externo: 2 toques até o primeiro passo (Req 3.5); o registro vai pela fila e não bloqueia.
    filaEventos.enfileirar(`/jornadas/${encodeURIComponent(jornadaId)}/vazamento`, { tipo: "externo" });
    setFase({ tipo: "carregando" });
    await abrirPassos("externo");
  }

  async function iniciarRepasse(motivo: MotivoRepasse, tentativas: number) {
    setFase({ tipo: "repasse", motivo, repasse: { estado: "enviando" } });
    try {
      const { numero } =
        motivo === "nao_resolveu"
          ? await registrarResolucao(jornadaId, {
              resolvido: false,
              problemaId: idDoProblema(problemaId),
              eventoId: idPara("resolucao-nao"),
            })
          : await informarVazamento(jornadaId, "interno", idPara("vazamento-interno"));
      // Guardado só depois do sucesso: ao recarregar, não voltamos a perguntar nem mostramos passos.
      if (motivo === "vazamento_interno") salvarRascunho(`vazamento.${jornadaId}`, "interno");
      setFase({ tipo: "repasse", motivo, repasse: { estado: "ok", numero } });
    } catch {
      setFase({ tipo: "repasse", motivo, repasse: { estado: "erro", tentativas } });
    }
  }

  async function responder(resolvido: boolean) {
    if (ocupado.current) return;
    if (!resolvido) {
      await iniciarRepasse("nao_resolveu", 0);
      return;
    }
    ocupado.current = true;
    try {
      await registrarResolucao(jornadaId, {
        resolvido: true,
        problemaId: idDoProblema(problemaId),
        eventoId: idPara("resolucao-sim"),
      });
      setFase({ tipo: "avaliacao" });
    } catch {
      setFase({ tipo: "pergunta", falha: true });
    } finally {
      ocupado.current = false;
    }
  }

  /** Em vez do assistente, leva ao formulário de chamado com o contexto do fluxo. */
  function abrirAssistente() {
    const estado: EstadoAbrirChamado = { contexto: `Fluxo ${problemaId} - modelo ${modeloId}` };
    void navegar("/abrir-chamado", { state: estado });
  }

  switch (fase.tipo) {
    case "carregando":
      return (
        <p role="status" className="carregando">
          Carregando…
        </p>
      );
    case "erro":
      return (
        <div role="alert" className="instrucao__aviso">
          <p>{MENSAGEM_ERRO_INSTRUCAO}</p>
          <button
            type="button"
            className="botao"
            onClick={() => {
              setFase({ tipo: "carregando" });
              void abrirPassos(fase.variante);
            }}
          >
            Tentar novamente
          </button>
        </div>
      );
    case "sem_instrucao":
      return <SemInstrucao modeloId={modeloId} aoAbrirAssistente={abrirAssistente} />;
    case "vazamento":
      return <PerguntaVazamento aoResponder={(tipo) => void responderVazamento(tipo)} />;
    case "passos":
      return (
        <Passos
          instrucao={fase.instrucao}
          jornadaId={jornadaId}
          problemaId={problemaId}
          aoConcluir={() => setFase({ tipo: "pergunta", falha: false })}
        />
      );
    case "pergunta":
      return <PerguntaResolvido falha={fase.falha} aoResponder={(r) => void responder(r)} />;
    case "avaliacao":
      return (
        <section aria-labelledby="titulo-avaliacao">
          <Titulo id="titulo-avaliacao">Que bom que deu certo!</Titulo>
          <AvaliacaoEstrelas jornadaId={jornadaId} />
        </section>
      );
    case "repasse":
      return (
        <RepasseVista
          motivo={fase.motivo}
          repasse={fase.repasse}
          aoTentarNovamente={() =>
            void iniciarRepasse(fase.motivo, fase.repasse.estado === "erro" ? fase.repasse.tentativas + 1 : 0)
          }
          aoPreferirAssistente={abrirAssistente}
        />
      );
  }
}

type EstadoJornada = { tipo: "carregando" } | { tipo: "erro" } | { tipo: "pronta"; id: string };

/** Garante a Jornada. Normalmente ela já existe (criada na Pagina_Maquina); sem ela, abre uma nova. */
function Guia({ modeloId, problemaId }: { modeloId: string; problemaId: string }) {
  const [jornada, setJornada] = useState<EstadoJornada>(() => {
    const existente = lerJornadaId();
    return existente ? { tipo: "pronta", id: existente } : { tipo: "carregando" };
  });
  const [tentativa, setTentativa] = useState(0);

  const pronta = jornada.tipo === "pronta";
  useEffect(() => {
    if (pronta) return;
    let cancelado = false;
    iniciarJornadaQr({ modeloId, origem: "busca" }).then(
      (id) => {
        if (!cancelado) setJornada({ tipo: "pronta", id });
      },
      () => {
        if (!cancelado) setJornada({ tipo: "erro" });
      },
    );
    return () => {
      cancelado = true;
    };
    // `tentativa` reinicia a criação depois de "Tentar novamente".
  }, [pronta, modeloId, tentativa]);

  if (jornada.tipo === "pronta") {
    return <Fluxo jornadaId={jornada.id} modeloId={modeloId} problemaId={problemaId} />;
  }
  if (jornada.tipo === "erro") {
    return (
      <div role="alert" className="instrucao__aviso">
        <p>{MENSAGEM_ERRO_INSTRUCAO}</p>
        <button
          type="button"
          className="botao"
          onClick={() => {
            setJornada({ tipo: "carregando" });
            setTentativa((n) => n + 1);
          }}
        >
          Tentar novamente
        </button>
      </div>
    );
  }
  return (
    <p role="status" className="carregando">
      Carregando…
    </p>
  );
}

/**
 * Rota `/m/:modeloId/p/:problemaId`: instrução em passos, "O problema foi
 * solucionado?", avaliação e repasse (Req 3 e 5).
 */
export function Component() {
  const { modeloId, problemaId } = useParams();
  if (!modeloId || !problemaId) return <Navigate to="/" replace />;
  return (
    <section className="instrucao">
      <h1>Como resolver</h1>
      <Guia key={`${modeloId}|${problemaId}`} modeloId={modeloId} problemaId={problemaId} />
    </section>
  );
}
