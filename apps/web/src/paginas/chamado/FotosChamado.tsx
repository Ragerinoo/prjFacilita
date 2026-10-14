import { useRef, useState, type ChangeEvent } from "react";
import { anexarFoto } from "../../api/chamado";
import { FOTOS_MAX_POR_CHAMADO, motivoFotoRejeitada } from "../../api/validacaoContato";

type EstadoFoto = "enviando" | "ok" | "erro";
interface ItemFoto {
  id: number;
  nome: string;
  estado: EstadoFoto;
  motivo?: string;
}

interface Props {
  numero: string;
  /** Fotos que o Chamado já tem no servidor. */
  anexosIniciais: number;
}

const TEXTO_ESTADO: Record<EstadoFoto, string> = { enviando: "enviando…", ok: "anexada", erro: "não anexada" };

/**
 * Anexos do Chamado (Req 12.7, 12.10): até 3 fotos JPEG ou PNG de até 5 MB.
 * Cada foto é validada e enviada sozinha. Uma foto recusada não afeta o Chamado nem as já anexadas.
 */
export function FotosChamado({ numero, anexosIniciais }: Props) {
  const [itens, setItens] = useState<ItemFoto[]>([]);
  const [total, setTotal] = useState(anexosIniciais);
  const totalRef = useRef(anexosIniciais);
  const proximoId = useRef(0);
  const ocupado = useRef(false);
  const [enviando, setEnviando] = useState(false);

  function atualizar(id: number, mudanca: Partial<ItemFoto>) {
    setItens((atual) => atual.map((i) => (i.id === id ? { ...i, ...mudanca } : i)));
  }

  async function aoEscolher(evento: ChangeEvent<HTMLInputElement>) {
    const arquivos = Array.from(evento.target.files ?? []);
    evento.target.value = ""; // permite escolher o mesmo arquivo de novo
    if (arquivos.length === 0 || ocupado.current) return;
    ocupado.current = true;
    setEnviando(true);
    // Recusas anteriores saem da lista; as fotos anexadas permanecem.
    setItens((atual) => atual.filter((i) => i.estado !== "erro"));
    try {
      for (const arquivo of arquivos) {
        const id = proximoId.current++;
        const motivo = motivoFotoRejeitada(arquivo.type, arquivo.size, totalRef.current);
        if (motivo) {
          setItens((atual) => [...atual, { id, nome: arquivo.name, estado: "erro", motivo }]);
          continue;
        }
        setItens((atual) => [...atual, { id, nome: arquivo.name, estado: "enviando" }]);
        try {
          const confirmado = await anexarFoto(numero, arquivo);
          totalRef.current = confirmado ?? totalRef.current + 1;
          setTotal(totalRef.current);
          atualizar(id, { estado: "ok" });
        } catch (erro) {
          atualizar(id, { estado: "erro", motivo: erro instanceof Error ? erro.message : undefined });
        }
      }
    } finally {
      ocupado.current = false;
      setEnviando(false);
    }
  }

  return (
    <section aria-labelledby="titulo-fotos" className="chamado__secao">
      <h2 id="titulo-fotos">Fotos do problema (opcional)</h2>
      <p>
        Uma foto ajuda a nossa equipe. Envie até {FOTOS_MAX_POR_CHAMADO} fotos JPEG ou PNG, de até 5 MB cada.
      </p>
      <label htmlFor="chamado-fotos" className="chamado__rotulo">
        Escolher fotos
      </label>
      <input
        id="chamado-fotos"
        type="file"
        disabled={enviando}
        accept="image/jpeg,image/png"
        multiple
        onChange={(e) => void aoEscolher(e)}
        aria-describedby="fotos-contagem"
      />
      <p id="fotos-contagem">
        Fotos anexadas: {total} de {FOTOS_MAX_POR_CHAMADO}
      </p>
      <ul className="chamado__fotos" aria-live="polite">
        {itens.map((item) => (
          <li key={item.id} className={item.estado === "erro" ? "chamado__erro" : undefined}>
            {item.nome}: {TEXTO_ESTADO[item.estado]}
            {item.motivo ? `. ${item.motivo}` : ""}
          </li>
        ))}
      </ul>
    </section>
  );
}
