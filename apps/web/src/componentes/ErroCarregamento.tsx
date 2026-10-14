import { useEffect, useRef } from "react";

interface Props {
  /** Ação do botão. Padrão: recarregar a página (dados ficam no sessionStorage). */
  aoTentarNovamente?: () => void;
}

/**
 * Tela de erro de carregamento (Req 19.9): avisa em português que a página não
 * carregou e oferece "Tentar novamente". O `jornada_id`, a fila de eventos e os
 * rascunhos estão no `sessionStorage`, então recarregar não perde dados.
 */
export function ErroCarregamento({ aoTentarNovamente }: Props) {
  const titulo = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    titulo.current?.focus();
  }, []);

  return (
    <section className="erro-carregamento" role="alert">
      <h1 ref={titulo} tabIndex={-1}>
        A página não carregou
      </h1>
      <p>Não foi possível mostrar esta página agora. As informações que você já deu foram guardadas.</p>
      <button type="button" className="botao" onClick={aoTentarNovamente ?? (() => window.location.reload())}>
        Tentar novamente
      </button>
    </section>
  );
}
