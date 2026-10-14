import { useEffect, useId, useState, type FormEvent } from "react";
import { ErroApi } from "../../api/cliente";
import { apiCs } from "../clienteCs";
import type { CardChamado } from "./tipos";
import { formatarData } from "./tipos";

/**
 * Ações do atendimento (tarefa 15.4): sugestão da IA, resposta com confirmação, instrução do
 * manual, Ordem_Servico, agendamento de ligação, encerramento e Cache_Respostas.
 */
export interface PropsAcoesChamado {
  card: CardChamado;
  aoAtualizar: () => void;
}

interface RespostaSugestao {
  sugestao: string | null;
  origem: "ia" | "modelo_local" | null;
  mensagem: string | null;
}

interface RespostaEncerrar {
  oferecer_cache: boolean;
}

interface RespostaCache {
  criada: boolean;
  ja_existe: boolean;
  aviso?: string;
}

interface RespostaOs {
  os_id: string;
  criada_agora: boolean;
  confirmada_agora: boolean;
}

const rotaChamado = (numero: string) => `/chamados/${encodeURIComponent(numero)}`;

/** Mensagem principal e erros por campo (422) de um erro da API. */
function descreverErro(e: unknown, padrao: string): { mensagem: string; campos: Record<string, string> } {
  const campos: Record<string, string> = {};
  if (e instanceof ErroApi && e.tipo === "http") {
    for (const c of e.campos ?? []) campos[c.campo] = c.motivo;
    return { mensagem: e.message, campos };
  }
  return { mensagem: padrao, campos };
}

function Aviso({ erro, ok }: { erro: string | null; ok?: string | null }) {
  return (
    <>
      {erro && <p role="alert">{erro}</p>}
      {ok && <p role="status">{ok}</p>}
    </>
  );
}

function ErroCampo({ id, texto }: { id: string; texto?: string }) {
  return texto ? (
    <span id={id} role="alert">
      {texto}
    </span>
  ) : null;
}

