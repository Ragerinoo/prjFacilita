# Roteiro de verificação manual: abertura de chamado

Este roteiro cobre o que a automação (`npm test` em `tests/`) não consegue verificar: leitor de tela real, celular físico, Firefox e Safari, contraste e sensação visual, Modo_API contra o back end real e os textos que ainda dependem de decisão externa.

**Status geral: todos os itens estão NÃO VERIFICADOS.** Este arquivo só foi criado. Nenhum item foi executado por uma pessoa. Quem executar deve preencher a coluna "Status", a data e o responsável, e anotar o que encontrou.

Telas cobertas:
- Tela_de_Chamado: rota `#/suporte/ID`
- Tela_de_Confirmacao: rota `#/chamado/ID`
- Tela_de_Resolvido (comentário opcional): rota `#/resolvido/ID`, seção 8

## Legenda de status

| Marca | Significado |
| --- | --- |
| `[ ]` NÃO VERIFICADO | Ninguém executou ainda (estado inicial de todos os itens) |
| `[x]` OK | Executado e passou |
| `[!]` FALHOU | Executado e encontrou problema (descrever em "Observações") |
| `[-]` N/A | Não se aplica ao ambiente testado (explicar) |

## Preparação

1. Na pasta do projeto, rodar `python -m http.server 8000`.
2. Abrir `http://localhost:8000` (não usar duplo clique em `file://`, o 3D não carrega).
3. Para testar no celular físico, usar o IP do computador na mesma rede Wi-Fi (por exemplo `http://192.168.0.10:8000`). Anotar o IP usado. O servidor `http.server` não tem autenticação; usar só em rede confiável e encerrá-lo ao fim.
4. Fluxo base para chegar à Tela_de_Chamado: escolher um modelo, escolher um problema, percorrer os passos e responder "Não, ainda não" em "O problema foi solucionado?".
5. Antes de cada rodada, limpar os dados do site (localStorage) para partir do zero.
6. Registrar em cada seção: navegador e versão, sistema operacional, aparelho e data.

Em Modo_Prototipo (padrão), `API_CHAMADOS_URL` fica vazia em `js/data.js`. Não deixar o valor alterado depois da seção 6.

---

## 1. Leitor de tela real

Requisitos: 4.2, 5.7 a 5.10, 5.16, 6.8, 7.13, 8.12, 8.19, 9.9, 11.4, 11.6, 11.11, 11.14, 11.15.

Combinações a testar (marcar as que forem possíveis):

| Leitor | Navegador | Sistema | Data / responsável | Status |
| --- | --- | --- | --- | --- |
| NVDA | Firefox | Windows | | `[ ]` |
| NVDA | Chrome ou Edge | Windows | | `[ ]` |
| VoiceOver | Safari | macOS | | `[ ]` |
| VoiceOver | Safari | iOS | | `[ ]` |
| TalkBack | Chrome | Android | | `[ ]` |

Para cada combinação, conferir os itens abaixo e anotar o texto realmente falado quando for relevante.

### 1.1 Tela_de_Chamado

- `[ ]` Ao chegar na tela, o foco vai para o título (`h1`) e o leitor fala que um chamado será aberto (req. 1.6).
- `[ ]` O resumo da jornada é lido antes do formulário: modelo, problema, "X de Y passos" e o rótulo dos passos como "apresentados" (req. 2.1, 2.8).
- `[ ]` No celular, o controle de expandir e recolher a lista de passos anuncia seu estado (recolhido ou expandido) e funciona por duplo toque (req. 2.11).
- `[ ]` Cada campo (Nome, Email, Telefone, Descricao) é lido com o rótulo, a palavra "obrigatório" e o texto de ajuda quando houver (req. 4.2, 4.13).
- `[ ]` O Telefone é lido como "Telefone (WhatsApp)" com a ajuda sobre DDD e WhatsApp.
- `[ ]` O contador "N de 500 caracteres" não fica falando a cada tecla de forma irritante e continua acessível ao navegar até ele (req. 4.9). Anotar se o comportamento incomoda.
- `[ ]` O Aceite_dos_Termos é anunciado como caixa de seleção, obrigatória, com o nome "Li e concordo com os termos para envio dos meus dados" e com o estado marcado ou desmarcado (req. 11.14).
- `[ ]` Ao acionar "Ler os termos", o leitor fala "Texto dos termos em elaboração" sem tirar o foco do botão (req. 6.8). Acionar duas vezes e confirmar que não repete nem duplica a mensagem de forma confusa.
- `[ ]` O Aviso_de_Privacidade é lido de forma compreensível na ordem do formulário (req. 6.1).

### 1.2 Erros de validação e falha de envio

- `[ ]` Enviar o formulário vazio: o leitor anuncia o número de itens com erro em até cerca de 1 segundo (req. 5.9, 11.11).
- `[ ]` O foco vai para o primeiro controle inválido e o leitor fala o rótulo, "inválido" e a mensagem de erro (req. 5.8, 5.10).
- `[ ]` Com o Aceite_dos_Termos desmarcado, a mensagem de erro dele é lida junto com o controle (req. 5.16).
- `[ ]` Corrigir um campo: a mensagem de erro some e o leitor não continua falando o erro antigo (req. 5.12).
- `[ ]` Simular falha de envio (seção 6, ou desligar o `localStorage` no modo anônimo com bloqueio de dados): a mensagem de erro é anunciada e o foco vai para ela (req. 7.14, 11.11).
- `[ ]` Ao enviar, o texto "Enviando" é anunciado e o botão aparece como desabilitado (req. 7.13).

### 1.3 Tela_de_Confirmacao

- `[ ]` A conclusão é anunciada em até cerca de 1 segundo e o foco vai para o `h1` (req. 8.12, 11.6).
- `[ ]` O protocolo é lido por inteiro e de forma entendível (letras e números). Anotar se a leitura é confusa (req. 8.4).
- `[ ]` Prazo e canais de retorno são lidos (req. 8.7, 8.8).
- `[ ]` Em Modo_Prototipo, o Aviso_de_Prototipo é lido. Em Modo_API, não aparece nem para o leitor (req. 8.10, 8.11).
- `[ ]` As estrelas são lidas como "N estrela(s) de 5", com estado pressionado ou não, e operam com Enter e Espaço (req. 11.15).
- `[ ]` Ao escolher uma nota, o texto de agradecimento é anunciado (req. 9.9).
- `[ ]` A barra de etapas indica "A solução" como etapa atual de forma identificável pelo leitor, nas duas telas (req. 11.9).

