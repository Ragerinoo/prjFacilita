import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { aoSessaoExpirar, apiCs } from "./clienteCs";

export type PerfilCs = "atendente" | "gestor";

const PERFIS: readonly PerfilCs[] = ["atendente", "gestor"];

/** Corpo de `GET /api/cs/sessao` e do `POST /api/cs/login` (200). */
interface CorpoSessao {
  usuario: string;
  perfil: PerfilCs;
  deve_trocar_senha: boolean;
  inatividade_maxima_s: number;
}

export type StatusSessao = "carregando" | "anonimo" | "autenticado";

export interface SessaoCs {
  status: StatusSessao;
  usuario: string | null;
  perfil: PerfilCs | null;
  deveTrocarSenha: boolean;
  /** Verdadeiro quando a sessão acabou depois de o usuário já estar dentro (Req 13.6). */
  expirou: boolean;
  /** Entra no Painel. Lança `ErroApi` (401, 429, rede...) para a tela de login tratar. */
  login(usuario: string, senha: string): Promise<void>;
  /** Encerra a sessão. Sempre limpa o estado local, mesmo se o servidor não responder. */
  logout(): Promise<void>;
}

interface Estado {
  status: StatusSessao;
  usuario: string | null;
  perfil: PerfilCs | null;
  deveTrocarSenha: boolean;
  expirou: boolean;
}

const ESTADO_INICIAL: Estado = {
  status: "carregando",
  usuario: null,
  perfil: null,
  deveTrocarSenha: false,
  expirou: false,
};

/** Estado sem nenhum dado do usuário anterior. */
const ANONIMO: Estado = { ...ESTADO_INICIAL, status: "anonimo" };

function lerCorpo(corpo: unknown): CorpoSessao | null {
  if (typeof corpo !== "object" || corpo === null) return null;
  const { usuario, perfil, deve_trocar_senha, inatividade_maxima_s } = corpo as Record<string, unknown>;
  if (typeof usuario !== "string" || !usuario) return null;
  if (!PERFIS.includes(perfil as PerfilCs)) return null;
  return {
    usuario,
    perfil: perfil as PerfilCs,
    deve_trocar_senha: deve_trocar_senha === true,
    inatividade_maxima_s: typeof inatividade_maxima_s === "number" ? inatividade_maxima_s : 0,
  };
}

function autenticado(corpo: CorpoSessao): Estado {
  return {
    status: "autenticado",
    usuario: corpo.usuario,
    perfil: corpo.perfil,
    deveTrocarSenha: corpo.deve_trocar_senha,
    expirou: false,
  };
}

const Contexto = createContext<SessaoCs | null>(null);

/**
 * Estado da sessão do Painel_CS. O cookie é HttpOnly, então o front-end só sabe quem
 * está logado perguntando a `GET /sessao` ao abrir o Painel. Nenhuma credencial é
 * guardada aqui nem em storage: a senha existe apenas no estado do formulário.
 */
export function SessaoCsProvider({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<Estado>(ESTADO_INICIAL);

  useEffect(() => {
    const controle = new AbortController();
    apiCs
      .get("/sessao", { sinal: controle.signal })
      .then((corpo) => {
        const dados = lerCorpo(corpo);
        setEstado(dados ? autenticado(dados) : ANONIMO);
      })
      // 401, falha de rede ou resposta inesperada: sem sessão confirmada, vai ao login.
      .catch(() => {
        if (!controle.signal.aborted) setEstado(ANONIMO);
      });
    return () => controle.abort();
  }, []);

  useEffect(
    () =>
      aoSessaoExpirar(() => {
        // Só é "expirou" para quem já estava dentro; um 401 durante a checagem inicial
        // apenas significa que não há sessão. Todos os dados anteriores saem do estado.
        setEstado((atual) => (atual.status === "autenticado" ? { ...ANONIMO, expirou: true } : atual));
      }),
    [],
  );

  const login = useCallback(async (usuario: string, senha: string) => {
    const corpo = await apiCs.post("/login", { usuario, senha });
    const dados = lerCorpo(corpo);
    if (!dados) throw new Error("Resposta de login inválida.");
    setEstado(autenticado(dados));
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiCs.post("/logout");
    } catch {
      // O cookie pode continuar valendo no servidor até expirar, mas a tela não mostra mais nada.
    } finally {
      setEstado(ANONIMO);
    }
  }, []);

  const valor = useMemo<SessaoCs>(
    () => ({ ...estado, login, logout }),
    [estado, login, logout],
  );

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useSessaoCs(): SessaoCs {
  const valor = useContext(Contexto);
  if (!valor) throw new Error("useSessaoCs deve ser usado dentro de SessaoCsProvider.");
  return valor;
}
