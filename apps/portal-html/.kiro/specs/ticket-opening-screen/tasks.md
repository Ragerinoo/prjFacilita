# Implementation Plan: Tela de abertura de chamado (ticket-opening-screen)

## Overview

O plano segue a ordem do design: primeiro configuração e textos em `js/data.js`, depois o núcleo sem DOM em `js/chamado.js`, depois os testes de propriedade desse núcleo em Node (fast-check só em `tests/`, fora do site), depois `index.html`, `css/styles.css` e `js/app.js`, e por fim os testes de interface em Edge headless, a atualização do `CONTEXTO-PROJETO.md` e a verificação final de integração.

Regras que valem para todas as tarefas:

- O site continua HTML, CSS e JS puros, sem build e sem pacotes na raiz. Nenhuma biblioteca, fonte ou script de terceiros novo em produção.
- Nenhum texto novo é escrito em `index.html` ou `js/app.js`; tudo vem de `TRES_DATA.CHAMADO` em `js/data.js` (a única exceção prevista é a frase de reserva de "conteúdo indisponível" em `js/chamado.js`, ver "Decisões e pontos em aberto" do design).
- O código novo não usa `console.*` e não usa `innerHTML` com dados do consumidor, do back end ou de `data.js`. Valores digitados entram só por `textContent`/`createTextNode` (helper `el()`).
- Não alterar `material/`, `img/*.png` originais nem o `.glb` original. Não alterar regras CSS existentes.
- `PRAZO_RETORNO_DIAS_UTEIS = 2` é ilustrativo e `PENDENTE` de validação do Customer Success. `API_CHAMADOS_URL` fica vazia (Modo_Prototipo).
- Testes de interface: o Edge headless recarrega a aba depois de uns 5 s. Cada cenário é curto (menos de 4 s) e começa em carga nova (lição do `CONTEXTO-PROJETO.md`).
- Não fazer commits.

## Tasks

- [x] 1. Linha de base de integridade, configuração e textos em `js/data.js`
  - [x] 1.1 Criar o script de integridade dos arquivos protegidos e gravar a linha de base
    - Criar `tests/verificar-protegidos.js` (somente módulos nativos do Node) com os modos `--gerar` e `--conferir`
    - Calcular SHA-256 de todos os arquivos de `material/` (recursivo), `img/LOV.png`, `img/Luna.png`, `img/Modo.png`, `img/Passione.png`, `img/TOUCH.png` e `modelos3d/c0adab67d5fc6db5e82670d1271e4559.glb`
    - `--gerar` grava `tests/baseline-protegidos.json` (caminho relativo e hash); `--conferir` falha se algum hash mudou, se algum arquivo sumiu ou se surgiu arquivo novo em `material/`
    - Executar `--gerar` agora, antes de qualquer outra alteração
    - _Requirements: 12.5_

  - [x] 1.2 Acrescentar o objeto `CHAMADO` em `js/data.js` e exportá-lo em `window.TRES_DATA`
    - `config`: `API_CHAMADOS_URL: ''`, `TIMEOUT_ENVIO_MS: 10000`, `PRAZO_RETORNO_DIAS_UTEIS: 2`, `PRAZO_RETORNO_VALIDADO: false`, `VERSAO_CONTRATO: '1'`, cada valor ilustrativo comentado como `ILUSTRATIVO / PENDENTE`
    - `privacidade`: `controlador: 'PENDENTE'`, `contato: 'PENDENTE'`, `politicaUrl: ''`
    - `textos`: todos os textos novos do design (título, introdução, resumo e legendas, rótulos dos campos e "obrigatório", ajuda do telefone, contador, rótulo do aceite, "Ler os termos", "Texto dos termos em elaboração", erros por campo e código com `{min}`/`{max}`, anúncio de erros singular e plural, aviso de privacidade com `{controlador}` e `{contato}`, prazo, canais do formulário e da confirmação, falha e alternativa, aviso de protótipo, título e mensagens da confirmação, título da avaliação, botões "Abrir meu chamado", "Enviando", "Rever os passos", "Escolher outro problema", "Tenho outro problema", "Voltar ao início", "Ver os passos", "Ocultar os passos", "Não informado", "Nenhum passo registrado nesta visita")
    - Manter intactas todas as chaves atuais de `TRES_DATA` e marcar `PENDENTE` o que depende de validação jurídica ou do back end
    - _Requirements: 6.15, 7.4, 8.7, 12.3, 12.4_