Observações:

```
(preencher)
```

---

## 2. Celular físico

Requisitos: 4.5 a 4.7, 11.1 a 11.3, 2.9 a 2.12.

| Aparelho | Sistema | Navegador | Data / responsável | Status |
| --- | --- | --- | --- | --- |
| (ex.: Android de entrada, tela pequena) | | Chrome | | `[ ]` |
| (ex.: iPhone) | iOS | Safari | | `[ ]` |
| (outro) | | | | `[ ]` |

Conferir em cada aparelho, em pé e com uma mão, como o consumidor usaria na frente da máquina:

- `[ ]` Sem rolagem horizontal e sem texto cortado ou sobreposto nas duas telas, em retrato (req. 11.1).
- `[ ]` Girar o aparelho para paisagem e voltar: os valores digitados e o estado do aceite continuam (req. 4.12).
- `[ ]` Campo Email abre o teclado com `@`; campo Telefone abre o teclado numérico de telefone (req. 4.5, 4.6).
- `[ ]` O iPhone não dá zoom automático ao tocar nos campos (fonte de 16 px) (req. 11.3).
- `[ ]` O preenchimento automático oferece nome, e-mail e telefone, e não oferece nada para a Descricao (req. 4.7).
- `[ ]` Botões, links, campos, a caixa do aceite e as estrelas são fáceis de tocar sem acertar o vizinho (req. 11.2).
- `[ ]` O botão "Abrir meu chamado" fica alcançável com o teclado virtual aberto; o campo com foco não fica escondido atrás do teclado.
- `[ ]` A lista de passos começa recolhida e expande ao toque (req. 2.9, 2.11).
- `[ ]` O protocolo aparece grande e dá para selecionar e copiar o texto (req. 8.4).
- `[ ]` Colar um texto com mais de 500 caracteres na Descricao corta em 500 (req. 4.10).
- `[ ]` Em celular com tela de 360 px ou menos de largura, tudo continua utilizável.
- `[ ]` Em sol forte ou brilho médio (como ao lado da máquina), o texto e as mensagens de erro continuam legíveis.
- `[ ]` Com a conexão lenta ou instável, o botão mostra "Enviando" e não permite duplo envio (req. 7.13).

Observações:

```
(preencher)
```

---

## 3. Navegadores: Firefox e Safari (e conferência no Chrome/Edge)

Requisitos: 11.1, 11.5, 11.7, 12.1, 12.4.

| Navegador | Versão | Sistema | Data / responsável | Status |
| --- | --- | --- | --- | --- |
| Firefox | | Windows ou macOS | | `[ ]` |
| Safari | | macOS | | `[ ]` |
| Safari | | iOS | | `[ ]` |
| Chrome ou Edge (referência) | | | | `[ ]` |

Em cada um, percorrer o fluxo completo (modelo, problema, passos, "Não, ainda não", formulário, confirmação) e conferir:

- `[ ]` As duas telas aparecem com o mesmo layout da referência (campos, espaçamentos, lista de passos).
- `[ ]` Os campos de Email e Telefone aceitam a digitação e a validação mostra as mensagens do projeto (e não as mensagens nativas do navegador).
- `[ ]` Validação ao sair do campo (perda de foco), correção e remoção do erro funcionam.
- `[ ]` O contador da Descricao atualiza e o limite de 500 caracteres funciona, inclusive ao colar.
- `[ ]` O indicador de foco aparece ao navegar com Tab e não é cortado (req. 11.5). No Safari, conferir também com a opção "Pressionar Tab realça cada item" ativada nas preferências.
- `[ ]` A caixa do Aceite_dos_Termos marca e desmarca com a tecla Espaço.
- `[ ]` Botão voltar e avançar do navegador: voltar depois de abrir o chamado mostra a confirmação existente (req. 8.14).
- `[ ]` Com `prefers-reduced-motion: reduce` ativado no sistema, não há animação nem rolagem suave nas duas telas (req. 11.7).
- `[ ]` Sem erros novos no console do navegador durante o fluxo, e sem dados pessoais impressos no console (req. 6.14).
- `[ ]` As rotas existentes (`#/`, `#/problemas`, `#/solucao/ID`, `#/confirma/ID`, `#/resolvido/ID`, `#/contato`) continuam como antes, com o cabeçalho "Falar com a gente" e o rodapé iguais (req. 12.1, 12.2).
- `[ ]` O modo privado do navegador (em que o `localStorage` pode estar restrito): em Modo_Prototipo, a falha de gravação mostra a mensagem de erro e mantém os dados do formulário (req. 7.15).

Observações:

```
(preencher)
```

---

## 4. Contraste e sensação visual

Requisitos: 11.5, 11.8. A razão de contraste dos pares de tokens é calculada por `tests/estatico.js`, mas só uma pessoa avalia o resultado visual real.

| Item | Data / responsável | Status |
| --- | --- | --- |
| Tela_de_Chamado em tela de computador | | `[ ]` |
| Tela_de_Chamado em celular | | `[ ]` |
| Tela_de_Confirmacao em tela de computador | | `[ ]` |
| Tela_de_Confirmacao em celular | | `[ ]` |

### 4.1 Contraste

- `[ ]` Medir com uma ferramenta (por exemplo, o seletor de cores das ferramentas do navegador ou o Colour Contrast Analyser) o texto sobre o fundo: rótulos, texto de ajuda, texto dentro dos campos, mensagens de erro e a Mensagem_de_Termos_em_Elaboracao. Mínimo 4,5:1 (req. 11.8).
- `[ ]` Conferir os mesmos itens nos estados normal, foco e erro.
- `[ ]` Conferir o contraste mínimo de 3:1 da borda dos campos, do indicador de foco e da borda da caixa do aceite (req. 11.5).
- `[ ]` Conferir que o erro não é indicado só pela cor: há texto de mensagem e `aria-invalid`.
- `[ ]` Conferir o texto do Aviso_de_Prototipo e do Aviso_de_Privacidade (mínimo de 14 px, req. 6.1).
- `[ ]` Zoom do navegador a 200% e fonte maior do sistema: nada some, sobrepõe ou fica cortado.
- `[ ]` Modo de alto contraste do sistema (Windows) ou tema escuro forçado: os campos e o foco continuam visíveis.

### 4.2 Sensação visual

Pontos para quem revisa dar uma nota ou comentar (não há critério de aprovação automático):

