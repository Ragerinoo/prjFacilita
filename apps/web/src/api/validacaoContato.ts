/**
 * Validação no navegador de telefone, CEP e fotos (Req 12.6, 12.7, 12.10).
 *
 * Espelha `dominio.validadores` (`validar_telefone`, `validar_cep`, `validar_foto`).
 * O servidor valida de novo: esta cópia só evita uma ida e volta e dá o erro junto ao campo.
 */
export const TELEFONE_DIGITOS = [10, 11] as const;
export const CEP_DIGITOS = 8;
export const FOTOS_MAX_POR_CHAMADO = 3;
export const FOTO_MAX_BYTES = 5 * 1024 * 1024;
export const MIMES_FOTO = ["image/jpeg", "image/png"] as const;

export const MENSAGEM_TELEFONE_INVALIDO =
  "Digite o telefone com DDD, com 10 ou 11 números. Use só números, espaço, parênteses e hífen. Exemplo: (11) 91234-5678.";
export const MENSAGEM_CEP_INVALIDO =
  "Digite o CEP com 8 números. Use só números, espaço, parênteses e hífen. Exemplo: 01310-100.";
export const MENSAGEM_FOTO_FORMATO = "Formato não aceito. Envie uma foto JPEG ou PNG.";
export const MENSAGEM_FOTO_TAMANHO = "A foto tem mais de 5 MB. Envie uma foto menor.";
export const MENSAGEM_FOTO_LIMITE = "Limite de 3 fotos por chamado atingido.";

const CARACTERES_ACEITOS = /^[0-9 ()-]*$/;

function digitosSeFormatoValido(valor: string): string | null {
  return CARACTERES_ACEITOS.test(valor) ? valor.replace(/\D/g, "") : null;
}

export function validarTelefone(valor: string): boolean {
  const digitos = digitosSeFormatoValido(valor.trim());
  return digitos !== null && (TELEFONE_DIGITOS as readonly number[]).includes(digitos.length);
}

export function validarCep(valor: string): boolean {
  const digitos = digitosSeFormatoValido(valor.trim());
  return digitos !== null && digitos.length === CEP_DIGITOS;
}

/** Motivo da rejeição da foto ou `null` quando ela pode ser enviada. Ordem: formato, tamanho, limite. */
export function motivoFotoRejeitada(mime: string, bytes: number, jaAnexadas: number): string | null {
  if (!(MIMES_FOTO as readonly string[]).includes(mime.trim().toLowerCase())) return MENSAGEM_FOTO_FORMATO;
  if (bytes > FOTO_MAX_BYTES) return MENSAGEM_FOTO_TAMANHO;
  if (jaAnexadas >= FOTOS_MAX_POR_CHAMADO) return MENSAGEM_FOTO_LIMITE;
  return null;
}
