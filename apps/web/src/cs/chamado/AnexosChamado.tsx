import { useState } from "react";
import { apiCs } from "../clienteCs";
import type { AnexoChamado } from "./tipos";

/** Lista de fotos; a URL curta só é pedida no clique e abre em nova aba. */
export function AnexosChamado({ numero, anexos }: { numero: string; anexos: AnexoChamado[] }) {
  const [erro, setErro] = useState<string | null>(null);

  async function abrir(indice: number) {
    setErro(null);
    try {
      const r = await apiCs.get<{ url: string }>(`/chamados/${encodeURIComponent(numero)}/anexos/${indice}`);
      window.open(r.url, "_blank", "noopener,noreferrer");
    } catch {
      setErro("Não foi possível abrir o anexo. Tente de novo.");
    }
  }

  return (
    <section aria-labelledby="chamado-anexos">
      <h2 id="chamado-anexos">Anexos</h2>
      {anexos.length === 0 ? (
        <p>Sem anexos.</p>
      ) : (
        <ul className="chamado__lista">
          {anexos.map((a) => (
            <li key={a.indice}>
              Foto {a.indice + 1} ({a.mime === "image/png" ? "PNG" : "JPEG"}, {Math.max(1, Math.round(a.bytes / 1024))} KB){" "}
              <button type="button" onClick={() => abrir(a.indice)}>
                Abrir foto {a.indice + 1}
              </button>
            </li>
          ))}
        </ul>
      )}
      {erro && <p role="alert">{erro}</p>}
    </section>
  );
}