- `[ ]` A tela transmite que o chamado realmente será aberto, sem parecer um beco sem saída.
- `[ ]` O resumo da jornada ajuda e não pesa; a lista de passos recolhida no celular é clara.
- `[ ]` O formulário parece curto e rápido de preencher.
- `[ ]` O protocolo se destaca na confirmação (maior que o resto do texto, req. 8.4).
- `[ ]` Prazo, canais de retorno e estrelas estão em uma ordem natural de leitura.
- `[ ]` O visual combina com o restante do Autoatendimento TRES (cores, tipografia, botões).
- `[ ]` O estilo não parece "quebrado" nas telas intermediárias (por exemplo, 600 a 900 px de largura).

Observações:

```
(preencher)
```

---

## 5. Troca de visual vinda do Figma (quando existir)

Esta seção só vale depois que o time de design entregar o visual novo. Se ainda não houver, deixar tudo `[-]` N/A.

- `[ ]` Os textos continuam vindo de `js/data.js` (nada escrito direto em `index.html` ou `js/app.js`) (req. 12.3).
- `[ ]` Rodar `npm test` em `tests/` e `node tests/estatico.js` e confirmar que continuam passando (contraste, `innerHTML`, `console.`).
- `[ ]` Repetir as seções 2, 3 e 4 neste roteiro para o visual novo.
- `[ ]` Alvos de toque de 44 px, espaçamento de 8 px, fonte de 16 px nos campos e indicador de foco de 2 px continuam valendo (req. 11.2, 11.3, 11.5).
- `[ ]` A barra de etapas ainda mostra "A solução" como etapa atual nas duas telas (req. 11.9).
- `[ ]` Nenhum arquivo de `material/`, nenhuma `img/*.png` original e nenhum `.glb` original foi alterado: `node tests/verificar-protegidos.js --conferir` (req. 12.5).

Observações:

```
(preencher)
```

---

## 6. Modo_API contra o back end real

Requisitos: 7.4, 7.8 a 7.11, 7.14, 7.17, 8.11, 9.2, 9.4, 10.10 a 10.12, 12.8. Itens do P9 ainda em aberto.

**Pré-requisitos (dependem do time de back end; sem eles, marcar `[-]` N/A):**
- URL do endpoint de teste (https, ou http em `localhost` ou `127.0.0.1`).
- CORS liberado para a origem usada no teste.
- Ambiente de teste, nunca produção, e sem dados pessoais reais.

**Como ativar:** em `js/data.js`, preencher `config.API_CHAMADOS_URL` com a URL de teste. Ao terminar, **voltar o valor para vazio (`''`)**. O padrão entregue deve continuar vazio (req. 7.4).

Abrir a aba Rede (Network) das ferramentas do navegador durante os testes.

### 6.1 Envio com sucesso

| Item | Status |
| --- | --- |
| `[ ]` Uma requisição `POST` vai para a URL configurada, com `Content-Type: application/json` | `[ ]` |
| `[ ]` O corpo tem exatamente os campos do contrato: `versaoContrato`, `chaveIdempotencia`, `abertoEm`, `nome`, `email`, `telefone`, `descricao`, `aceiteTermos`, `aceiteEm`, `modelo`, `problemaId`, `problemaTitulo`, `passosPercorridos`, `totalPassos` | `[ ]` |
| `[ ]` O corpo não tem `protocolo` nem dados de métricas | `[ ]` |
| `[ ]` `telefone` só com dígitos; `email` em minúsculas; `nome` sem espaços sobrando | `[ ]` |
| `[ ]` `chaveIdempotencia` é um UUID v4 (36 caracteres) | `[ ]` |
| `[ ]` Nenhum token, segredo ou chave de API aparece nos cabeçalhos ou no código | `[ ]` |
| `[ ]` A confirmação mostra o protocolo devolvido pelo back end, não um protocolo `TRES-AAAAMMDD-XXXXXX` gerado local | `[ ]` |
| `[ ]` O Aviso_de_Prototipo não aparece | `[ ]` |
| `[ ]` O `localStorage` não ganha a chave `tres-autoatendimento-chamados` | `[ ]` |
| `[ ]` O evento `chamado` aparece na chave `tres-autoatendimento-eventos` com `modo: 'api'` e sem dados pessoais | `[ ]` |

### 6.2 Falhas

Para cada caso, conferir: bloco de falha com a mensagem de erro, telefone e e-mail de `CONTATO` como alternativa, valores digitados mantidos, aceite mantido, botão reabilitado, nenhum protocolo de sucesso, nenhum evento `chamado` (req. 7.14, 9.4).

| Caso | Como provocar | Status |
| --- | --- | --- |
| Rede indisponível | Desligar a rede ou marcar "Offline" nas ferramentas | `[ ]` |
| Tempo limite | Endpoint que demora mais que `TIMEOUT_ENVIO_MS` (10 s); ou limitar a rede (throttling) | `[ ]` |
| Erro HTTP 4xx | Endpoint de teste que responde 400 | `[ ]` |
| Erro HTTP 5xx | Endpoint de teste que responde 500 | `[ ]` |
| Resposta 200 sem `protocolo` | Endpoint de teste que responde `{}` | `[ ]` |
| Bloqueio por CORS | Origem não liberada no back end | `[ ]` |

- `[ ]` Em nenhuma falha o front end repete a requisição sozinho (req. 7.10).
- `[ ]` Retentativa manual envia a mesma `chaveIdempotencia` da tentativa anterior (comparar na aba Rede) (req. 7.12).
- `[ ]` Depois de uma falha seguida de sucesso, existe um único chamado no back end.
- `[ ]` Duplo clique em "Abrir meu chamado" gera uma só requisição (req. 7.13).

### 6.3 Pontos em aberto com o back end (P9)

Registrar a resposta do time de back end. Enquanto não houver resposta, ficam como pendência e o Modo_API não deve ir para produção.

| Ponto | Resposta / data / responsável | Status |
| --- | --- | --- |
| Esquema do banco de dados | | `[ ]` PENDENTE |
| Autenticação e autorização do endpoint | | `[ ]` PENDENTE |
| Política de CORS e URL por ambiente | | `[ ]` PENDENTE |
| Formato da resposta de sucesso (campo `protocolo`, até 64 caracteres) e códigos HTTP de erro | | `[ ]` PENDENTE |
| Chave de idempotência repetida: devolve o mesmo protocolo? | | `[ ]` PENDENTE |
| Chave de idempotência também em cabeçalho HTTP? | | `[ ]` PENDENTE |
| Formato do telefone (só dígitos sem DDI, ou E.164) | | `[ ]` PENDENTE |
| Restringir WhatsApp a celular (11 dígitos)? O cliente aceita 10 ou 11 | | `[ ]` PENDENTE |
| Limites de tamanho, limitação de taxa e retenção dos dados | | `[ ]` PENDENTE |
| Valor definitivo de `TIMEOUT_ENVIO_MS` | | `[ ]` PENDENTE |
| Prazo de retorno real validado (ver seção 7) | | `[ ]` PENDENTE |