- [x] 2. Implementar o núcleo sem DOM em `js/chamado.js`
  - [x] 2.1 Criar o módulo UMD com constantes, normalização e validação
    - Criar `js/chamado.js` como script clássico (IIFE que exporta em `module.exports` no Node e em `window.TRESChamado` no navegador), com `'use strict'`
    - `LIMITES` (nome 3 a 100, email 254, telefone 20, descrição 10 a 500, protocolo 64, 10 tentativas de protocolo, 50 chamados)
    - `normalizarNome`, `normalizarEmail`, `normalizarDescricao`, `normalizarTelefone` (remove `55` só com 12 ou 13 dígitos começando em `55`)
    - `validarNome`, `validarEmail`, `validarTelefone`, `validarDescricao` (códigos `null`, `'vazio'`, `'tamanho'`, `'formato'`), `validarFormulario` (erros na ordem nome, email, telefone, descricao, aceite; sem alterar a entrada), `limitarDescricao`, `formatarContador`
    - Contar caracteres com `String.length`, igual ao `maxlength` do navegador
    - _Requirements: 4.9, 4.10, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.8, 5.13, 5.14, 5.16, 7.3, 10.4, 10.5_

  - [x] 2.2 Implementar a lógica de jornada e sessão
    - `registrarPasso(passos, problemaId, posicao, total)` (zera ao mudar de problema, ignora repetida ou fora de `1..total`, mantém a ordem)
    - `montarResumo({ modeloNome, problema, posicoes })` (usa `null` para "Não informado"; devolve `modelo`, `problemaTitulo`, `passos`, `vistos`, `total`; sem problema: `0 de 0`)
    - `novaSessao(problemaId)` e `garantirSessao(sessao, problemaId)`
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.13, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.14, 8.15_

  - [x] 2.3 Implementar identificadores
    - `gerarProtocolo(dataLocal, sorteio)`, `gerarProtocoloUnico(existentes, dataLocal, sorteio)` (até 10 tentativas, `null` se todas colidirem), `ehProtocoloLocal(s)` (valida a data no calendário)
    - `uuidV4(bytes16)` e `gerarChaveIdempotencia(sorteio)`; no navegador usar `crypto.randomUUID`, depois `getRandomValues` e, por último, `Math.random`
    - _Requirements: 7.12, 8.2, 8.3, 8.16, 10.6, 10.14_

  - [x] 2.4 Implementar textos, prazo, modo, política e verificação de conteúdo
    - `formatarPrazo(dias)` ("N dias úteis", "1 dia útil", `null` fora de inteiro de 1 a 30), `montarTextoCanais(modelo, telefone, email)` (substituição literal de `{telefone}` e `{email}`), `politicaLink(url)` (só `http:` ou `https:`)
    - `resolverModo(url)` (`'api'` só para `https:` ou `http:` em `localhost`/`127.0.0.1`; senão `'prototipo'`)
    - `textosValidos(dadosChamado)` e a frase de reserva de "conteúdo indisponível" (única exceção ao requisito 12.3)
    - _Requirements: 6.5, 6.16, 6.17, 7.4, 8.7, 8.8, 8.9, 12.3, 12.6_

  - [x] 2.5 Implementar Chamado, Payload, serialização e Repositorio_de_Chamados
    - `montarChamado(entrada)` (14 campos do contrato; `aceiteTermos: true`; `abertoEm` e `aceiteEm` em ISO 8601 com deslocamento de fuso, não `Z`; descrição com `trim`)
    - `montarPayload(chamado)` (exatamente os 14 campos, sem `protocolo` e sem `modoEnvio`), `serializar`, `desserializar`
    - `lerLista(texto)` (qualquer entrada ilegível vira `[]`, itens que não são objetos são descartados), `adicionarComLimite(lista, chamado, max)`, `criarRepositorio(storage, chave)` com `ler()` e `gravar(lista)` (esta lança em erro de armazenamento)
    - _Requirements: 6.12, 7.2, 7.3, 7.6, 7.16, 10.1, 10.2, 10.3, 10.7, 10.10, 10.11, 10.12, 10.13_

  - [x] 2.6 Implementar a camada de envio (Ponto_de_Integracao)
    - `interpretarRespostaApi(status, corpo)` (2xx com `protocolo` texto de 1 a 64 caracteres após `trim`; senão `'http'` ou `'resposta-invalida'`)
    - `criarPontoDeIntegracao(deps)` devolvendo `enviar(chamado)`, que sempre resolve (nunca rejeita) com `{ ok: true, protocolo, modo }` ou `{ ok: false, categoria }` (`'rede'`, `'timeout'`, `'http'`, `'resposta-invalida'`, `'armazenamento'`, `'protocolo'`)
    - Modo_API: um único `fetch` `POST` com `Content-Type: application/json`, corpo do payload, `AbortController` e `TIMEOUT_ENVIO_MS`, `credentials: 'omit'`, `cache: 'no-store'`, `referrerPolicy: 'no-referrer'`, sem retentativa automática e com alternativa por `Promise.race` sem `AbortController`; não toca no repositório local, não gera protocolo local e nunca devolve corpo da resposta no resultado
    - Modo_Prototipo: ler o repositório, reaproveitar o protocolo da mesma `chaveIdempotencia`, gerar protocolo único, gravar com limite de 50 e só então sinalizar sucesso; nenhuma requisição de rede
    - Sem `console.*` e sem dados pessoais nos resultados
    - _Requirements: 7.1, 7.5, 7.7, 7.8, 7.9, 7.10, 7.11, 7.13, 7.14, 7.15, 7.17, 8.16, 10.8, 12.7, 12.8_

  - [x] 2.7 Implementar o resumo e os eventos de métrica
    - `resumirEventos(eventos)` (mantém `resolvidos`, `encaminhadosAoSuporte`, `deflexaoPercentual`, `porProblema` e soma `chamadosAbertos`; eventos `chamado` e `avaliacao` não entram nos quatro valores originais)
    - `eventoChamado(c, protocolo, modo, passos)` e `eventoAvaliacao(...)` com apenas os campos permitidos, sem nome, e-mail, telefone nem descrição
    - _Requirements: 6.13, 9.2, 9.3, 9.5, 9.6, 9.9_

