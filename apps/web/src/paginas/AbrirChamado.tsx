import { useRef, useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router";
import {
  CATEGORIAS,
  LIMITES,
  URGENCIAS,
  abrirChamado,
  novoProgresso,
  type EstadoAbrirChamado,
  type DadosAbertura,
  type ProgressoAbertura,
} from "../api/abrirChamado";
import { errosPorCampo } from "../api/chamado";
import { MENSAGEM_TELEFONE_INVALIDO, validarTelefone } from "../api/validacaoContato";
import "./Chamado.css";

export const MENSAGEM_FALHA_ABERTURA = "Não foi possível abrir o chamado agora. O que você digitou foi mantido. Tente de novo.";
export const TEXTO_CONSENTIMENTO_ABERTURA = "Concordo em informar meu nome e telefone para este atendimento.";

type Campo = keyof DadosAbertura | "consentimento";

const VAZIO: DadosAbertura = {
  categoria: "",
  urgencia: "",
  descricao: "",
  inicio: "",
  jaTentou: "",
  nome: "",
  telefone: "",
};

const OBRIGATORIOS: [Exclude<keyof DadosAbertura, "contexto">, string][] = [
  ["categoria", "Escolha o assunto."],
  ["urgencia", "Escolha a urgência."],
  ["descricao", "Descreva o problema."],
  ["inicio", "Conte quando começou."],
  ["jaTentou", "Conte o que você já tentou (pode ser “nada”)."],
  ["nome", "Informe o seu nome."],
];

export function validarFormulario(d: DadosAbertura, consentimento: boolean): Partial<Record<Campo, string>> {
  const erros: Partial<Record<Campo, string>> = {};
  for (const [campo, mensagem] of OBRIGATORIOS) if (!d[campo].trim()) erros[campo] = mensagem;
  if (!erros.nome && d.nome.trim().length < 2) erros.nome = "Informe o seu nome.";
  if (!validarTelefone(d.telefone)) erros.telefone = MENSAGEM_TELEFONE_INVALIDO;
  if (!consentimento) erros.consentimento = "Marque a caixa para poder enviar.";
  return erros;
}

export function Component() {
  const estado = useLocation().state as EstadoAbrirChamado | null;
  const [dados, setDados] = useState<DadosAbertura>(() => ({
    ...VAZIO,
    categoria: estado?.categoria && estado.categoria in CATEGORIAS ? estado.categoria : "",
    contexto: estado?.contexto,
  }));
  const [consentimento, setConsentimento] = useState(false);
  const [erros, setErros] = useState<Partial<Record<Campo, string>>>({});
  const [erroGeral, setErroGeral] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [protocolo, setProtocolo] = useState<string | null>(null);
  const progresso = useRef<ProgressoAbertura>(novoProgresso());
  const formulario = useRef<HTMLFormElement>(null);

  function alterar(campo: keyof DadosAbertura, valor: string) {
    setDados((d) => ({ ...d, [campo]: valor }));
  }

  function focarPrimeiroErro(novos: Partial<Record<Campo, string>>) {
    const primeiro = Object.keys(novos)[0];
    formulario.current?.querySelector<HTMLElement>(`[name="${primeiro}"]`)?.focus();
  }

  async function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (enviando) return;
    const novos = validarFormulario(dados, consentimento);
    setErros(novos);
    setErroGeral(null);
    if (Object.keys(novos).length > 0) {
      focarPrimeiroErro(novos);
      return;
    }
    setEnviando(true);
    try {
      setProtocolo(await abrirChamado(dados, progresso.current));
    } catch (erro) {
      const doServidor = errosPorCampo(erro) as Partial<Record<Campo, string>>;
      if (Object.keys(doServidor).length > 0) setErros(doServidor);
      else setErroGeral(MENSAGEM_FALHA_ABERTURA);
    } finally {
      setEnviando(false);
    }
  }

  if (protocolo) {
    return (
      <section className="chamado" aria-labelledby="titulo-aberto">
        <h1 id="titulo-aberto">Chamado aberto</h1>
        <p role="status">
          Recebemos seu chamado. Em breve nossa equipe retornará o contato. Guarde o seu protocolo:{" "}
          <strong className="chamado__numero">{protocolo}</strong>
        </p>
        <p>Você pode acompanhar o chamado pelo número acima.</p>
        <Link to={`/chamado/${encodeURIComponent(protocolo)}`}>Acompanhar o chamado</Link>
      </section>
    );
  }

  function erroDe(campo: Campo) {
    return erros[campo] ? (
      <p id={`erro-${campo}`} className="chamado__erro">
        {erros[campo]}
      </p>
    ) : null;
  }
  const ligacao = (campo: Campo) => ({
    name: campo,
    id: `abrir-${campo}`,
    "aria-invalid": erros[campo] ? (true as const) : undefined,
    "aria-describedby": erros[campo] ? `erro-${campo}` : undefined,
  });

  return (
    <section className="chamado" aria-labelledby="titulo-abrir">
      <h1 id="titulo-abrir">Abrir um chamado</h1>
      <p>Responda às perguntas abaixo para nossa equipe entender o problema e atender mais rápido.</p>
      <form ref={formulario} onSubmit={(e) => void enviar(e)} noValidate>
        <div className="chamado__campo">
          <label htmlFor="abrir-categoria">Qual é o assunto?</label>
          <select {...ligacao("categoria")} value={dados.categoria} onChange={(e) => alterar("categoria", e.target.value)}>
            <option value="">Escolha uma opção</option>
            {Object.entries(CATEGORIAS).map(([chave, rotulo]) => (
              <option key={chave} value={chave}>
                {rotulo}
              </option>
            ))}
          </select>
          {erroDe("categoria")}
        </div>
        <div className="chamado__campo">
          <label htmlFor="abrir-descricao">Descreva o problema</label>
          <textarea
            {...ligacao("descricao")}
            rows={4}
            maxLength={LIMITES.descricao}
            value={dados.descricao}
            onChange={(e) => alterar("descricao", e.target.value)}
          />
          {erroDe("descricao")}
        </div>
        <div className="chamado__campo">
          <label htmlFor="abrir-inicio">Quando o problema começou?</label>
          <input
            {...ligacao("inicio")}
            type="text"
            maxLength={LIMITES.inicio}
            value={dados.inicio}
            onChange={(e) => alterar("inicio", e.target.value)}
          />
          {erroDe("inicio")}
        </div>
        <div className="chamado__campo">
          <label htmlFor="abrir-jaTentou">O que você já tentou fazer?</label>
          <textarea
            {...ligacao("jaTentou")}
            rows={3}
            maxLength={LIMITES.jaTentou}
            value={dados.jaTentou}
            onChange={(e) => alterar("jaTentou", e.target.value)}
          />
          {erroDe("jaTentou")}
        </div>
        <div className="chamado__campo">
          <label htmlFor="abrir-urgencia">Qual o impacto?</label>
          <select {...ligacao("urgencia")} value={dados.urgencia} onChange={(e) => alterar("urgencia", e.target.value)}>
            <option value="">Escolha uma opção</option>
            {Object.entries(URGENCIAS).map(([chave, rotulo]) => (
              <option key={chave} value={chave}>
                {rotulo}
              </option>
            ))}
          </select>
          {erroDe("urgencia")}
        </div>
        <div className="chamado__campo">
          <label htmlFor="abrir-nome">Seu nome</label>
          <input
            {...ligacao("nome")}
            type="text"
            autoComplete="name"
            maxLength={LIMITES.nome}
            value={dados.nome}
            onChange={(e) => alterar("nome", e.target.value)}
          />
          {erroDe("nome")}
        </div>
        <div className="chamado__campo">
          <label htmlFor="abrir-telefone">Telefone com DDD</label>
          <p className="chamado__ajuda">Usamos o seu telefone só para a nossa equipe ligar para você sobre este chamado.</p>
          <input
            {...ligacao("telefone")}
            type="tel"
            inputMode="tel"
            autoComplete="tel-national"
            value={dados.telefone}
            onChange={(e) => alterar("telefone", e.target.value)}
          />
          {erroDe("telefone")}
        </div>
        <div className="chamado__consentimento">
          <input
            {...ligacao("consentimento")}
            type="checkbox"
            checked={consentimento}
            onChange={(e) => setConsentimento(e.target.checked)}
          />
          <label htmlFor="abrir-consentimento">{TEXTO_CONSENTIMENTO_ABERTURA}</label>
        </div>
        {erroDe("consentimento")}
        {erroGeral ? (
          <p role="alert" className="chamado__erro">
            {erroGeral}
          </p>
        ) : null}
        <button type="submit" className="botao chamado__enviar" disabled={enviando}>
          {enviando ? "Enviando…" : "Abrir chamado"}
        </button>
      </form>
    </section>
  );
}