Observações:

```
(preencher)
```

---

## 7. Pendências de texto jurídico, LGPD e prazo

Estes itens não são testes de código: dependem de decisão ou validação de outras áreas. Continuam PENDENTES até receberem uma resposta registrada aqui. Os valores atuais em `js/data.js` são provisórios.

### 7.1 Jurídico e LGPD (req. 6.4, 6.5, 6.15 a 6.17; P5)

| Item | Situação atual no projeto | Responsável / data / resposta | Status |
| --- | --- | --- | --- |
| Texto dos termos de uso | Não existe. "Ler os termos" é só ilustrativo e mostra "Texto dos termos em elaboração" | | `[ ]` PENDENTE |
| Texto do Aviso_de_Privacidade e base legal | Texto provisório em `js/data.js` | | `[ ]` PENDENTE |
| Nome do controlador dos dados | `PENDENTE` em `privacidade.controlador` | | `[ ]` PENDENTE |
| Contato do titular para exercer direitos | `PENDENTE` em `privacidade.contato` | | `[ ]` PENDENTE |
| URL da política de privacidade | Vazia em `privacidade.politicaUrl` (o aviso sai sem link) | | `[ ]` PENDENTE |
| Adequação geral à LGPD (finalidade, retenção, compartilhamento) | Sem validação jurídica | | `[ ]` PENDENTE |

Verificações a fazer quando os valores chegarem:

- `[ ]` Aviso_de_Privacidade mostra controlador e contato reais, sem o marcador `PENDENTE`.
- `[ ]` Se houver URL da política, o link abre em nova aba com `rel="noopener noreferrer"` (req. 6.5).
- `[ ]` O botão "Ler os termos" passa a abrir o texto real (isso muda o escopo atual e exige nova tarefa na spec).
- `[ ]` O aceite continua sendo registrado como `true` com data e hora (req. 6.12).

### 7.2 Prazo e canais de retorno (req. 8.7 a 8.10; P4)

| Item | Situação atual no projeto | Responsável / data / resposta | Status |
| --- | --- | --- | --- |
| Prazo de retorno: 2 dias úteis | Ilustrativo, `PRAZO_RETORNO_DIAS_UTEIS: 2`, `PRAZO_RETORNO_VALIDADO: false` | Customer Success | `[ ]` PENDENTE |
| O time consegue cumprir esse prazo | Sem validação | Customer Success | `[ ]` PENDENTE |
| O time consegue contatar por WhatsApp (número informado) e por e-mail | Sem validação | Customer Success | `[ ]` PENDENTE |

- `[ ]` Antes de ativar o Modo_API em produção, validar o prazo e então atualizar `PRAZO_RETORNO_VALIDADO` (o prazo deixa de ser ilustrativo).
- `[ ]` Em Modo_Prototipo, o Aviso_de_Prototipo continua dizendo que o prazo é ilustrativo (req. 8.10).

Observações:

```
(preencher)
```

---

## 8. Comentário opcional na Tela_de_Resolvido

Spec: `.kiro/specs/resolved-feedback-comment`. Rota `#/resolvido/ID`, com o bloco de comentário logo abaixo das estrelas ("Como foi a ajuda?").

**Status desta seção: todos os itens estão NÃO VERIFICADOS.** Esta seção só foi escrita. Nenhuma pessoa executou nenhum item, e a automação (`npm test` e `node tests/ui/rodar.js`) não substitui nada do que está aqui. Quem executar deve preencher status, data e responsável, e anotar o que encontrou. Não marcar nada como OK sem ter feito o teste de fato.

Requisitos: 1.3, 1.6, 1.7, 4.2 a 4.4, 5.3 a 5.5, 7.2, 7.4 a 7.8, 8.1, 8.3, 10.4 a 10.10, 11.7, 12.1 a 12.8, 13.4, 13.6. Itens ligados ao design: "Possível leitura dupla" (Acessibilidade) e "Decisões e pontos em aberto".

**Preparação específica:**

1. Fluxo para chegar à tela: escolher um modelo, escolher um problema, percorrer os passos e responder "Sim" em "O problema foi solucionado?".
2. Limpar os dados do site (localStorage) antes de cada rodada. O estado "já enviado" fica só em memória e some ao recarregar a página.
3. Em Modo_Prototipo (padrão), `API_FEEDBACK_URL` fica vazia em `js/data.js`. Os comentários vão para a chave `tres-autoatendimento-feedbacks` do `localStorage` (no máximo 50 registros). Conferir ali o que foi gravado.
4. Registrar em cada subseção: leitor de tela e versão, navegador e versão, sistema operacional, aparelho e data.
5. Em todos os testes, usar só texto inventado. Não digitar dados pessoais reais no campo.

### 8.1 Leitor de tela real

Combinações a testar (marcar as que forem possíveis):

| Leitor | Navegador | Sistema | Data / responsável | Status |
| --- | --- | --- | --- | --- |
| NVDA | Firefox | Windows | | `[ ]` NÃO VERIFICADO |
| NVDA | Chrome ou Edge | Windows | | `[ ]` NÃO VERIFICADO |
| VoiceOver | Safari | macOS | | `[ ]` NÃO VERIFICADO |
| VoiceOver | Safari | iOS | | `[ ]` NÃO VERIFICADO |
| TalkBack | Chrome | Android | | `[ ]` NÃO VERIFICADO |

Para cada combinação, anotar o texto realmente falado quando for relevante.

**Ao chegar na tela e no campo:**