- [x] 3. Testes do núcleo em Node (somente desenvolvimento, fora do site)
  - [x]* 3.1 Montar a infraestrutura de testes em `tests/`
    - Criar `tests/package.json` (privado, script `"test": "node --test"`, `devDependencies` com `fast-check` em versão fixa e exata, sem `^` nem `~`; a consulta ao npm retornou 4.10.2, conferir de novo antes de fixar) e instalar com `npm install` dentro de `tests/`
    - Criar `tests/geradores.js` (Unicode completo com emojis, acentos, quebras de linha, aspas, `\`, `<`, `>`, `&` e surrogates soltos; nomes, e-mails, telefones, chamados, listas de chamados, eventos de métrica, sorteio determinístico)
    - Criar `tests/falsos.js` (storage falso com modos "lança em `getItem`", "lança em `setItem`" e espião; `fetch` falso configurável por `(status, corpo)`, sem resposta e com rejeição de rede; `AbortController` e `setTimeout` falsos; relógio e sorteio determinísticos)
    - Não criar `package.json` na raiz do projeto
    - _Requirements: 12.4_

  - [x]* 3.2 Escrever os testes de exemplo sobre `js/data.js` (`tests/dados.test.js`)
    - Carregar `js/data.js` em contexto `vm` com `window` falso
    - Conferir: título com "chamado" e "aberto" e até 80 caracteres; introdução até 300 caracteres e com "time responsável" e "analis…"; rótulo dos passos sem "feito", "executado", "realizado" e "concluído"; rótulo exato do aceite; "Ler os termos"; "Texto dos termos em elaboração"; `API_CHAMADOS_URL` vazia; `PRAZO_RETORNO_DIAS_UTEIS` igual a 2; marcações `PENDENTE`; `TIMEOUT_ENVIO_MS` presente; chaves antigas de `TRES_DATA` intactas
    - _Requirements: 1.2, 1.3, 2.8, 6.6, 6.7, 6.8, 6.15, 7.4, 12.3_

  - [x]* 3.3 Escrever o teste de propriedade da normalização idempotente
    - **Property 1: Normalização de texto é idempotente**
    - Arquivo `tests/nucleo/normalizacao-validacao.test.js`, `numRuns` mínimo 100, com o comentário `// Feature: ticket-opening-screen, Property 1: Normalização de texto é idempotente`
    - **Validates: Requirements 10.4**

  - [x]* 3.4 Escrever o teste de propriedade do telefone normalizado
    - **Property 2: Telefone válido normaliza para 10 ou 11 dígitos**
    - **Validates: Requirements 5.3, 7.3, 10.5**

  - [x]* 3.5 Escrever o teste de propriedade da validação do telefone
    - **Property 3: Validação do telefone**
    - **Validates: Requirements 5.3, 5.4**

  - [x]* 3.6 Escrever o teste de propriedade da validação do nome
    - **Property 4: Validação do nome**
    - **Validates: Requirements 5.1**

  - [x]* 3.7 Escrever o teste de propriedade da validação do e-mail
    - **Property 5: Validação do e-mail**
    - **Validates: Requirements 5.2**

  - [x]* 3.8 Escrever o teste de propriedade de descrição, contador e truncamento
    - **Property 6: Descrição, contador e truncamento**
    - **Validates: Requirements 4.9, 4.10, 5.5, 5.13**

  - [x]* 3.9 Escrever o teste de propriedade da validade do formulário
    - **Property 7: Validade do formulário, ordem e contagem dos erros**
    - **Validates: Requirements 5.6, 5.8, 5.9, 5.14, 5.15, 5.16**

  - [x]* 3.10 Escrever o teste de propriedade dos passos percorridos
    - **Property 8: Passos percorridos**
    - Arquivo `tests/nucleo/jornada.test.js`
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

  - [x]* 3.11 Escrever o teste de propriedade do resumo da jornada
    - **Property 9: Resumo da jornada**
    - **Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.13**

  - [x]* 3.12 Escrever o teste de propriedade do formato do protocolo local
    - **Property 10: Formato do protocolo local**
    - Arquivo `tests/nucleo/identificadores.test.js`
    - **Validates: Requirements 8.2, 10.6**

  - [x]* 3.13 Escrever o teste de propriedade do protocolo local único
    - **Property 11: Protocolo local único**
    - **Validates: Requirements 8.3, 8.16**

  - [x]* 3.14 Escrever o teste de propriedade da chave de idempotência
    - **Property 12: Chave de idempotência**
    - **Validates: Requirements 7.12, 10.14**

  - [x]* 3.15 Escrever o teste de propriedade do conteúdo do Chamado e do Payload
    - **Property 13: Conteúdo do Chamado e do Payload**
    - Arquivo `tests/nucleo/chamado-payload.test.js`
    - **Validates: Requirements 6.12, 7.2, 7.3, 10.10, 10.11, 10.12**

  - [x]* 3.16 Escrever o teste de propriedade da ida e volta do Chamado no repositório
    - **Property 14: Ida e volta do Chamado no repositório**
    - Usar mais de 100 execuções e os geradores Unicode completos
    - **Validates: Requirements 10.1, 10.2, 10.3**

  - [x]* 3.17 Escrever o teste de propriedade da ida e volta do Payload
    - **Property 15: Ida e volta do Payload**
    - **Validates: Requirements 10.13**

  - [x]* 3.18 Escrever o teste de propriedade da leitura tolerante do repositório
    - **Property 16: Leitura tolerante do repositório**
    - **Validates: Requirements 7.16, 10.7**

  - [x]* 3.19 Escrever o teste de propriedade do limite de 50 chamados
    - **Property 17: Limite de 50 chamados**
    - **Validates: Requirements 7.6**

  - [x]* 3.20 Escrever o teste de propriedade da seleção do modo de envio
    - **Property 18: Seleção do modo de envio**
    - Arquivo `tests/nucleo/envio.test.js`, com `fetch` falso espião
    - **Validates: Requirements 7.4, 12.8**

  - [x]* 3.21 Escrever o teste de propriedade da requisição em Modo_API
    - **Property 19: Requisição em Modo_API**
    - **Validates: Requirements 7.8, 10.10**

  - [x]* 3.22 Escrever o teste de propriedade da classificação da resposta da API
    - **Property 20: Classificação da resposta da API**
    - **Validates: Requirements 7.9, 7.10, 7.11, 7.17**

  - [x]* 3.23 Escrever o teste de propriedade do envio idempotente em Modo_Prototipo
    - **Property 21: Envio em Modo_Prototipo é idempotente por chave**
    - **Validates: Requirements 7.5, 7.13, 12.7**

  - [x]* 3.24 Escrever o teste de propriedade da falha de registro sem rastro
    - **Property 22: Falha de registro não deixa rastro**
    - **Validates: Requirements 7.14, 7.15, 8.16, 10.8**

  - [x]* 3.25 Escrever o teste de propriedade do prazo de retorno
    - **Property 23: Prazo de retorno**
    - Arquivo `tests/nucleo/textos-metricas.test.js`
    - **Validates: Requirements 8.7, 8.9**

  - [x]* 3.26 Escrever o teste de propriedade do texto dos canais de retorno
    - **Property 24: Texto dos canais de retorno**
    - **Validates: Requirements 8.6, 8.8**

  - [x]* 3.27 Escrever o teste de propriedade do resumo de métricas
    - **Property 25: Resumo de métricas preserva a deflexão**
    - **Validates: Requirements 9.5, 9.6**

  - [x]* 3.28 Escrever o teste de propriedade dos eventos sem dados pessoais
    - **Property 26: Eventos de métrica sem dados pessoais**
    - **Validates: Requirements 6.13, 9.2, 9.3, 9.9**

  - [x]* 3.29 Escrever o teste de propriedade da decisão do link da política
    - **Property 27: Decisão do link da política de privacidade**
    - **Validates: Requirements 6.5, 6.17**

  - [x]* 3.30 Escrever o teste de propriedade do conteúdo indisponível
    - **Property 28: Conteúdo indisponível**
    - **Validates: Requirements 12.6**

  - [x]* 3.31 Escrever o teste de propriedade da nova sessão para outro problema
    - **Property 29: Nova sessão para outro problema**
    - Escrever em `tests/nucleo/jornada.test.js`
    - **Validates: Requirements 4.14, 8.15**

  - [x]* 3.32 Escrever os testes de exemplo e de borda do núcleo (`tests/nucleo/exemplos.test.js`)
    - Ordem e códigos dos erros (`vazio`, `tamanho`, `formato`, `aceite`)
    - DDD 55 com 11 dígitos não perde o `55`; `5555999999999` vira `55999999999`
    - Tempo limite: `fetch` que nunca responde com temporizador falso → `'timeout'`; falha de rede → `'rede'`
    - Geração da chave sem `crypto.randomUUID`
    - Protocolo de 64 caracteres aceito e de 65 rejeitado em Modo_API
    - _Requirements: 5.3, 5.8, 7.9, 7.10, 7.11, 7.12_

- [x] 4. Checkpoint - Núcleo e testes
  - Garanta que os testes passam (`npm test` dentro de `tests/`), pergunte ao usuário se houver dúvidas.

- [x] 5. Estrutura HTML em `index.html`
  - [x] 5.1 Incluir o script do núcleo e a região de anúncios
    - Acrescentar `<script src="js/chamado.js"></script>` entre `js/data.js` e `js/app.js`
    - Acrescentar, dentro de `<main>` e fora de qualquer `.view`, `<div id="anuncio" class="sr-only" role="status" aria-live="polite"></div>`
    - _Requirements: 11.6, 11.11, 12.4_

  - [x] 5.2 Substituir o conteúdo de `#view-suporte` pela Tela_de_Chamado
    - Seguir o esqueleto do design: faixa `.desfecho--chamado` com `h1#titulo-suporte` e introdução; cartão `#resumo-jornada` (`dl` de modelo, problema e "X de Y passos", botão `#resumo-toggle` com `aria-expanded` e `aria-controls`, legenda, `ol#resumo-lista`, `#resumo-vazio`); formulário `#form-chamado` com `novalidate`; campos Nome, E-mail, Telefone, Descrição e aceite; `#btn-ler-termos` e `#termos-msg` (`role="status"`); `#btn-abrir-chamado`; `#chamado-falha-area`; botões `#btn-rever-chamado` e "Escolher outro problema"
    - Atributos: `type="email"` e `type="tel"` com `inputmode="tel"`; `autocomplete` `name`, `email`, `tel` e nenhum na descrição; `maxlength` 100, 254, 20 e 500; `required`; `aria-describedby` do telefone e da descrição; `<p class="campo__erro" hidden>` por controle; `input type="checkbox"` nativo dentro do `label`
    - Todos os textos por `data-texto="chave"`, sem texto escrito no HTML; `linha de prazo e canais` (`#chamado-prazo-resumo`) e `#aviso-privacidade` acima do aceite
    - Remover os ids que deixam de existir (`cartao-contato`, `lista-em-maos`, `estrelas-suporte`, `status-aval-suporte`, `btn-rever-suporte`) sem tocar nas outras views, no cabeçalho, na barra de etapas nem no rodapé
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.8, 2.1, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.11, 4.13, 6.1, 6.6, 6.7, 11.10, 12.1, 12.3_

  - [x] 5.3 Incluir `#view-chamado` com a Tela_de_Confirmacao
    - Depois de `#view-suporte`, seguir o esqueleto do design: faixa `.desfecho--ok` com `h1#titulo-chamado` e mensagem de recebimento; cartão do protocolo (`#chamado-protocolo`); `#chamado-aviso-prototipo` com `hidden`; cartão de retorno (`#chamado-prazo`, `#chamado-canais`, convite para conferir, `#chamado-email`, `#chamado-telefone`); grupo de avaliação (`#estrelas-chamado`, `#status-aval-chamado` com `role="status"`); exatamente dois links, `#/problemas` e `#/`
    - Todos os textos por `data-texto`, sem texto escrito no HTML
    - _Requirements: 8.4, 8.5, 8.6, 8.7, 8.8, 8.10, 8.13, 8.19, 11.9, 12.3_

- [x] 6. Estilos em `css/styles.css`
  - [x] 6.1 Acrescentar os tokens semânticos no `:root`
    - Acrescentar (sem alterar as variáveis de marca existentes) `--superficie`, `--superficie-borda`, `--texto`, `--texto-suave`, `--acao`, `--acao-hover`, `--link`, `--foco`, `--campo-fundo`, `--campo-borda`, `--campo-borda-foco`, `--erro`, `--erro-fundo`, `--sucesso-fundo`, `--info-fundo`, `--aviso-fundo`, `--aviso-borda`, `--raio-cartao`, `--sombra-cartao`, `--alvo-minimo`
    - Os blocos novos usam só esses tokens, sem cor, raio, sombra ou fonte literal
    - _Requirements: 11.8, 12.1_

  - [x] 6.2 Estilizar a Tela_de_Chamado
    - Ao final do arquivo, sem alterar regra existente: `.cartao`, `.resumo*` (recolhido até 480 px com `@media (max-width: 480px)`, lista sempre expandida e `.resumo__toggle { display: none }` acima disso), `.form`, `.campo*` (campos com `min-height: 52px`, `font-size: 1rem`, borda `--campo-borda`, textarea com `min-height: 140px` e `resize: vertical`), `.campo__erro` e `[aria-invalid="true"]`, `.aceite*` (label inteiro com no mínimo 44 px, caixa de 24 px), `.envio*` (aviso de privacidade com no mínimo 14 px), `.desfecho--chamado`, `.msg-falha`
    - Alvos de 44 px, espaçamento de 8 px entre alvos adjacentes, foco visível herdado de `:focus-visible` sem corte por `overflow`, formulário com `max-width: 640px` centralizado, sem rolagem horizontal de 360 px a 1024 px
    - _Requirements: 2.9, 2.11, 2.12, 4.3, 6.1, 11.1, 11.2, 11.3, 11.5, 11.7, 11.8_

  - [x] 6.3 Estilizar a Tela_de_Confirmacao
    - `.protocolo*` (`font-size: clamp(1.5rem, 6vw, 2rem)`, `font-weight: 800`, `overflow-wrap: anywhere`, texto selecionável), `.aviso`, `.aviso--prototipo` (`--aviso-fundo` e `--aviso-borda`), `.retorno`, `.dados-contato`, `.desfecho--ok` reaproveitado sem editar a regra existente
    - Nenhuma animação nem transição nova; manter `prefers-reduced-motion` efetivo para os blocos novos
    - _Requirements: 8.4, 8.10, 11.2, 11.5, 11.7, 11.8_

- [x] 7. Lógica de tela em `js/app.js`
  - [x] 7.1 Estado, rotas base e utilitários
    - Acrescentar `passos` e `sessao` a `state`; acrescentar `chamado: 'chamado'` a `VIEWS` e `chamado: 3` a `ETAPA_DA_VIEW`
    - Criar `aplicarTextos(raiz)` (preenche `[data-texto]` com `textContent` a partir de `D.CHAMADO.textos`), `anunciar(texto)` (limpa e preenche `#anuncio`) e `garantirSessao(problemaId)`
    - Fazer `TRESMetricas.resumo` delegar a `TRESChamado.resumirEventos`, com os mesmos quatro campos de antes mais `chamadosAbertos`
    - Garantir listas vazias de passos e sessão em página nova e quando a jornada recomeça
    - _Requirements: 3.7, 9.5, 9.6, 11.9, 12.3_

  - [x] 7.2 Registrar os passos exibidos em `renderSolucao`
    - Chamar `garantirSessao(p.id)` e `TRESChamado.registrarPasso` a cada passo exibido (inclusive o primeiro), mantendo os registrados ao usar "Anterior" e "Rever os passos"
    - Trocar de problema pela lista ou pelo link "Ver solução de" descarta os passos anteriores; escolher o mesmo problema mantém
    - Trocar o listener de `#btn-rever-suporte` por `#btn-rever-chamado`; `#btn-nao` continua gravando o evento `suporte` e indo a `#/suporte/ID`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 9.1_

  - [x] 7.3 Rotas e guardas em `aoMudarRota`
    - Incluir `chamado` na lista de rotas com ID; ID ausente ou inexistente em `#/suporte` e `#/chamado` → `ir('#/problemas')` sem mostrar conteúdo da tela
    - Guardas: `suporte` com `state.sessao.aberto` → `location.replace('#/chamado/ID')`; `chamado` sem chamado aberto → `location.replace('#/suporte/ID')`
    - Chamar `renderChamado()` para `suporte` e `renderConfirmacao()` para `chamado`; remover `renderSuporte`; manter `renderContato` e a rota `#/contato`
    - Foco no `h1` em até 300 ms em qualquer meio de navegação
    - _Requirements: 1.1, 1.6, 1.7, 8.14, 8.15, 12.1, 12.2_

  - [x] 7.4 Implementar `renderChamado` (resumo, aviso de privacidade e conteúdo indisponível)
    - Preencher o Resumo_da_Jornada com `TRESChamado.montarResumo` (modelo, problema, "X de Y passos", lista de passos ou "Nenhum passo registrado nesta visita"), com ou sem problema válido; valores só por `textContent`
    - Controle `#resumo-toggle` (alterna `resumo--recolhido` e `aria-expanded`, texto "Ver os passos" e "Ocultar os passos"), com estado recolhido ao carregar
    - Repor os valores digitados e o aceite da sessão; contador `formatarContador`
    - Aviso de privacidade com `PENDENTE` no lugar de controlador ou contato ausente e link da política só quando `politicaLink` aceitar (`target="_blank"`, `rel="noopener noreferrer"`)
    - Se `!textosValidos(...)`, exibir a mensagem de conteúdo indisponível e desabilitar o envio, mantendo as demais telas
    - Ações "Rever os passos" (preserva os valores do formulário) e "Escolher outro problema"
    - _Requirements: 1.2, 1.3, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 4.12, 6.1, 6.2, 6.3, 6.4, 6.5, 6.16, 6.17, 10.9, 11.10, 11.12, 11.13, 12.6_

  - [x] 7.5 Implementar `iniciarFormulario` e a validação por campo
    - Ligar uma única vez os eventos `input`, `blur` e `submit`
    - `validarCampo`, `mostrarErro` e `limparErro` para Nome, E-mail, Telefone e Descrição: mensagem visível adjacente, `aria-invalid="true"`, `aria-describedby` com o erro (e a ajuda, no telefone e na descrição); mensagens com `{min}` e `{max}` a partir de `TRESChamado.LIMITES`
    - Mostrar erro ao sair de campo vazio ou inválido; remover erro em até 200 ms quando o novo valor é válido
    - Contador atualizado a cada alteração; descrição truncada em 500 (digitada ou colada), mantendo o texto
    - Manter em memória, sem alterar, os valores digitados após rejeição, falha e mudança de orientação
    - Envio inválido: nenhuma gravação nem requisição, foco no primeiro controle inválido (ordem Nome, E-mail, Telefone, Descrição, Aceite), anúncio em `#anuncio` do número de itens com erro em até 1 s
    - _Requirements: 4.9, 4.10, 4.12, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 5.13, 5.14, 5.15, 11.4, 11.11_

  - [x] 7.6 Implementar `aoEnviar`, `mostrarFalha` e o registro de métricas do chamado
    - Criar o Ponto_de_Integracao com `TRESChamado.criarPontoDeIntegracao` e as dependências reais do navegador (`fetch`, `AbortController`, `setTimeout`, `localStorage`, `Date`, sorteio), lendo `D.CHAMADO.config`
    - Marcar `estado = 'enviando'` antes do primeiro `await`; botão desabilitado com o texto "Enviando", `aria-busy` no formulário e anúncio; ativações adicionais ignoradas
    - Gerar `sessao.chave` uma única vez no primeiro envio válido e reutilizá-la nas retentativas; montar o Chamado com `abertoEm` e `aceiteEm` do instante do envio
    - Sucesso: guardar `sessao.aberto` (problema, protocolo, e-mail e telefone normalizados, modo), gravar um único evento `chamado` com `TRESChamado.eventoChamado`, anunciar a conclusão em até 1 s e fazer `location.replace('#/chamado/ID')` em até 1 s
    - Falha: não gravar evento `chamado`; `mostrarFalha(categoria)` cria bloco `role="alert"` com `tabindex="-1"`, mensagem, telefone e e-mail de `CONTATO`, foco no bloco, anúncio, botão reabilitado e valores mantidos
    - Falha ao gravar métricas não pode alterar a tela nem exibir erro; sem `console.*`
    - _Requirements: 7.1, 7.7, 7.12, 7.13, 7.14, 7.15, 8.1, 8.16, 9.2, 9.4, 9.7, 10.8, 11.6, 11.11_

  - [x] 7.7 Implementar `renderConfirmacao`
    - Ler `state.sessao.aberto` e preencher protocolo, e-mail e telefone como texto literal (telefone exibido como dígitos normalizados)
    - Exibir o Aviso_de_Prototipo só quando o modo é `'prototipo'`; em `'api'` manter o elemento `hidden` e vazio
    - Foco no `h1` em até 500 ms; exatamente duas ações, "Tenho outro problema" (`#/problemas`) e "Voltar ao início" (`#/`), sem apagar o chamado
    - Voltar à Tela_de_Chamado do mesmo problema mostra a mesma confirmação, sem novo chamado; outro problema abre o formulário vazio e com o aceite desmarcado
    - _Requirements: 8.4, 8.5, 8.6, 8.10, 8.11, 8.12, 8.13, 8.14, 8.15, 8.17, 8.18, 10.9, 11.9_

  - [x] 7.8 Estender `montarEstrelas` com o quarto parâmetro `extras`
    - Assinatura `montarEstrelas(cont, status, desfecho, extras)`; `extras` é mesclado no evento `avaliacao`
    - Sem o parâmetro o comportamento fica idêntico ao atual (tela de problema resolvido grava `avaliacao` com `desfecho` igual a `resolvido`, mesma aparência e mesmas opções)
    - _Requirements: 9.8, 12.1_

- [x] 8. Botão "Ler os termos" ilustrativo e aceite obrigatório
  - [x] 8.1 Implementar o botão "Ler os termos"
    - Ao acionar, exibir "Texto dos termos em elaboração" (de `data.js`) em `#termos-msg` (`role="status"`), mantendo o foco no botão e o aceite inalterado
    - Sem navegar, sem abrir aba, janela nem diálogo e sem alterar a URL; acionar várias vezes mantém uma única mensagem
    - O botão fica entre o aceite e "Abrir meu chamado" na ordem de Tab; nenhum texto jurídico é exibido
    - _Requirements: 4.4, 6.7, 6.8, 6.9, 6.10, 6.11_

  - [x] 8.2 Integrar o aceite obrigatório à validação e ao chamado
    - Aceite desmarcado: mensagem adjacente em português, `aria-invalid="true"` e `aria-describedby`; ao marcar, remover mensagem e atributos em até 200 ms; incluir o aceite no foco ao primeiro erro e na contagem anunciada
    - Estado do aceite mantido em memória após rejeição, falha e mudança de orientação; desmarcado em nova jornada
    - Aceite marcado e campos válidos: seguir para o envio sem mensagens de erro e sem contagem de erros
    - Registrar `aceiteTermos: true` e `aceiteEm` no Chamado no instante do envio válido
    - _Requirements: 4.2, 4.12, 4.14, 5.6, 5.8, 5.9, 5.15, 5.16, 5.17, 6.6, 6.12, 11.14_

- [x] 9. Prazo de retorno e canais (WhatsApp e e-mail) nas duas telas
  - [x] 9.1 Linha de resumo na Tela_de_Chamado
    - Preencher `#chamado-prazo-resumo` acima do aviso de privacidade com `formatarPrazo(PRAZO_RETORNO_DIAS_UTEIS)` e a frase de canais do formulário, com os mesmos textos-base da confirmação
    - Prazo ausente ou inválido: omitir a frase de prazo, manter os canais, sem texto de erro técnico
    - _Requirements: 1.8, 8.9_

  - [x] 9.2 Prazo e canais na Tela_de_Confirmacao
    - Preencher `#chamado-prazo` ("N dias úteis" ou "1 dia útil", sem data limite) e `#chamado-canais` com `montarTextoCanais` (WhatsApp no telefone e e-mail do chamado), além do convite para conferir os dados
    - Prazo inválido: omitir a frase de prazo e manter os canais
    - _Requirements: 8.6, 8.7, 8.8, 8.9_

- [x] 10. Avaliação por estrelas na Tela_de_Confirmacao
  - [x] 10.1 Montar as estrelas na confirmação
    - Em `renderConfirmacao`, chamar `montarEstrelas($('#estrelas-chamado'), $('#status-aval-chamado'), 'chamado', { protocolo })`
    - A nota grava o evento `avaliacao` com `nota`, `desfecho: 'chamado'`, problema, modelo, protocolo e instante, sem dados pessoais, e exibe o agradecimento em `role="status"`; a avaliação é opcional e não bloqueia a navegação
    - Botões de 44 px ou mais, nome acessível "N estrelas de 5", `aria-pressed` e operação por teclado, como no componente atual
    - _Requirements: 8.19, 9.3, 9.9, 11.15_

  - [x] 10.2 Garantir que a Tela_de_Chamado não tem avaliação
    - Confirmar que nenhum código monta estrelas em `#view-suporte` e que nenhum evento `avaliacao` com `desfecho` `suporte` ou `chamado` é gravado antes do sucesso do envio
    - Confirmar que o evento `avaliacao` da tela de problema resolvido continua idêntico
    - _Requirements: 9.8, 9.10_

- [x] 11. Checkpoint - Telas integradas
  - Garanta que os testes passam (`npm test` dentro de `tests/`), abra a página por um servidor estático e confira o fluxo à mão uma vez, pergunte ao usuário se houver dúvidas.

- [x] 12. Testes de interface e verificação (Edge headless, cenários curtos)
  - [x]* 12.1 Criar a infraestrutura de testes de interface em `tests/ui/`
    - `servidor-teste.js`: servidor estático sem dependências para a raiz do projeto e API falsa em `/api/chamados` com cenários (sucesso 201 com `{protocolo}`, 500, 2xx sem protocolo, resposta lenta, corpo inválido), registrando as chaves de idempotência recebidas; para o Modo_API entrega `js/data.js` com `API_CHAMADOS_URL` apontando para a API falsa, sem editar o arquivo do projeto
    - `cdp.js`: controle do Edge (`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`) por DevTools Protocol com `fetch` e `WebSocket` nativos do Node, perfil temporário apagado ao final
    - `cenarios.js`: executor que roda cada arquivo de `tests/ui/cenarios/` em carga nova, com limite de 4 s por cenário
    - Capturas e perfis só em pasta temporária do sistema
    - _Requirements: 12.4_

  - [x]* 12.2 Cenário: fluxo feliz em Modo_Prototipo
    - Escolher modelo e problema, percorrer passos, "Não, ainda não"; conferir resumo (modelo, problema, "X de Y passos"), preencher, aceitar e enviar; conferir `#/chamado/ID`, protocolo no formato, aviso de protótipo, prazo e canais, foco no `h1`, `#anuncio`, evento `chamado` e `chamadosAbertos`
    - _Requirements: 1.1, 1.6, 2.2, 2.4, 2.7, 7.5, 8.1, 8.2, 8.7, 8.8, 8.10, 8.12, 9.1, 9.2, 9.6, 11.6_

  - [x]* 12.3 Cenário: validação
    - Enviar vazio; conferir mensagens, `aria-invalid`, `aria-describedby`, foco no primeiro erro e anúncio "5 itens"; corrigir um campo e conferir a remoção do erro; enviar sem aceite; marcar o aceite e conferir a remoção
    - _Requirements: 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 5.16, 5.17_

  - [x]* 12.4 Cenário: termos
    - Acionar "Ler os termos" 3 vezes; conferir uma única mensagem em `role="status"`, foco no botão, hash e janelas inalterados e aceite inalterado
    - _Requirements: 6.8, 6.9, 6.10_

  - [x]* 12.5 Cenário: Modo_API
    - Sucesso com protocolo da API, aviso de protótipo ausente do DOM e repositório local vazio; falha 500, tempo limite e resposta sem protocolo mostram o bloco de falha, botão reabilitado e valores mantidos; retentativa reaproveita a mesma `chaveIdempotencia`; nenhum evento `chamado` em caso de falha
    - _Requirements: 7.8, 7.9, 7.10, 7.11, 7.14, 7.17, 8.11, 9.4_

  - [x]* 12.6 Cenário: duplo toque
    - Dois cliques rápidos em "Abrir meu chamado" resultam em uma única requisição e em um único chamado
    - _Requirements: 7.13_

  - [x]* 12.7 Cenário: navegação
    - Voltar depois de abrir o chamado mostra a confirmação existente; "Tenho outro problema" e "Voltar ao início" mantêm o chamado; outro problema abre o formulário vazio, com novo protocolo e sem alterar o anterior; `#/suporte/999` e `#/chamado/999` vão a `#/problemas`; `#/chamado/ID` sem chamado volta ao formulário
    - _Requirements: 1.7, 8.14, 8.15, 8.17, 8.18_

  - [x]* 12.8 Cenário: estrelas
    - Tocar uma nota na confirmação grava `avaliacao` com `desfecho: 'chamado'` e `protocolo`; a Tela_de_Chamado não tem estrelas; a avaliação de problema resolvido grava o mesmo evento de antes
    - _Requirements: 9.8, 9.9, 9.10, 8.19_

  - [x]* 12.9 Cenário: texto literal
    - Digitar `<b>x</b>` e `<img src=x onerror=alert(1)>` em nome e descrição; a confirmação e o armazenamento mostram o texto e nenhum elemento é criado
    - _Requirements: 10.9_

  - [x]* 12.10 Cenário: responsivo
    - Em 360, 480, 768 e 1024 px: `scrollWidth <= innerWidth`, alvos de 44 px, fonte dos campos de 16 px, lista de passos recolhida até 480 px e expandida acima, espaçamento de 8 px; capturas de tela de cada estado em pasta temporária para revisão visual
    - _Requirements: 2.9, 2.11, 2.12, 11.1, 11.2, 11.3_

  - [x]* 12.11 Cenário: movimento reduzido
    - Emular `prefers-reduced-motion: reduce` e conferir transições e animações de 0 ms nas duas telas
    - _Requirements: 11.7_

  - [x]* 12.12 Cenário: regressão das rotas existentes
    - `#/`, `#/problemas`, `#/solucao/ID`, `#/confirma/ID`, `#/resolvido/ID` e `#/contato` mantêm DOM e comportamento; cabeçalho "Falar com a gente" e rodapé iguais; barra de etapas com 3 itens e etapa 3 atual nas telas novas
    - _Requirements: 11.9, 12.1, 12.2_

  - [x]* 12.13 Cenário: dados pessoais fora de lugar indevido
    - Depois do fluxo, `sessionStorage`, cookies, URL e a chave `tres-autoatendimento-eventos` não contêm nome, e-mail, telefone nem descrição, e o console não registra esses valores; em Modo_Prototipo nenhuma requisição de rede para chamados
    - _Requirements: 6.13, 6.14, 9.3, 12.7, 12.8_

  - [x]* 12.14 Escrever o script de verificações estáticas (`tests/estatico.js`)
    - Buscar `innerHTML` com variáveis de usuário e `console.` nos arquivos novos ou alterados
    - Buscar texto novo escrito direto em `index.html` ou `js/app.js`
    - Calcular a razão de contraste dos pares de tokens usados (texto e fundo, erro, foco, borda do campo) e falhar abaixo de 4,5:1 (texto) ou 3:1 (borda e foco)
    - _Requirements: 6.14, 10.9, 11.5, 11.8, 12.3_

  - [x]* 12.15 Criar o roteiro de verificação manual (`tests/ui/roteiro-manual.md`)
    - Checklist curto dos itens que a automação não cobre: leitor de tela real (NVDA, VoiceOver, TalkBack), celular físico, Firefox, Safari, sensação visual das duas telas e, depois, a troca de visual vinda do Figma
    - Os itens continuam "não verificados" até alguém executá-los; esta tarefa só cria o roteiro
    - _Requirements: 11.4, 11.8_

- [x] 13. Atualizar o `CONTEXTO-PROJETO.md`
  - [x] 13.1 Registrar a funcionalidade no contexto do projeto
    - Atualizar jornada (desfecho "Não" agora abre chamado), rotas (`#/suporte/ID` e `#/chamado/ID`), estrutura de arquivos (`js/chamado.js`, `tests/`), `TRES_DATA.CHAMADO`, métricas (`chamado`, `chamadosAbertos`, `avaliacao` com `desfecho`), Modo_Prototipo e Modo_API
    - Pendências: prazo ilustrativo, texto jurídico dos termos, controlador e contato, esquema do banco, autenticação, CORS, formato da resposta e idempotência no back end, itens não verificados (leitor de tela, celular, outros navegadores)
    - Lições dos testes de interface e como rodar `npm test` em `tests/`
    - _Requirements: 12.3_

- [x] 14. Integração e verificação final
  - [x] 14.1 Conferir arquivos protegidos e escopo dos arquivos
    - Rodar `node tests/verificar-protegidos.js --conferir` e confirmar que nada em `material/`, em `img/*.png` originais e no `.glb` original mudou, e que não foi criado, movido nem excluído arquivo em `material/`
    - Confirmar que não existe `package.json` na raiz, que `js/vendor` não ganhou arquivos e que `API_CHAMADOS_URL` continua vazia
    - _Requirements: 12.4, 12.5, 12.8_

  - [x] 14.2 Conferir que nenhum dado pessoal vai para as métricas nem para o console
    - Revisar `js/app.js` e `js/chamado.js`: nenhum `console.*`, nenhum `innerHTML` com dados do consumidor, eventos `chamado` e `avaliacao` só com os campos permitidos e dados pessoais só no repositório (Modo_Prototipo) ou no corpo da requisição (Modo_API)
    - Rodar a suíte completa do núcleo e, se existirem, os cenários de interface e o script de verificações estáticas; confirmar `TRESMetricas.resumo()` com `resolvidos`, `encaminhadosAoSuporte`, `deflexaoPercentual` e `porProblema` inalterados
    - _Requirements: 6.13, 6.14, 9.3, 9.5, 12.3, 12.7_

  - [x] 14.3 Limpar temporários e fechar a verificação
    - Encerrar servidores de teste e processos do Edge, apagar perfis temporários, capturas e arquivos `tmp-*` que tenham sobrado, e garantir que `tests/node_modules` não fica referenciado pelo site
    - Garantir que todos os testes passam, pergunte ao usuário se houver dúvidas.
    - _Requirements: 12.4_

## Notes

- Tarefas marcadas com `*` são opcionais (testes) e podem ser puladas para um MVP mais rápido; as tarefas de código e de verificação final não são opcionais.
- Cada tarefa cita os requisitos específicos que cumpre; cada teste de propriedade cita o número da propriedade do design e o requisito que valida.
- Os testes de propriedade usam fast-check em versão fixa, só em `tests/`, com no mínimo 100 execuções e o comentário `// Feature: ticket-opening-screen, Property N: <título>`.
- A verificação com leitor de tela real, celular físico, Firefox, Safari e back end real fica fora da automação e continua não verificada até alguém executá-la.
- As tarefas 7.x a 10.x alteram o mesmo arquivo (`js/app.js`) e por isso são sequenciais no grafo de dependências.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2.1"] },
    { "id": 1, "tasks": ["2.2", "3.1", "5.1", "6.1"] },
    { "id": 2, "tasks": ["2.3", "3.2", "3.3", "3.10", "5.2", "6.2"] },
    { "id": 3, "tasks": ["2.4", "3.4", "3.11", "3.12", "5.3", "6.3"] },
    { "id": 4, "tasks": ["2.5", "3.5", "3.13", "3.25", "3.31"] },
    { "id": 5, "tasks": ["2.6", "3.6", "3.14", "3.15", "3.26"] },
    { "id": 6, "tasks": ["2.7", "3.7", "3.16", "3.20", "3.32"] },
    { "id": 7, "tasks": ["7.1", "3.8", "3.17", "3.21", "3.27"] },
    { "id": 8, "tasks": ["7.2", "3.9", "3.18", "3.22", "3.28"] },
    { "id": 9, "tasks": ["7.3", "3.19", "3.23", "3.29"] },
    { "id": 10, "tasks": ["7.4", "3.24", "3.30"] },
    { "id": 11, "tasks": ["7.5"] },
    { "id": 12, "tasks": ["7.6"] },
    { "id": 13, "tasks": ["7.7"] },
    { "id": 14, "tasks": ["7.8"] },
    { "id": 15, "tasks": ["8.1"] },
    { "id": 16, "tasks": ["8.2"] },
    { "id": 17, "tasks": ["9.1"] },
    { "id": 18, "tasks": ["9.2"] },
    { "id": 19, "tasks": ["10.1"] },
    { "id": 20, "tasks": ["10.2"] },
    { "id": 21, "tasks": ["12.1", "12.14"] },
    { "id": 22, "tasks": ["12.2", "12.3", "12.4", "12.5", "12.6", "12.7", "12.8", "12.9", "12.10", "12.11", "12.12", "12.13", "12.15"] },
    { "id": 23, "tasks": ["13.1"] },
    { "id": 24, "tasks": ["14.1", "14.2"] },
    { "id": 25, "tasks": ["14.3"] }
  ]
}
```
