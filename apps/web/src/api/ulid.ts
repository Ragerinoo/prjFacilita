const ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"; // Crockford base32

/**
 * Gera um ULID (48 bits de tempo + 80 bits aleatórios, 26 caracteres).
 * Usado como `evento_id`, que dá idempotência ao reenvio no servidor.
 */
export function novoUlid(agora: number = Date.now()): string {
  let tempo = "";
  let restante = agora;
  for (let i = 0; i < 10; i++) {
    tempo = ALFABETO[restante % 32] + tempo;
    restante = Math.floor(restante / 32);
  }
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  let aleatorio = "";
  for (let i = 0; i < 16; i++) {
    aleatorio += ALFABETO[bytes[i] % 32];
  }
  return tempo + aleatorio;
}