- `[ ]` NÃO VERIFICADO: Ao entrar em `#/resolvido/ID`, o foco vai para o título (`h1`) e não para o campo de comentário (req. 1.7).
- `[ ]` NÃO VERIFICADO: O bloco é identificado como grupo com o nome "Como foi a ajuda?", e as estrelas continuam lidas como "N estrela(s) de 5", com estado pressionado ou não (req. 12.9, 12.10).
- `[ ]` NÃO VERIFICADO: O campo é lido com o rótulo "Deixe um comentário sobre a ajuda (opcional)". A palavra "opcional" é falada junto do rótulo, e o leitor não diz "obrigatório" para este campo (req. 1.3).
- `[ ]` NÃO VERIFICADO: O campo é anunciado como campo de texto de várias linhas.
- `[ ]` NÃO VERIFICADO: O aviso de não identificação ("Não escreva nome, e-mail, telefone nem outros dados pessoais aqui.") é lido como descrição do campo, junto do contador, ao focar o campo (req. 1.6).
- `[ ]` NÃO VERIFICADO: A ordem de leitura é: estrelas, campo, aviso, contador, botão "Enviar comentário", "Cuidados com a sua máquina", links finais (req. 1.1, 12.4).

**Contador:**

- `[ ]` NÃO VERIFICADO: O contador "N de 500 caracteres" é lido ao focar o campo (como descrição) e NÃO é falado a cada tecla digitada (req. 4.4). Anotar se o comportamento incomoda ou se algum leitor fala o valor repetidamente.
- `[ ]` NÃO VERIFICADO: Ao chegar a 500 caracteres, o leitor não anuncia nada de forma confusa e o contador mostra "500 de 500 caracteres".

**Erro (envio vazio):**

- `[ ]` NÃO VERIFICADO: Tocar em "Enviar comentário" com o campo vazio (ou só espaços): o leitor anuncia "Comentário vazio. Escreva um comentário antes de enviar." em até cerca de 1 segundo (req. 5.4).
- `[ ]` NÃO VERIFICADO: O foco vai para o campo e o leitor fala o rótulo, "inválido" e a mensagem "Escreva um comentário antes de enviar." (req. 5.3, 5.4).
- `[ ]` NÃO VERIFICADO: O erro não é falado duas vezes de forma confusa (região `#anuncio` mais descrição do campo). Anotar o que foi ouvido.
- `[ ]` NÃO VERIFICADO: Ao digitar no campo, a mensagem de erro some e o leitor não continua falando o erro antigo (req. 5.5).

**Envio, agradecimento e leitura dupla:**

- `[ ]` NÃO VERIFICADO: Ao enviar, o botão aparece como "Enviando" e desabilitado, e o leitor identifica o formulário como ocupado (`aria-busy`) ou fala "Enviando" (req. 7.2).
- `[ ]` NÃO VERIFICADO: Depois do sucesso, o agradecimento ("Obrigado pelo seu comentário! Ele ajuda a melhorar o autoatendimento.") é falado em até cerca de 1 segundo (req. 7.7).
- `[ ]` NÃO VERIFICADO: O foco vai para a região do agradecimento (`role="status"`, `aria-live="polite"`) (req. 7.6).
- `[ ]` NÃO VERIFICADO: **Leitura dupla.** O design aceita que, por a região `role="status"` ser preenchida e receber o foco ao mesmo tempo, o leitor leia o agradecimento duas vezes (uma pelo foco, outra pela região viva). Em cada combinação da tabela acima, anotar: lê uma vez, lê duas vezes ou não lê. Se ler duas vezes ou nenhuma, registrar como pendência para decisão (não alterar o requisito sem input do usuário).
- `[ ]` NÃO VERIFICADO: O campo e o botão ficam desabilitados e o texto enviado continua legível por navegação do leitor (modo de leitura).
- `[ ]` NÃO VERIFICADO: Escolher uma estrela depois do envio continua anunciando o agradecimento da avaliação (req. 3.4).
- `[ ]` NÃO VERIFICADO: Voltar para `#/confirma/ID` e avançar de novo para `#/resolvido/ID` na mesma jornada mostra o estado "já enviado", e o leitor lê o agradecimento visível (req. 7.8).

**Falha de envio:**

- `[ ]` NÃO VERIFICADO: Provocar uma falha (seção 8.5, ou `localStorage` bloqueado em Modo_Prototipo): o bloco de falha (`role="alert"`) é anunciado de imediato e o foco vai para ele (req. 8.1, 8.3).
- `[ ]` NÃO VERIFICADO: A falha não é lida duas vezes de forma confusa (`role="alert"` mais foco). Anotar o que foi ouvido.
- `[ ]` NÃO VERIFICADO: Depois da falha, o texto digitado continua no campo, o campo e o botão voltam a ser operáveis e o leitor consegue tentar de novo (req. 8.2).

Observações:

```
(preencher)
```

### 8.2 Celular físico

| Aparelho | Sistema | Navegador | Data / responsável | Status |
| --- | --- | --- | --- | --- |
| (ex.: Android de entrada, tela pequena) | | Chrome | | `[ ]` NÃO VERIFICADO |
| (ex.: iPhone) | iOS | Safari | | `[ ]` NÃO VERIFICADO |
| (outro) | | | | `[ ]` NÃO VERIFICADO |

Conferir em cada aparelho, em pé e com uma mão, como o consumidor usaria na frente da máquina:

- `[ ]` NÃO VERIFICADO: Sem rolagem horizontal e sem texto cortado ou sobreposto na Tela_de_Resolvido, antes e depois do envio, em retrato (req. 12.1).
- `[ ]` NÃO VERIFICADO: Em tela de 360 px de largura (ou a menor disponível), o bloco inteiro continua utilizável: estrelas, campo, aviso, contador, botão e links (req. 12.1).
- `[ ]` NÃO VERIFICADO: Ao tocar no campo, o teclado virtual abre e o campo com foco não fica escondido atrás dele. O botão "Enviar comentário" é alcançável com o teclado aberto (rolando, se preciso).
- `[ ]` NÃO VERIFICADO: O iPhone não dá zoom automático ao tocar no campo (fonte de 16 px) (req. 12.3).
- `[ ]` NÃO VERIFICADO: O teclado não oferece preenchimento automático de nome, e-mail ou telefone para este campo (`autocomplete="off"`).
- `[ ]` NÃO VERIFICADO: Alvos de toque: as 5 estrelas, o campo, o botão "Enviar comentário" e os links "Tenho outro problema" e "Voltar ao início" são fáceis de tocar sem acertar o vizinho (44 px e 8 px de espaçamento, req. 12.2). Anotar qualquer toque errado.
- `[ ]` NÃO VERIFICADO: A tecla Enter do teclado virtual insere quebra de linha e não envia o comentário (req. 5.7).
- `[ ]` NÃO VERIFICADO: **Texto colado de 500+ caracteres.** Copiar um texto com bem mais de 500 caracteres (por exemplo, 800, com acentos e emoji) e colar no campo: o texto é cortado em 500, o contador mostra "500 de 500 caracteres" e o que já estava digitado não some (req. 4.3). Repetir com um emoji exatamente na posição 500 e anotar o que acontece (corta no meio do emoji?).
- `[ ]` NÃO VERIFICADO: Digitar com ditado por voz do aparelho: o texto entra no campo, o contador acompanha e o limite vale.
- `[ ]` NÃO VERIFICADO: Girar o aparelho para paisagem e voltar: o texto digitado e o contador continuam.
- `[ ]` NÃO VERIFICADO: Com a conexão lenta ou instável (Modo_API de teste, seção 8.5), o botão mostra "Enviando" e um segundo toque não gera segundo envio (req. 7.3).
- `[ ]` NÃO VERIFICADO: Em sol forte ou brilho médio, o rótulo, o aviso, o contador, as mensagens de erro e de falha e o agradecimento continuam legíveis.

