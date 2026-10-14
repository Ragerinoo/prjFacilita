import { useRef, useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router";
import { ErroApi } from "../api/cliente";
import { useSessaoCs } from "./SessaoCs";

export const MENSAGEM_CREDENCIAIS = "Usuário ou senha inválidos.";
export const MENSAGEM_CAMPOS_VAZIOS = "Informe o usuário e a senha.";
export const MENSAGEM_BLOQUEIO_PADRAO = "Acesso temporariamente bloqueado por excesso de tentativas. Tente de novo mais tarde.";
export const MENSAGEM_FALHA = "Não foi possível entrar agora. Tente de novo.";
export const AVISO_SESSAO_EXPIRADA = "Sua sessão expirou. Entre novamente para continuar.";

function traduzirErro(erro: unknown): string {
  if (erro instanceof ErroApi) {
    // 401: mensagem única, igual para usuário inexistente e senha errada (Req 13.7).
    if (erro.status === 401) return MENSAGEM_CREDENCIAIS;
    // 429: o servidor informa os minutos restantes na própria mensagem (Req 13.8).
    if (erro.status === 429) return erro.message.includes("bloqueado") ? erro.message : MENSAGEM_BLOQUEIO_PADRAO;
  }
  return MENSAGEM_FALHA;
}

const DESTINO_PADRAO = "/cs";

/** Destino após o login: só caminhos internos do Painel (evita redirecionamento aberto). */
function destinoSeguro(estado: unknown): string {
  const de = (estado as { de?: unknown } | null)?.de;
  if (typeof de !== "string") return DESTINO_PADRAO;
  const dentroDoPainel = de === "/cs" || de.startsWith("/cs/") || de.startsWith("/cs?");
  return dentroDoPainel && !de.startsWith("/cs/login") ? de : DESTINO_PADRAO;
}

export function Component() {
  const sessao = useSessaoCs();
  const local = useLocation();
  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const campoUsuario = useRef<HTMLInputElement>(null);

  if (sessao.status === "autenticado") {
    return <Navigate to={destinoSeguro(local.state)} replace />;
  }

  async function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (enviando) return;
    if (!usuario.trim() || !senha) {
      setErro(MENSAGEM_CAMPOS_VAZIOS);
      return;
    }
    setEnviando(true);
    setErro(null);
    try {
      await sessao.login(usuario.trim(), senha);
      // Sucesso: o contexto passa a "autenticado" e este componente redireciona.
    } catch (falha) {
      setErro(traduzirErro(falha));
      setSenha("");
      setEnviando(false);
      campoUsuario.current?.focus();
    }
  }

  return (
    <main id="conteudo" tabIndex={-1} className="login-cs">
      <h1>Entrar no painel de atendimento</h1>
      {sessao.expirou ? (
        <p role="status" className="login-cs__aviso">
          {AVISO_SESSAO_EXPIRADA}
        </p>
      ) : null}
      <form onSubmit={enviar} noValidate aria-busy={enviando}>
        <div className="login-cs__campo">
          <label htmlFor="cs-usuario">Usuário</label>
          <input
            id="cs-usuario"
            ref={campoUsuario}
            name="usuario"
            type="text"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            maxLength={100}
            value={usuario}
            onChange={(e) => setUsuario(e.target.value)}
          />
        </div>
        <div className="login-cs__campo">
          <label htmlFor="cs-senha">Senha</label>
          <input
            id="cs-senha"
            name="senha"
            type="password"
            autoComplete="current-password"
            maxLength={256}
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
          />
        </div>
        {erro ? (
          <p role="alert" className="login-cs__erro">
            {erro}
          </p>
        ) : null}
        <button type="submit" className="botao" disabled={enviando}>
          {enviando ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </main>
  );
}