function RespostaConsumidor({ card, aoAtualizar, travado }: PropsAcoesChamado & { travado: boolean }) {
  const id = useId();
  const [texto, setTexto] = useState("");
  const [carregando, setCarregando] = useState(true);
  const [aviso, setAviso] = useState<string | null>(null);
  const [confirmando, setConfirmando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [erroTexto, setErroTexto] = useState<string | undefined>();
  const [ok, setOk] = useState<string | null>(null);

  useEffect(() => {
    let ativo = true;
    setCarregando(true);
    apiCs
      .get<RespostaSugestao>(`${rotaChamado(card.numero)}/sugestao`)
      .then((r) => {
        if (!ativo) return;
        if (r.sugestao) setTexto((atual) => (atual === "" ? (r.sugestao ?? "") : atual));
        else setAviso(r.mensagem ?? "Sugestão indisponível.");
      })
      .catch(() => {
        if (ativo) setAviso("Sugestão indisponível.");
      })
      .finally(() => {
        if (ativo) setCarregando(false);
      });
    return () => {
      ativo = false;
    };
  }, [card.numero]);

  async function enviar() {
    setEnviando(true);
    setErro(null);
    setErroTexto(undefined);
    setOk(null);
    try {
      await apiCs.post(`${rotaChamado(card.numero)}/mensagens`, { texto, confirmada: true });
      setTexto("");
      setConfirmando(false);
      setOk("Mensagem enviada ao consumidor.");
      aoAtualizar();
    } catch (e) {
      const d = descreverErro(e, "Não foi possível enviar a mensagem. O texto foi mantido; tente de novo.");
      setErro(d.mensagem);
      setErroTexto(d.campos.mensagem);
      setConfirmando(false); // o texto digitado permanece no campo (Req 15.8)
      if (e instanceof ErroApi && e.status === 409) aoAtualizar();
    } finally {
      setEnviando(false);
    }
  }

  function aoSubmeter(ev: FormEvent) {
    ev.preventDefault();
    setOk(null);
    setConfirmando(true);
  }

  return (
    <section aria-labelledby={`${id}-t`}>
      <h3 id={`${id}-t`}>Responder ao consumidor</h3>
      <form onSubmit={aoSubmeter}>
        <label htmlFor={`${id}-texto`}>Mensagem (sugestão da IA editável)</label>
        <textarea
          id={`${id}-texto`}
          value={texto}
          rows={5}
          maxLength={2000}
          disabled={travado}
          aria-describedby={erroTexto ? `${id}-erro` : undefined}
          aria-invalid={erroTexto ? true : undefined}
          onChange={(e) => {
            setTexto(e.target.value);
            setConfirmando(false);
          }}
        />
        <ErroCampo id={`${id}-erro`} texto={erroTexto} />
        {carregando && <p role="status">Carregando sugestão…</p>}
        {!carregando && aviso && <p role="status">{aviso}</p>}
        {!confirmando ? (
          <button type="submit" disabled={travado || enviando || texto.trim() === ""}>
            Enviar mensagem
          </button>
        ) : (
          <div role="group" aria-label="Confirmar envio">
            <p>Enviar esta mensagem ao consumidor?</p>
            <button type="button" onClick={enviar} disabled={enviando}>
              {enviando ? "Enviando…" : "Confirmar envio"}
            </button>{" "}
            <button type="button" onClick={() => setConfirmando(false)} disabled={enviando}>
              Cancelar
            </button>
          </div>
        )}
        <Aviso erro={erro} ok={ok} />
      </form>
    </section>
  );
}

function InstrucaoManual({ card, aoAtualizar, travado }: PropsAcoesChamado & { travado: boolean }) {
  const id = useId();
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  async function enviar(ev: FormEvent) {
    ev.preventDefault();
    setEnviando(true);
    setErro(null);
    setOk(null);
    try {
      await apiCs.post(`${rotaChamado(card.numero)}/mensagens`, { texto, confirmada: true });
      setTexto("");
      setOk("Instrução do manual enviada.");
      aoAtualizar();
    } catch (e) {
      setErro(descreverErro(e, "Não foi possível enviar a instrução. O texto foi mantido.").mensagem);
      if (e instanceof ErroApi && e.status === 409) aoAtualizar();
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section aria-labelledby={`${id}-t`}>
      <h3 id={`${id}-t`}>Enviar instrução do manual</h3>
      <form onSubmit={enviar}>
        <label htmlFor={`${id}-texto`}>Texto da instrução</label>
        <textarea
          id={`${id}-texto`}
          value={texto}
          rows={3}
          maxLength={2000}
          disabled={travado}
          onChange={(e) => setTexto(e.target.value)}
        />
        <button type="submit" disabled={travado || enviando || texto.trim() === ""}>
          {enviando ? "Enviando…" : "Enviar instrução do manual"}
        </button>
        <Aviso erro={erro} ok={ok} />
      </form>
    </section>
  );
}

function OrdemServicoAcao({ card, aoAtualizar, travado }: PropsAcoesChamado & { travado: boolean }) {
  const id = useId();
  const [enviando, setEnviando] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  async function confirmar() {
    setEnviando(true);
    setErro(null);
    setOk(null);
    try {
      const r = await apiCs.post<RespostaOs>(`${rotaChamado(card.numero)}/ordem-servico`);
      setOk(`Ordem de serviço ${r.os_id} confirmada.`);
      setConfirmando(false);
      aoAtualizar();
    } catch (e) {
      setErro(descreverErro(e, "Não foi possível confirmar a ordem de serviço. Tente de novo.").mensagem);
      if (e instanceof ErroApi && e.status === 409) aoAtualizar();
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section aria-labelledby={`${id}-t`}>
      <h3 id={`${id}-t`}>Ordem de serviço</h3>
      <p>Situação: {card.os_status ?? "não aberta"}</p>
      {!confirmando ? (
        <button type="button" disabled={travado || enviando} onClick={() => setConfirmando(true)}>
          Abrir ordem de serviço
        </button>
      ) : (
        <div role="group" aria-label="Confirmar ordem de serviço">
          <p>Confirmar a abertura da ordem de serviço?</p>
          <button type="button" onClick={confirmar} disabled={enviando}>
            {enviando ? "Confirmando…" : "Confirmar ordem de serviço"}
          </button>{" "}
          <button type="button" onClick={() => setConfirmando(false)} disabled={enviando}>
            Cancelar
          </button>
        </div>
      )}
      <Aviso erro={erro} ok={ok} />
    </section>
  );
}

function AgendarLigacao({ card, aoAtualizar, travado }: PropsAcoesChamado & { travado: boolean }) {
  const id = useId();
  const [data, setData] = useState("");
  const [hora, setHora] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [campos, setCampos] = useState<Record<string, string>>({});
  const [ok, setOk] = useState<string | null>(null);

  async function agendar(ev: FormEvent) {
    ev.preventDefault();
    setEnviando(true);
    setErro(null);
    setCampos({});
    setOk(null);
    try {
      const r = await apiCs.post<{ agendamento: string | null }>(`${rotaChamado(card.numero)}/agendamento`, {
        data,
        hora,
      });
      setOk(`Ligação agendada para ${formatarData(r.agendamento)}.`);
      aoAtualizar();
    } catch (e) {
      const d = descreverErro(e, "Não foi possível agendar a ligação. Tente de novo.");
      setErro(d.mensagem);
      setCampos(d.campos);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section aria-labelledby={`${id}-t`}>
      <h3 id={`${id}-t`}>Agendar ligação</h3>
      {card.agendamento && <p>Agendada para {formatarData(card.agendamento)}.</p>}
      <form onSubmit={agendar}>
        <label htmlFor={`${id}-data`}>Data</label>
        <input
          id={`${id}-data`}
          type="date"
          value={data}
          disabled={travado}
          aria-invalid={campos.data ? true : undefined}
          aria-describedby={campos.data ? `${id}-erro-data` : undefined}
          onChange={(e) => setData(e.target.value)}
        />
        <ErroCampo id={`${id}-erro-data`} texto={campos.data} />
        <label htmlFor={`${id}-hora`}>Hora (Brasília)</label>
        <input
          id={`${id}-hora`}
          type="time"
          value={hora}
          disabled={travado}
          aria-invalid={campos.hora ? true : undefined}
          aria-describedby={campos.hora ? `${id}-erro-hora` : undefined}
          onChange={(e) => setHora(e.target.value)}
        />
        <ErroCampo id={`${id}-erro-hora`} texto={campos.hora} />
        <button type="submit" disabled={travado || enviando}>
          {enviando ? "Agendando…" : "Agendar ligação"}
        </button>
        <Aviso erro={erro} ok={ok} />
      </form>
    </section>
  );
}

function AdicionarCache({ card, aoConcluir }: { card: CardChamado; aoConcluir: () => void }) {
  const id = useId();
  const [pergunta, setPergunta] = useState("");
  const [resposta, setResposta] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [campos, setCampos] = useState<Record<string, string>>({});
  const [ok, setOk] = useState<string | null>(null);

  async function adicionar(ev: FormEvent) {
    ev.preventDefault();
    setEnviando(true);
    setErro(null);
    setCampos({});
    try {
      const r = await apiCs.post<RespostaCache>("/cache", { numero: card.numero, pergunta, resposta });
      setOk(r.ja_existe ? (r.aviso ?? "Já existe uma resposta para esta pergunta.") : "Adicionado ao Cache_Respostas.");
      aoConcluir();
    } catch (e) {
      const d = descreverErro(e, "Não foi possível salvar no cache. Os textos foram mantidos.");
      setErro(d.mensagem);
      setCampos(d.campos);
    } finally {
      setEnviando(false);
    }
  }

  if (ok) return <p role="status">{ok}</p>;

  return (
    <form onSubmit={adicionar} aria-label="Adicionar ao Cache_Respostas">
      <h4>Adicionar ao Cache_Respostas</h4>
      <label htmlFor={`${id}-p`}>Pergunta</label>
      <input
        id={`${id}-p`}
        type="text"
        value={pergunta}
        maxLength={300}
        aria-invalid={campos.pergunta ? true : undefined}
        aria-describedby={campos.pergunta ? `${id}-ep` : undefined}
        onChange={(e) => setPergunta(e.target.value)}
      />
      <ErroCampo id={`${id}-ep`} texto={campos.pergunta} />
      <label htmlFor={`${id}-r`}>Resposta</label>
      <textarea
        id={`${id}-r`}
        value={resposta}
        rows={3}
        maxLength={1000}
        aria-invalid={campos.resposta ? true : undefined}
        aria-describedby={campos.resposta ? `${id}-er` : undefined}
        onChange={(e) => setResposta(e.target.value)}
      />
      <ErroCampo id={`${id}-er`} texto={campos.resposta} />
      <button type="submit" disabled={enviando || pergunta.trim() === "" || resposta.trim() === ""}>
        {enviando ? "Salvando…" : "Adicionar ao Cache_Respostas"}
      </button>
      <Aviso erro={erro} />
    </form>
  );
}

function Encerramento({ card, aoAtualizar }: PropsAcoesChamado) {
  const id = useId();
  const [desfecho, setDesfecho] = useState("");
  const [tipo, setTipo] = useState("");
  const [solucao, setSolucao] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [campos, setCampos] = useState<Record<string, string>>({});
  const [encerrado, setEncerrado] = useState<RespostaEncerrar | null>(null);
  const [cacheFeito, setCacheFeito] = useState(false);

  async function encerrar(ev: FormEvent) {
    ev.preventDefault();
    setEnviando(true);
    setErro(null);
    setCampos({});
    try {
      const r = await apiCs.post<RespostaEncerrar>(`${rotaChamado(card.numero)}/encerrar`, {
        desfecho,
        solucao_tipo: tipo,
        solucao,
      });
      setEncerrado(r);
      // Com oferta de cache, o recarregamento espera o fim do fluxo para não desmontar o formulário.
      if (!r.oferecer_cache) aoAtualizar();
    } catch (e) {
      const d = descreverErro(e, "Não foi possível encerrar o Chamado. Tente de novo.");
      setErro(d.mensagem);
      setCampos(d.campos);
      if (e instanceof ErroApi && e.status === 409) aoAtualizar();
    } finally {
      setEnviando(false);
    }
  }

  if (encerrado) {
    return (
      <section aria-labelledby={`${id}-t`}>
        <h3 id={`${id}-t`}>Encerramento</h3>
        <p role="status">Chamado encerrado.</p>
        {encerrado.oferecer_cache && <AdicionarCache card={card} aoConcluir={() => setCacheFeito(true)} />}
        {encerrado.oferecer_cache && (
          <button type="button" onClick={aoAtualizar}>
            {cacheFeito ? "Concluir" : "Agora não"}
          </button>
        )}
      </section>
    );
  }

  const campoErro = (c: string) => ({
    "aria-invalid": campos[c] ? (true as const) : undefined,
    "aria-describedby": campos[c] ? `${id}-e-${c}` : undefined,
  });

  return (
    <section aria-labelledby={`${id}-t`}>
      <h3 id={`${id}-t`}>Encerrar Chamado</h3>
      <form onSubmit={encerrar}>
        <label htmlFor={`${id}-d`}>Desfecho</label>
        <select id={`${id}-d`} value={desfecho} onChange={(e) => setDesfecho(e.target.value)} {...campoErro("desfecho")}>
          <option value="">Selecione</option>
          <option value="falso_defeito">Falso defeito</option>
          <option value="defeito_real">Defeito real</option>
        </select>
        <ErroCampo id={`${id}-e-desfecho`} texto={campos.desfecho} />
        <label htmlFor={`${id}-t2`}>Tipo de solução</label>
        <select id={`${id}-t2`} value={tipo} onChange={(e) => setTipo(e.target.value)} {...campoErro("tipo_solucao")}>
          <option value="">Selecione</option>
          <option value="instrução do manual">Instrução do manual</option>
          <option value="outra">Outra</option>
        </select>
        <ErroCampo id={`${id}-e-tipo_solucao`} texto={campos.tipo_solucao} />
        <label htmlFor={`${id}-s`}>Descrição da solução</label>
        <textarea
          id={`${id}-s`}
          value={solucao}
          rows={3}
          maxLength={500}
          onChange={(e) => setSolucao(e.target.value)}
          {...campoErro("descricao_solucao")}
        />
        <ErroCampo id={`${id}-e-descricao_solucao`} texto={campos.descricao_solucao} />
        <button type="submit" disabled={enviando}>
          {enviando ? "Encerrando…" : "Encerrar Chamado"}
        </button>
        <Aviso erro={erro} />
      </form>
    </section>
  );
}

export function AcoesChamado({ card, aoAtualizar }: PropsAcoesChamado) {
  if (card.status === "encerrado") {
    return (
      <section aria-label="Ações do atendimento" data-chamado={card.numero}>
        <p>Este Chamado já foi encerrado. Não há ações disponíveis.</p>
      </section>
    );
  }
  const travado = false;
  return (
    <section aria-label="Ações do atendimento" data-chamado={card.numero}>
      <RespostaConsumidor card={card} aoAtualizar={aoAtualizar} travado={travado} />
      <InstrucaoManual card={card} aoAtualizar={aoAtualizar} travado={travado} />
      <OrdemServicoAcao card={card} aoAtualizar={aoAtualizar} travado={travado} />
      <AgendarLigacao card={card} aoAtualizar={aoAtualizar} travado={travado} />
      <Encerramento card={card} aoAtualizar={aoAtualizar} />
    </section>
  );
}