Observações:

```
(preencher)
```

### 8.3 Firefox e Safari (e conferência no Chrome/Edge)

| Navegador | Versão | Sistema | Data / responsável | Status |
| --- | --- | --- | --- | --- |
| Firefox | | Windows ou macOS | | `[ ]` NÃO VERIFICADO |
| Safari | | macOS | | `[ ]` NÃO VERIFICADO |
| Safari | | iOS | | `[ ]` NÃO VERIFICADO |
| Chrome ou Edge (referência) | | | | `[ ]` NÃO VERIFICADO |

Em cada um, percorrer o fluxo até `#/resolvido/ID` e conferir:

- `[ ]` NÃO VERIFICADO: O bloco aparece com o mesmo layout da referência: campo com 4 linhas, aviso e contador abaixo, botão abaixo, tudo em uma coluna.
- `[ ]` NÃO VERIFICADO: O campo tem altura e fonte de 16 px, aceita digitação e redimensiona só na vertical.
- `[ ]` NÃO VERIFICADO: O limite de 500 caracteres vale digitando e colando, e o contador atualiza a cada alteração.
- `[ ]` NÃO VERIFICADO: O indicador de foco aparece ao navegar com Tab (estrelas, campo, botão, links) e não é cortado (req. 12.5). No Safari, conferir também com a opção "Pressionar Tab realça cada item" ativada.
- `[ ]` NÃO VERIFICADO: Tab e Shift+Tab percorrem os controles na ordem visual, sem armadilha de foco (req. 12.4).
- `[ ]` NÃO VERIFICADO: Enter no campo insere quebra de linha; Enter ou Espaço no botão focado envia (req. 5.7).
- `[ ]` NÃO VERIFICADO: O estado desabilitado (durante o envio e depois de enviado) mostra o texto do campo e do botão com boa legibilidade, sem ficar esmaecido (o Safari costuma alterar a cor do texto de campos desabilitados; conferir `-webkit-text-fill-color`).
- `[ ]` NÃO VERIFICADO: A mensagem de erro de campo vazio, o agradecimento e o bloco de falha aparecem com texto, borda e ícone legíveis.
- `[ ]` NÃO VERIFICADO: Botão voltar e avançar do navegador: voltar para `#/confirma/ID` e avançar mostra o estado "já enviado" quando houve envio (req. 7.8), e o campo vazio quando não houve.
- `[ ]` NÃO VERIFICADO: Escolher um problema na lista (mesmo o mesmo) e voltar ao resolvido: campo vazio, estado "já enviado" descartado (req. 7.9).
- `[ ]` NÃO VERIFICADO: Com `prefers-reduced-motion: reduce` ativado no sistema, nenhuma animação nem rolagem suave no bloco (req. 12.8).
- `[ ]` NÃO VERIFICADO: Sem erros novos no console durante o fluxo e sem o texto do comentário impresso no console.
- `[ ]` NÃO VERIFICADO: Modo privado do navegador (em que o `localStorage` pode estar restrito): em Modo_Prototipo, a falha de gravação mostra a mensagem de falha e mantém o texto (req. 8.1, 9.7). A falha só nas métricas não deve mostrar erro (req. 11.7).
- `[ ]` NÃO VERIFICADO: As demais rotas (`#/`, `#/problemas`, `#/solucao/ID`, `#/confirma/ID`, `#/suporte/ID`, `#/chamado/ID`, `#/contato`) continuam como antes, sem o bloco de comentário (req. 14.1, 14.3).

Observações:

```
(preencher)
```

### 8.4 Contraste e sensação visual do bloco

A razão de contraste dos pares de tokens é calculada por `tests/estatico.js`, mas só uma pessoa avalia o resultado real em tela. Medir com uma ferramenta (seletor de cores das ferramentas do navegador ou Colour Contrast Analyser).

| Item | Data / responsável | Status |
| --- | --- | --- |
| Tela_de_Resolvido em tela de computador | | `[ ]` NÃO VERIFICADO |
| Tela_de_Resolvido em celular | | `[ ]` NÃO VERIFICADO |

**Pares de cores novos e botão desabilitado (mínimo 4,5:1 para texto, req. 12.6; 3:1 para bordas e foco, req. 12.5):**

| Par | Onde aparece | Medido | Status |
| --- | --- | --- | --- |
| Texto `--texto` sobre `--campo-fundo` (branco) | texto digitado no campo | | `[ ]` NÃO VERIFICADO |
| Rótulo e "(opcional)" sobre o fundo da tela | rótulo do campo | | `[ ]` NÃO VERIFICADO |
| `--texto-suave` sobre o fundo | aviso de não identificação e contador | | `[ ]` NÃO VERIFICADO |
| `--erro` sobre `--erro-fundo` | mensagem de campo vazio e bloco de falha | | `[ ]` NÃO VERIFICADO |
| `--texto` sobre `--sucesso-fundo` | agradecimento | | `[ ]` NÃO VERIFICADO |
| `--texto` sobre `--campo-fundo-desabilitado` (`--creme`) | campo travado (envio e "já enviado") | | `[ ]` NÃO VERIFICADO |
| `--texto` sobre `--campo-fundo-desabilitado` | botão "Enviando" e botão travado depois do envio | | `[ ]` NÃO VERIFICADO |
| Borda `--campo-borda` do campo e do botão desabilitado sobre o fundo | contorno dos controles | | `[ ]` NÃO VERIFICADO |
| Indicador de foco sobre o fundo adjacente | campo e botão | | `[ ]` NÃO VERIFICADO |

