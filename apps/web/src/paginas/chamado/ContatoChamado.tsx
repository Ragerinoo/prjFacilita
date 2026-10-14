import { useRef, useState, type FormEvent } from "react";
import { enviarContato, errosPorCampo, type DadoPessoal } from "../../api/chamado";
import {
  MENSAGEM_CEP_INVALIDO,
  MENSAGEM_TELEFONE_INVALIDO,
  validarCep,
  validarTelefone,
} from "../../api/validacaoContato";

/** Finalidade do uso de cada dado (Req 12.5). Texto editável; o jurídico da 3corações deve revisar. */
export const FINALIDADES: Record<DadoPessoal, string> = {
  telefone: "Usamos o seu telefone só para a nossa equipe ligar para você sobre este chamado.",
  cep: "Usamos o seu CEP só para indicar a assistência técnica mais próxima de você.",
};
const ROTULOS: Record<DadoPessoal, string> = { telefone: "Telefone com DDD", cep: "CEP" };
const NOMES: Record<DadoPessoal, string> = { telefone: "o telefone", cep: "o CEP" };
export const TEXTO_CONSENTIMENTO = "Concordo em informar esses dados para este atendimento.";
export const MENSAGEM_FALHA_CONTATO = "Não foi possível enviar agora. O que você digitou foi mantido. Tente de novo.";
export const MENSAGEM_CONTATO_ENVIADO = "Recebemos os seus dados. Obrigado!";

const MENSAGENS_FORMATO: Record<DadoPessoal, string> = { telefone: MENSAGEM_TELEFONE_INVALIDO, cep: MENSAGEM_CEP_INVALIDO };
const VALIDADORES: Record<DadoPessoal, (v: string) => boolean> = { telefone: validarTelefone, cep: validarCep };

export function listaDeDados(dados: readonly DadoPessoal[]): string {
  return dados.map((d) => NOMES[d]).join(" e ");
}

interface Props {
  numero: string;
  /** Só o que falta (já descontado o que foi informado na Jornada). */
  solicitados: DadoPessoal[];
  aoAtualizar: (restantes: DadoPessoal[]) => void;
}

/**
 * Formulário de contato (Req 12.2 a 12.6, 12.9, 18.1, 18.5): pede só os dados que faltam,
 * mostra a finalidade, exige consentimento (caixa desmarcada) e mantém o que foi digitado em caso de erro.
 * Os valores ficam só em memória: telefone e CEP não vão para o `sessionStorage`.
 */
export function ContatoChamado({ numero, solicitados, aoAtualizar }: Props) {
  const [valores, setValores] = useState<Record<DadoPessoal, string>>({ telefone: "", cep: "" });
  const [consentimento, setConsentimento] = useState(false);
  const [erros, setErros] = useState<Partial<Record<DadoPessoal, string>>>({});
  const [erroGeral, setErroGeral] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [enviado, setEnviado] = useState(false);
  const campos = useRef<Partial<Record<DadoPessoal, HTMLInputElement | null>>>({});

  if (solicitados.length === 0) {
    return enviado ? (
      <section aria-labelledby="titulo-contato" className="chamado__secao">
        <h2 id="titulo-contato">Seus dados de contato</h2>
        <p role="status">{MENSAGEM_CONTATO_ENVIADO}</p>
      </section>
    ) : null;
  }

  function focarPrimeiroErro(novos: Partial<Record<DadoPessoal, string>>) {
    const primeiro = solicitados.find((d) => novos[d]);
    if (primeiro) campos.current[primeiro]?.focus();
  }

  async function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (!consentimento || enviando) return; // Req 12.5: sem consentimento, nada é enviado
    const preenchidos = solicitados.filter((d) => valores[d].trim() !== "");
    const novos: Partial<Record<DadoPessoal, string>> = {};
    if (preenchidos.length === 0) novos[solicitados[0]] = MENSAGENS_FORMATO[solicitados[0]];
    for (const dado of preenchidos) {
      if (!VALIDADORES[dado](valores[dado])) novos[dado] = MENSAGENS_FORMATO[dado];
    }
    setErros(novos);
    setErroGeral(null);
    if (Object.keys(novos).length > 0) {
      focarPrimeiroErro(novos);
      return;
    }
    setEnviando(true);
    try {
      const dados = Object.fromEntries(preenchidos.map((d) => [d, valores[d].trim()]));
      const restantes = await enviarContato(numero, dados);
      setEnviado(true);
      aoAtualizar(restantes);
    } catch (erro) {
      const doServidor = errosPorCampo(erro);
      const porCampo: Partial<Record<DadoPessoal, string>> = {};
      for (const dado of solicitados) if (doServidor[dado]) porCampo[dado] = doServidor[dado];
      if (Object.keys(porCampo).length > 0) {
        setErros(porCampo);
        focarPrimeiroErro(porCampo);
      } else {
        setErroGeral(MENSAGEM_FALHA_CONTATO);
      }
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section aria-labelledby="titulo-contato" className="chamado__secao">
      <h2 id="titulo-contato">Falta só {listaDeDados(solicitados)}</h2>
      <p className="chamado__aviso" data-testid="aviso-prazo">
        Sem {listaDeDados(solicitados)}, não conseguimos garantir o contato no prazo indicado. Você pode informar
        depois, nesta mesma página.
      </p>
      <form onSubmit={(e) => void enviar(e)} noValidate>
        {solicitados.map((dado) => {
          const id = `contato-${dado}`;
          return (
            <div className="chamado__campo" key={dado}>
              <label htmlFor={id}>{ROTULOS[dado]}</label>
              <p id={`${id}-finalidade`} className="chamado__ajuda">
                {FINALIDADES[dado]}
              </p>
              <input
                id={id}
                ref={(el) => {
                  campos.current[dado] = el;
                }}
                type={dado === "telefone" ? "tel" : "text"}
                inputMode={dado === "telefone" ? "tel" : "numeric"}
                autoComplete={dado === "telefone" ? "tel-national" : "postal-code"}
                value={valores[dado]}
                onChange={(e) => setValores((v) => ({ ...v, [dado]: e.target.value }))}
                aria-invalid={erros[dado] ? true : undefined}
                aria-describedby={`${id}-finalidade${erros[dado] ? ` ${id}-erro` : ""}`}
              />
              {erros[dado] ? (
                <p id={`${id}-erro`} className="chamado__erro">
                  {erros[dado]}
                </p>
              ) : null}
            </div>
          );
        })}
        <div className="chamado__consentimento">
          <input
            id="contato-consentimento"
            type="checkbox"
            checked={consentimento}
            onChange={(e) => setConsentimento(e.target.checked)}
            aria-describedby="contato-privacidade"
          />
          <label htmlFor="contato-consentimento">{TEXTO_CONSENTIMENTO}</label>
        </div>
        <p id="contato-privacidade">
          Veja como cuidamos dos seus dados no{" "}
          <a href="/privacidade" target="_blank" rel="noopener noreferrer">
            aviso de privacidade (abre em nova aba)
          </a>
          .
        </p>
        {!consentimento ? <p className="chamado__ajuda">Marque a caixa acima para poder enviar.</p> : null}
        {erroGeral ? (
          <p role="alert" className="chamado__erro">
            {erroGeral}
          </p>
        ) : null}
        <button type="submit" className="botao chamado__enviar" disabled={!consentimento || enviando}>
          {enviando ? "Enviando…" : "Enviar"}
        </button>
      </form>
    </section>
  );
}
