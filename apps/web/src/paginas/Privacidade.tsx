import { Link } from "react-router";

/**
 * Aviso de privacidade (Req 18.5). Texto-base em linguagem simples, mantido em `SECOES` para
 * ser editado sem mexer na tela. O texto jurídico final é responsabilidade da 3corações
 * (design.md, seção Segurança): revise os trechos marcados com "Confirmar" antes de publicar.
 */
interface Secao {
  id: string;
  titulo: string;
  paragrafos?: string[];
  itens?: string[];
}

export const SECOES: Secao[] = [
  {
    id: "quem",
    titulo: "Quem cuida dos seus dados",
    paragrafos: [
      "A 3corações cuida dos dados que você informa neste canal de autoatendimento das máquinas TRES.",
    ],
  },
  {
    id: "dados",
    titulo: "Quais dados pedimos",
    paragrafos: [
      "Você pode ver as instruções e conversar com o assistente sem informar nenhum dado pessoal. Só pedimos dados quando você precisa falar com uma pessoa da nossa equipe.",
    ],
    itens: [
      "Telefone com DDD, para ligarmos para você.",
      "CEP, para indicar a assistência técnica mais próxima.",
      "Fotos do problema, se você quiser enviar.",
      "O texto das suas mensagens. Antes de qualquer uso, trocamos telefone, CPF, e-mail e CEP escritos nelas por marcadores.",
    ],
  },
  {
    id: "finalidade",
    titulo: "Para que usamos",
    paragrafos: [
      "Usamos os dados só para atender o seu chamado e melhorar as instruções. Não vendemos os seus dados. Os relatórios de acompanhamento mostram apenas números somados, sem nomes, telefones ou CEPs.",
      "Só usamos o seu telefone e o seu CEP depois que você marca a caixa de concordância. A caixa sempre começa desmarcada.",
    ],
  },
  {
    id: "protecao",
    titulo: "Como protegemos",
    paragrafos: [
      "Os dados ficam guardados com criptografia. A conexão com este site é sempre segura (HTTPS). Quando uma pessoa da equipe vê o seu telefone ou CEP, registramos quem viu e quando.",
    ],
  },
  {
    id: "guarda",
    titulo: "Por quanto tempo guardamos",
    paragrafos: [
      "Confirmar com o jurídico da 3corações: guardamos os dados pelo tempo necessário para o atendimento e para cumprir obrigações legais. Depois disso, apagamos ou deixamos os dados sem identificação.",
    ],
  },
  {
    id: "direitos",
    titulo: "Os seus direitos",
    paragrafos: ["Pela Lei Geral de Proteção de Dados (LGPD), você pode pedir:"],
    itens: [
      "saber quais dados temos sobre você;",
      "corrigir dados errados;",
      "apagar os seus dados;",
      "retirar o seu consentimento quando quiser.",
    ],
  },
  {
    id: "contato",
    titulo: "Como falar com a gente sobre os seus dados",
    paragrafos: [
      "Confirmar com o jurídico da 3corações: indicar aqui o canal oficial e o nome da pessoa responsável pela proteção de dados. Enquanto isso, fale com o atendimento ao informar o número do seu chamado.",
    ],
  },
];

export function Component() {
  return (
    <section>
      <h1>Aviso de privacidade</h1>
      <p>Aqui você vê como cuidamos dos seus dados.</p>
      {SECOES.map((secao) => (
        <section key={secao.id} aria-labelledby={`privacidade-${secao.id}`}>
          <h2 id={`privacidade-${secao.id}`}>{secao.titulo}</h2>
          {secao.paragrafos?.map((p) => <p key={p}>{p}</p>)}
          {secao.itens ? (
            <ul>
              {secao.itens.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
        </section>
      ))}
      <p>
        <Link to="/">Voltar ao início</Link>
      </p>
    </section>
  );
}