- `[ ]` NÃO VERIFICADO: O botão desabilitado ("Enviando" e depois do envio) é legível e passa de 4,5:1. A regra global `.btn[disabled]` usa `opacity: 0.45`, que derrubaria o contraste; confirmar que dentro do bloco ela não vale (`.feedback .btn[disabled]` com `opacity: 1`). Se o botão ficar apagado, registrar como falha.
- `[ ]` NÃO VERIFICADO: É possível distinguir o botão desabilitado do habilitado sem depender só da cor (texto "Enviando", cursor, borda).
- `[ ]` NÃO VERIFICADO: Erro, envio, falha e sucesso são indicados por texto e não só por cor ou ícone (req. 12.7).
- `[ ]` NÃO VERIFICADO: Zoom do navegador a 200% e fonte maior do sistema: nada some, sobrepõe ou fica cortado no bloco.
- `[ ]` NÃO VERIFICADO: Modo de alto contraste do sistema (Windows) ou tema escuro forçado: campo, botão, texto e foco continuam visíveis.

**Sensação visual (sem critério de aprovação automático; dar nota ou comentar):**

- `[ ]` NÃO VERIFICADO: O bloco de comentário parece parte da avaliação "Como foi a ajuda?", logo abaixo das estrelas, e não um formulário separado.
- `[ ]` NÃO VERIFICADO: Fica claro que o comentário é opcional e que só mandar as estrelas basta.
- `[ ]` NÃO VERIFICADO: O aviso de não identificação é percebido sem assustar nem pesar.
- `[ ]` NÃO VERIFICADO: O agradecimento e a falha são percebidos de imediato (posição, borda, ícone).
- `[ ]` NÃO VERIFICADO: O visual combina com o restante do Autoatendimento TRES (cores, tipografia, botões).
- `[ ]` NÃO VERIFICADO: O bloco não parece "quebrado" em larguras intermediárias (600 a 900 px), com o formulário alinhado à esquerda e limitado a 640 px.

Observações:

```
(preencher)
```

### 8.5 Modo_API real do feedback

Requisitos: 7.5, 8.1, 10.4 a 10.10, 10.16, 14.8. **O contrato é provisório (versão `"1"`).** Não existe endpoint de feedback nem acordo com o back end. Esta subseção só pode ser executada contra um endpoint de teste. Sem ele, marcar `[-]` N/A.

**Pré-requisitos (dependem do time de back end):**
- URL do endpoint de teste de feedback (https, ou http em `localhost` ou `127.0.0.1`).
- CORS liberado para a origem usada no teste.
- Ambiente de teste, nunca produção, e sem dados pessoais reais.

**Como ativar:** em `js/data.js`, preencher `FEEDBACK.config.API_FEEDBACK_URL` com a URL de teste. Para testar o tempo limite, pode-se usar uma rede lenta (throttling) em vez de editar `TIMEOUT_FEEDBACK_MS`. **Ao terminar, voltar `API_FEEDBACK_URL` para vazia (`''`).** O padrão entregue deve continuar vazio (req. 14.8). `API_CHAMADOS_URL` também deve continuar vazia.

Abrir a aba Rede (Network) das ferramentas do navegador durante os testes.

**Envio com sucesso:**

| Item | Status |
| --- | --- |
| Uma requisição `POST` vai para `API_FEEDBACK_URL`, com `Content-Type: application/json` | `[ ]` NÃO VERIFICADO |
| O corpo tem exatamente os 7 campos do contrato provisório: `versaoContrato` (`"1"`), `chaveIdempotencia`, `enviadoEm`, `comentario`, `nota`, `problemaId`, `modelo` | `[ ]` NÃO VERIFICADO |
| O corpo não tem nome, e-mail, telefone, protocolo, título do problema nem dados de métricas | `[ ]` NÃO VERIFICADO |
| `chaveIdempotencia` é um UUID v4; `enviadoEm` está em ISO 8601 com fuso; `nota` é 1 a 5 ou `null`; `modelo` é o id do modelo ou `null` | `[ ]` NÃO VERIFICADO |
| O `comentario` chega com as pontas sem espaços e com acentos, emoji, quebras de linha, aspas, barras invertidas, `<`, `>` e `&` preservados | `[ ]` NÃO VERIFICADO |
| Qualquer resposta 2xx (com ou sem corpo) mostra o agradecimento, igual ao Modo_Prototipo e sem aviso de protótipo | `[ ]` NÃO VERIFICADO |
| Nenhum token, segredo ou chave de API aparece nos cabeçalhos ou no código | `[ ]` NÃO VERIFICADO |
| O `localStorage` não ganha a chave `tres-autoatendimento-feedbacks` (nem `tres-autoatendimento-chamados`) | `[ ]` NÃO VERIFICADO |
| O evento `comentario` aparece em `tres-autoatendimento-eventos` sem texto, sem nota, sem tamanho e sem chave de idempotência | `[ ]` NÃO VERIFICADO |
| Nenhuma requisição vai para `API_CHAMADOS_URL` por causa do feedback | `[ ]` NÃO VERIFICADO |
| Com `API_FEEDBACK_URL` vazia e `API_CHAMADOS_URL` preenchida, nenhuma requisição de feedback é feita (Modo_Prototipo) | `[ ]` NÃO VERIFICADO |

**Falhas** (conferir: bloco de falha com a mensagem, sem detalhe técnico; texto preservado; botão e campo reabilitados; nenhum agradecimento; nenhum evento `comentario`; estrelas, "Cuidados com a sua máquina" e links funcionando):

| Caso | Como provocar | Status |
| --- | --- | --- |
| Rede indisponível | Desligar a rede ou marcar "Offline" nas ferramentas | `[ ]` NÃO VERIFICADO |
| Tempo limite | Endpoint que demora mais que `TIMEOUT_FEEDBACK_MS` (10 s) ou throttling | `[ ]` NÃO VERIFICADO |
| Erro HTTP 4xx | Endpoint de teste que responde 400 | `[ ]` NÃO VERIFICADO |
| Erro HTTP 5xx | Endpoint de teste que responde 500 | `[ ]` NÃO VERIFICADO |
| Bloqueio por CORS | Origem não liberada no back end | `[ ]` NÃO VERIFICADO |

- `[ ]` NÃO VERIFICADO: Em nenhuma falha o front end repete a requisição sozinho.
- `[ ]` NÃO VERIFICADO: A nova tentativa manual, mesmo com o texto editado, envia a mesma `chaveIdempotencia` da tentativa anterior (comparar na aba Rede) (req. 8.6).
- `[ ]` NÃO VERIFICADO: Depois de uma falha seguida de sucesso, existe um único feedback no back end de teste.
- `[ ]` NÃO VERIFICADO: Duplo clique em "Enviar comentário" gera uma só requisição (req. 7.3).
- `[ ]` NÃO VERIFICADO: A falha do comentário não impede nem desfaz o registro da nota (e vice-versa) (req. 3.5).

