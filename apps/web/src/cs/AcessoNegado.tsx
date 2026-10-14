import { useEffect, useRef } from "react";
import { Link } from "react-router";

export function AcessoNegado() {
  const titulo = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    titulo.current?.focus();
  }, []);
  return (
    <section>
      <h1 ref={titulo} tabIndex={-1}>
        Acesso negado
      </h1>
      <p>O seu perfil não tem permissão para ver esta área.</p>
      <p>
        <Link to="/cs/fila">Voltar à fila de chamados</Link>
      </p>
    </section>
  );
}