**Pontos em aberto com o back end (contrato provisório; Modo_API não deve ir para produção enquanto estiverem pendentes):**

| Ponto | Resposta / data / responsável | Status |
| --- | --- | --- |
| URL do endpoint de feedback por ambiente | | `[ ]` PENDENTE |
| Autenticação e autorização do endpoint | | `[ ]` PENDENTE |
| Política de CORS | | `[ ]` PENDENTE |
| Esquema do banco de dados | | `[ ]` PENDENTE |
| Formato da resposta de sucesso (hoje o cliente aceita qualquer 2xx, sem exigir corpo) e códigos de erro | | `[ ]` PENDENTE |
| Chave de idempotência repetida: o back end ignora o duplicado? Devolve sucesso? | | `[ ]` PENDENTE |
| Chave de idempotência também em cabeçalho HTTP? | | `[ ]` PENDENTE |
| Limites de tamanho, limitação de taxa (rate limit) | | `[ ]` PENDENTE |
| Prazo e política de retenção dos comentários | | `[ ]` PENDENTE |
| Valor definitivo de `TIMEOUT_FEEDBACK_MS` e da `versaoContrato` | | `[ ]` PENDENTE |

Observações:

```
(preencher)
```

### 8.6 Pendências jurídicas e LGPD do texto livre

Estes itens não são testes de código: dependem de decisão de outras áreas. Continuam PENDENTES até receberem resposta registrada aqui. O texto livre pode conter dado pessoal digitado pelo consumidor, e o sistema não detecta nem remove (req. 2.5). Em Modo_Prototipo o texto fica em texto puro no `localStorage` do navegador, em dispositivo possivelmente compartilhado, até 50 registros. É aceitável para demonstração e **inaceitável em produção** sem estas respostas.

| Item | Situação atual no projeto | Responsável / data / resposta | Status |
| --- | --- | --- | --- |
| Revisão jurídica do texto do aviso de não identificação | Texto `ILUSTRATIVO` em `FEEDBACK.textos.avisoNaoIdentificacao` | | `[ ]` PENDENTE |
| Avaliação do risco de dado pessoal digitado no texto livre | Sem detecção nem remoção; só o aviso | | `[ ]` PENDENTE |
| Base legal, finalidade e transparência da coleta do comentário | Sem aceite de termos e sem aviso de privacidade no bloco | | `[ ]` PENDENTE |
| Política de retenção e descarte dos comentários | Sem definição (Modo_API) | | `[ ]` PENDENTE |
| Direitos do titular sobre texto livre que contenha dado pessoal (consulta, correção, exclusão) | Sem processo definido | | `[ ]` PENDENTE |
| Quem pode ler os comentários e como (não há painel nem moderação) | Fora do escopo da spec | | `[ ]` PENDENTE |
| Limpeza de `tres-autoatendimento-feedbacks` em aparelhos de demonstração | Não existe comando de limpeza | | `[ ]` PENDENTE |

Verificações a fazer quando as respostas chegarem:

- `[ ]` NÃO VERIFICADO: O aviso de não identificação revisado está em `js/data.js` (1 a 200 caracteres, pedindo para não escrever nome, e-mail, telefone nem outros dados pessoais) e a marcação `ILUSTRATIVO` foi atualizada.
- `[ ]` NÃO VERIFICADO: Se o jurídico exigir aviso de privacidade, aceite ou link de política no bloco, abrir nova tarefa na spec (muda o escopo atual, que não tem aceite nem identificação).
- `[ ]` NÃO VERIFICADO: A política de retenção definida foi comunicada ao time de back end antes de ativar o Modo_API.

Observações:

```
(preencher)
```

### 8.7 Limpeza ao terminar a seção 8

- `[ ]` `API_FEEDBACK_URL` em `js/data.js` voltou a ser vazia (e `API_CHAMADOS_URL` também).
- `[ ]` Dados de teste (comentários) removidos do back end de teste e do `localStorage` dos aparelhos, em especial a chave `tres-autoatendimento-feedbacks`.
- `[ ]` Servidor `python -m http.server` encerrado.
- `[ ]` Falhas encontradas registradas como novas tarefas ou pendências no `CONTEXTO-PROJETO.md`.

---

## 9. Resumo de execução

Preencher ao fim de cada rodada.

| Seção | Executada? | Data | Responsável | Resultado (OK / falhou / N/A) |
| --- | --- | --- | --- | --- |
| 1. Leitor de tela | Não | | | NÃO VERIFICADO |
| 2. Celular físico | Não | | | NÃO VERIFICADO |
| 3. Firefox e Safari | Não | | | NÃO VERIFICADO |
| 4. Contraste e sensação visual | Não | | | NÃO VERIFICADO |
| 5. Visual do Figma | Não | | | NÃO VERIFICADO |
| 6. Modo_API real | Não | | | NÃO VERIFICADO |
| 7. Jurídico, LGPD e prazo | Não | | | PENDENTE |
| 8.1 Comentário: leitor de tela (inclui leitura dupla do agradecimento) | Não | | | NÃO VERIFICADO |
| 8.2 Comentário: celular físico (teclado, 360 px, alvos de toque, texto colado de 500+) | Não | | | NÃO VERIFICADO |
| 8.3 Comentário: Firefox e Safari | Não | | | NÃO VERIFICADO |
| 8.4 Comentário: contraste dos pares novos, botão desabilitado e sensação visual | Não | | | NÃO VERIFICADO |
| 8.5 Comentário: Modo_API real do feedback (contrato provisório) | Não | | | NÃO VERIFICADO |
| 8.6 Comentário: jurídico e LGPD do texto livre | Não | | | PENDENTE |

### Limpeza ao terminar

- `[ ]` `API_CHAMADOS_URL` em `js/data.js` voltou a ser vazia.
- `[ ]` `API_FEEDBACK_URL` em `js/data.js` voltou a ser vazia (seção 8.5).
- `[ ]` Servidor `python -m http.server` encerrado.
- `[ ]` Dados de teste removidos do back end de teste e do `localStorage` dos aparelhos.
- `[ ]` Falhas encontradas registradas como novas tarefas ou pendências no `CONTEXTO-PROJETO.md`.
