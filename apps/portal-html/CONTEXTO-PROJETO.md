# Contexto do projeto: Autoatendimento TRES (Hackathon Cafeína Week 2026)

> Arquivo para retomar o trabalho em outra conversa. Cole-o (ou anexe-o) no início da nova conversa.
> Gerado ao final da primeira sessão. Tudo marcado como **NÃO VERIFICADO** não foi testado de fato.

## 1. O desafio

- **Evento:** Hackathon Cafeína Week 2026, FIAP, presencial, 13 e 14 de outubro de 2026.
- **Desafio 03, Customer Success: "Autoatendimento TRES"** (3corações).
- **Problema:** mais de 70% dos chamados técnicos das máquinas TRES são **falsos defeitos** (limpeza simples ou dúvida de uso). Isso gera custo de logística, manutenção e tempo de atendente.
- **Missão:** criar uma jornada de autoatendimento que ajude o consumidor a resolver sozinho o que não é defeito, e leve ao atendimento humano só o que realmente precisa dele.
- **Pergunta-guia (rascunho no briefing):** como ajudar o consumidor TRES a resolver sozinho, de forma simples e rápida, o que não é defeito, e levar ao atendimento humano só o que precisa dele?
- **Máquinas do desafio:** LOV, Modo, Passione, Luna e Touch. A Mimo fica fora.
- **Entregas esperadas:** (1) protótipo funcional; (2) jornada de ponta a ponta (da busca do modelo até a solução ou o transbordo para uma pessoa); (3) pitch de 5 minutos (problema, solução, como mede a deflexão de chamados, o que falta para virar POC); (4) código, README e especificações (como rodar e premissas assumidas sobre manuais e medição).
- **Critérios de avaliação:** Aderência ao desafio 25%; Impacto no negócio e no usuário 25%; Criatividade e diferenciação 20%; Viabilidade 20%; Protótipo e comunicação 10%.
- **"Tempero" do briefing (IA sustentável):** quando a IA precisa entrar, como reaproveitar respostas repetidas, quanto custa cada dúvida resolvida. (Esta solução não usa IA: é um guia determinístico.)
- **Pistas do briefing:** landing page com busca por modelo; guia dos falsos defeitos mais comuns; chatbot com IA (não feito); simular transbordo para humano; registrar a resolução por camada para medir a deflexão.

## 2. A solução construída

Landing page (HTML, CSS e JS puros, sem build) pensada como uma página dentro do site da 3corações. Ela **não cria conteúdo novo**: simplifica e torna visual o conteúdo que a empresa já tem (Central de Ajuda, 5 guias rápidos e o "Mapa da Jornada de Atendimento" com 13 fichas).

### Jornada
1. **Sua máquina:** 5 cards com foto (LOV, Modo, Passione, Luna, Touch) e uma descrição curta para reconhecimento. Opção "Não sei qual é a minha" (dica de onde achar o nome e botão para continuar sem escolher).
2. **O problema:** 13 problemas, busca por texto livre (com pontuação por relevância), filtros por categoria, e os 4 motivos mais frequentes em destaque ("Mais comuns").
3. **A solução:** um passo por tela, com barra de progresso, tipo do passo ("Confira" ou "Faça"), "como fazer" embutido (reset, passagem de água, retrolavagem) e, para a Touch, uma ilustração 3D.
4. **"O problema foi solucionado?"**
   - **Sim:** tela de sucesso (Tela_de_Resolvido, `#/resolvido/ID`), avaliação por estrelas, **comentário opcional** logo abaixo das estrelas (**novo**, funcionalidade "resolved-feedback-comment"; veja a seção 13) e "Cuidados com a sua máquina" (limpeza, volumes, link do guia em PDF). A ordem na tela é: estrelas, comentário, cuidados, links finais.
   - **Não:** tela de assistência técnica com telefone, horários, e-mail, o que ter em mãos e avaliação. **Atualizado (funcionalidade "ticket-opening-screen"):** o desfecho "Não" agora abre a **Tela_de_Chamado** (`#/suporte/ID`), onde a pessoa vê o resumo do que já percorreu, preenche nome, e-mail, telefone (usado como WhatsApp) e descrição, aceita os termos e abre o chamado. O envio leva à **Tela_de_Confirmacao** (`#/chamado/ID`), com protocolo, prazo ilustrativo, avaliação por estrelas e os canais de contato direto. Veja a seção 12.
5. Rodapé e cabeçalho levam ao contato direto, de forma discreta (o humano é o último recurso).

### Decisões de UX registradas
- Mobile primeiro (a pessoa está em pé na frente da máquina com o celular).
- A etapa de modelo personaliza (cuidados, guia PDF, ilustração 3D), mas os passos de solução valem para todas as máquinas.
- Texto sempre é o conteúdo principal; o 3D é apoio. Foto da Touch é a reserva se o 3D falhar.
- Acessibilidade: link "pular para o conteúdo", foco movido para o título a cada tela, `aria-live` nos passos e nas avaliações, alvos de toque de 44 px ou mais, `prefers-reduced-motion`. Fotos dos modelos usam `alt=""` de propósito (o nome do modelo está escrito ao lado). **NÃO VERIFICADO** com leitor de tela real.
- Cores são **provisórias** (variáveis no começo de `css/styles.css`); trocar pelas do guia de marca.

## 3. Estrutura de arquivos

```
D:\autoatendimento-3coracoes\
  index.html                  estrutura de todas as telas
  css\styles.css              estilos (mobile primeiro)
  js\data.js                  TODO o conteúdo (window.TRES_DATA)
  js\app.js                   navegação, busca, passos, desfechos, 3D, métricas
  js\chamado.js               núcleo do chamado sem DOM (window.TRESChamado; em Node, module.exports). Ver seção 12
  js\feedback.js              núcleo do comentário opcional sem DOM (window.TRESFeedback; fábrica criar(base); em Node, module.exports = { criar }). Ver seção 13
  tests\                      testes de desenvolvimento (NÃO fazem parte do site). Ver seções 12 e 13
  js\vendor\model-viewer-umd.min.js   @google/model-viewer 4.4.0 (local, sem CDN) + LICENSE
  img\LOV.png Luna.png Modo.png Passione.png TOUCH.png   ORIGINAIS enviados pelo usuário (não alterar)
  img\web\lov.png luna.png modo.png passione.png touch.png   cópias leves (até 440 px) usadas na página
  modelos3d\c0adab67d5fc6db5e82670d1271e4559.glb   ORIGINAL (48 MB, não alterar)
  modelos3d\maquina-web.glb   cópia otimizada (5 MB) usada na página
  material\                   material extraído do zip (não alterar)
    autoatendimento.html, Mapa_da_Jornada_de_Atendimento (1).pdf, mapa.txt (texto extraído),
    Autoatendimentoqrcode_drive.google.com.png, guias\ (lov/modo/passione/luna/touch .pdf e .txt)
  CONTEXTO-PROJETO.md         este arquivo
```

- **Zip original do hackathon:** `D:\Materiais _ Hackathon-20261013T105209Z-1-001 (1).zip` (só a pasta `Autoatendimento` interessa a este desafio; as outras são de outros desafios).
- **Como rodar:** na pasta do projeto, `python -m http.server 8000` e abrir `http://localhost:8000`. O usuário já roda assim.
- **Abrir por duplo clique (`file://`) não carrega o 3D** (aparece a foto de reserva). Teste feito: deu erro no Edge por `file://`, mas o teste de controle por HTTP ficou inconclusivo no navegador sem tela. O usuário confirmou que por HTTP funciona. Alternativa não implementada: embutir o `.glb` em base64 num `.js` (~7 MB) para funcionar sem servidor.

### Rotas (hash)
`#/` (modelo), `#/problemas`, `#/solucao/ID`, `#/confirma/ID`, `#/resolvido/ID`, `#/suporte/ID`, `#/contato`. O botão voltar do navegador funciona. A máquina escolhida fica só em memória (recarregar a página perde a escolha).
**Nova rota:** `#/chamado/ID` (Tela_de_Confirmacao). `#/suporte/ID` continua existindo, mas agora mostra a Tela_de_Chamado (formulário) em vez do cartão de contato.
`#/resolvido/ID` não ganhou rota nova, mas a tela ganhou o bloco de comentário opcional (seção 13). Nas demais rotas o bloco não existe.

### `js/data.js` (window.TRES_DATA)
`CONTATO`, `COMO_FAZER` (reset, passagem, retrolavagem), `CATEGORIAS`, `PROBLEMAS` (13), `MODELOS` (5, com `imagem`, `dica`, `guia`, `cuidados`, `alertas`, `botoes`), `BOTOES_BEBIDA`, `AVISOS_GERAIS`, `MODELO_3D`.
Também há `CHAMADO` (novo): `config` (`API_CHAMADOS_URL`, vazia por padrão, e `TIMEOUT_ENVIO_MS`, 10000) e `textos` (todos os textos da Tela_de_Chamado e da Tela_de_Confirmacao). Ver seção 12.
E `FEEDBACK` (novo): `config` (`API_FEEDBACK_URL`, vazia por padrão, `TIMEOUT_FEEDBACK_MS`, 10000, e `VERSAO_CONTRATO_FEEDBACK`, `'1'`) e `textos` (todos os textos do comentário opcional). Ver seção 13. `window.TRES_DATA` passou a exportar também `CHAMADO` e `FEEDBACK`.
Cada passo tem `tipo` (`checar` ou `acao`), `texto`, opcionais `detalhe`, `ref` (chave de COMO_FAZER), `porModelo`, `link` e `visual` (3D).

## 4. Conteúdo: os 13 problemas (fonte: Mapa da Jornada de Atendimento)

| id | Problema | Mais comum |
|---|---|---|
| 1 | A máquina não liga | |
| 2 | Luz vermelha fixa | |
| 3 | Alerta vermelho piscando | |
| 4 | Teclas das xícaras e sensor vermelho piscando | |
| 5 | Luz amarela acesa (reset do contador) | |
| 6 | A máquina não extrai bebida | sim |
| 7 | Bebida aguada | |
| 8 | Bebida fria | |
| 9 | Alavanca travada | |
| 10 | Vazamento | sim |
| 11 | A máquina não puxa água | sim |
| 12 | Bico entupido | sim |
| 13 | A alavanca não fecha com a cápsula | |

As fichas originais foram escritas para o atendente; foram reescritas na voz direta com o consumidor, sem acrescentar instruções que não estão nas fontes.

### Fontes de conteúdo
- Guias rápidos oficiais (PDFs): LOV, Modo, Passione, Luna e Touch (URLs em `js/data.js`, campo `guia`). Textos extraídos em `material/guias/*.txt`.
- Contatos (Central de Ajuda): **0800 979 2021**; segunda a sexta 08h às 18h; sábado 08h às 12h; `atendimento@3coracoes.com.br`.
- Volumes padrão (guias Passione, Luna e Touch): espresso 50 mL; cappuccino, chocolatto e cremosas 80 mL; filtrados e chás 100 mL. Na Modo o volume é reprogramável de 30 a 250 mL.
- Limpeza completa a cada 15 dias: Passione e Touch. Limpeza semanal do bico: Luna. LOV: limpeza diária.

## 5. Ilustração 3D (somente Touch)

- **Escopo acordado:** um modelo só (Touch), peça única (sem animação), ilustrando apenas passos que usam peças visíveis. Aparece só se o usuário escolheu a Touch.
- **Modelo original:** 48 MB, 1 nó, 1 malha, 1 material, 486 mil triângulos, 30 MB de texturas PNG, sem animações. Provavelmente gerado por ferramenta de IA (nome das texturas); superfície irregular. O usuário aceitou a qualidade.
- **Otimização feita:** `npx @gltf-transform/cli@4.5.1 optimize ... --compress false --texture-compress webp --texture-size 1024 --simplify true --simplify-ratio 0.08 --simplify-error 0.005` => 5 MB, ~89 mil triângulos, texturas WebP (extensão `EXT_texture_webp`). Sem compressão Draco/meshopt, para não depender de decodificador.
- **Visualizador:** `<model-viewer>` 4.4.0, versão UMD (a versão módulo não funciona bem fora de servidor). Carregado sob demanda no primeiro passo ilustrado.
- **Dimensões do modelo:** ~0,50 x 0,80 x 0,91 m, centro em y = 0,40.
- **Vistas de câmera** (`MODELO_3D.vistas`): `teclas` (alvo `0.008m 0.74m 0.03m`, órbita `0deg 35deg 0.7m`) e `frente` (alvo `0m 0.38m 0.1m`, órbita `15deg 72deg 2.1m`).
- **Rótulos** (`MODELO_3D.pontos`, coordenadas medidas no próprio modelo com `positionAndNormalFromPoint`): `teclas` (0.008, 0.7533, 0.0318), `bico` (-0.0004, 0.4914, 0.3108), `apoio` (-0.0085, 0.144, 0.2916). Se o `.glb` for trocado, medir de novo.
- **Passos ilustrados (problema:passo):** 3:2, 4:1, 5:1, 6:3, 7:1, 8:1, 8:2, 12:2.
- **Controles de câmera (última alteração):** `orbit-sensitivity` 0,5; `zoom-sensitivity` 0,6; `interpolation-decay` 25 ms (1 se o sistema pede menos movimento). **Atenção:** `interpolation-decay` é um TEMPO de amortecimento; valor MAIOR = a câmera escorrega mais (confirmado lendo o código do visualizador). Não testado na prática; o usuário pediu "mais lento e menos drift" e deve confirmar a sensação.
- **Limitação das animações:** como o modelo é uma peça só, só há câmera e rótulos. O usuário pode entregar depois um modelo com peças separadas (alavanca, reservatório, porta-cápsulas) para animar passos como alavanca travada e retrolavagem.

## 6. Medição da deflexão (base para o pitch)

Cada decisão é gravada em `localStorage` (chave `tres-autoatendimento-eventos`, até 500 eventos): `modelo`, `problema`, `resolvido`, `suporte`, `avaliacao`.
No console: `TRESMetricas.resumo()` devolve resolvidos, encaminhados ao suporte, deflexão percentual e contagem por problema. `TRESMetricas.listar()` e `TRESMetricas.limpar()` também existem. **Não há painel nem envio de métricas a servidor**; é só a base. (Atualização: o resumo agora também traz `chamadosAbertos`, e existem os eventos `chamado` e `avaliacao` com `desfecho`. Ver seção 12. Atualização 2: o resumo também traz `comentarios` e existe o evento `comentario`, sem o texto. Ver seção 13.) A deflexão medida assim é a taxa "resolvido na camada guia" contra "foi para o suporte".

## 7. Pendências e pontos em aberto

**Conteúdo (precisa de validação do time de Customer Success):**
- **Bebida fria (ficha 8):** o mapa pede "aumentar a temperatura" mas não diz como. O texto da página só repete a instrução. Marcado `PENDENTE` em `data.js`.
- **Vazamento (ficha 10):** o mapa manda seguir a "resposta de e-mail 37" (conteúdo não fornecido). A página usa só o que os guias dizem (esvaziar a gaveta de cápsulas usadas). Marcado `PENDENTE`.
- **Teclas da Touch:** a foto e o guia da Touch mostram a tecla **vermelha** (não amarela), mas as fichas falam em "amarela, azul e verde". Isso afeta a ficha 4 e o ícone genérico. Ainda não corrigido. Também precisa confirmar com a máquina real se a azul é a do meio.
- **Telefone do SAC:** o guia da Luna traz outro número (0800 0313033). A página usa o da Central de Ajuda (0800 979 2021). Confirmar qual é o oficial.
- **Reset na Touch:** as fichas falam em "botão lateral" e "levantar a alavanca"; na Touch o liga/desliga é um ícone no topo. As legendas do 3D evitam citar esses itens. Confirmar.

**Produto e entrega:**
- Faltam **README**, **especificações** e **roteiro do pitch** (exigidos pelo desafio). O usuário pediu para deixar isso para depois ("mantenha essas propostas para depois").
- Ao formalizar, a plataforma pede escolher: *Build a Feature*, *Fix a Bug* ou *Quick Spec* (e, na funcionalidade, começar por Requisitos ou por Design). **Atualização:** já existem specs em `.kiro/specs/`: `ticket-opening-screen` (seção 12) e `resolved-feedback-comment` (seção 13). Para o restante do projeto ainda não há spec.
- Visual: o card do Modo fica mais alto que os outros (a descrição quebra em 2 linhas). Não corrigido.
- Testado só em largura de 500 px e em Edge. **NÃO VERIFICADO:** celular real, Firefox, Safari, leitor de tela, desempenho do 3D no celular.
- Cores provisórias; ícones dos problemas são emojis (trocar por SVG se houver identidade visual).
- Ideias não feitas: chatbot com IA (camada 2 do briefing), painel de métricas, vídeos da Central de Ajuda, `.bat` para subir o servidor com um clique, base64 do modelo para abrir sem servidor.

## 8. Lições e armadilhas

- **Testes com navegador sem tela:** o Edge headless que usei **recarrega a aba sozinho depois de uns 5 segundos** (provado com uma página trivial, sem código do projeto). Para testar, usar cenários curtos (cada um em carga nova, menos de 4 s). Isso causou várias falsas pistas; capturas em branco no começo vinham de carregamento incompleto.
- Bug antigo corrigido: `replaceChildren(null)` escrevia o texto "null" nos passos. Corrigido com `.filter(Boolean)`.
- Algumas ferramentas de edição (`fs_write`, `str_replace`) ficaram indisponíveis em certos turnos; as edições foram feitas por PowerShell com troca de texto que exige trecho **único**.
- Em PowerShell, cuidado ao reaproveitar variáveis como `$h` e `$r` entre comandos (já viraram número e quebraram scripts).
- A saída do terminal às vezes volta vazia ou truncada; gravar resultados em arquivo e ler depois, sem ler em paralelo com o comando que ainda escreve.
- Lembrar de apagar arquivos temporários (`tmp-*.html` na raiz, servidores `http.server` e perfis do Edge). No fim da sessão não havia sobras.

## 9. Preferências do usuário e regras da conversa

- Responder em **português**; tom direto e acolhedor, sem exageros.
- **Não alterar nenhum material que já existia**: o zip, a pasta `material\`, as imagens originais em `img\` e o `.glb` original. Cópias otimizadas ficam em `img\web\` e `modelos3d\maquina-web.glb`.
- Não fazer commits nem mexer em repositório sem pedido explícito.
- Conteúdo de instrução de máquina **não pode ser inventado** (uma instrução errada gera mais ligação). O que não está nas fontes fica `PENDENTE` e é avisado.
- Antes de afirmar que algo funciona, verificar (build, teste, captura de tela) e dizer o que não foi verificado.
- Escopo do 3D: uma máquina (Touch), peças visíveis, qualidade atual aceita.

## 10. Ambiente

Windows, PowerShell, Python 3.14, Node 24, npm 11, Edge instalado (`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`). O servidor local do usuário roda na porta 8000.

## 11. Texto sugerido para iniciar a próxima conversa

> Estou retomando o projeto "Autoatendimento TRES" (Hackathon Cafeína Week 2026, desafio 03 de Customer Success da 3corações). A pasta está em `D:\autoatendimento-3coracoes` e o arquivo `CONTEXTO-PROJETO.md` tem todo o histórico. Leia-o primeiro e depois os arquivos `index.html`, `css/styles.css`, `js/data.js` e `js/app.js`. Não altere o que está em `material/`, `img/*.png` nem o `.glb` original. Quero seguir com: [descreva o próximo passo, por exemplo "escrever o README e as especificações", "corrigir as teclas da Touch (vermelha)" ou "adicionar o modelo 3D com peças separadas"].

## 12. Funcionalidade: tela de abertura de chamado (spec `ticket-opening-screen`)

Spec em `.kiro/specs/ticket-opening-screen/` (`requirements.md`, `design.md`, `tasks.md`). Tudo continua em HTML, CSS e JS puros, sem build e sem dependências no site.

### O que mudou na jornada
- Antes, "Não, ainda não" mostrava telefone, horários e e-mail. Agora abre a **Tela_de_Chamado** em `#/suporte/ID`: resumo da jornada (modelo, problema, passos percorridos), campos de nome, e-mail, telefone (WhatsApp) e descrição, aceite dos termos e botão "Abrir meu chamado".
- Em caso de sucesso, `location.replace` leva à **Tela_de_Confirmacao** em `#/chamado/ID`: protocolo, prazo, o que acontece depois, **avaliação por estrelas** e os canais de contato direto. O `replace` evita que o botão voltar mostre um formulário já enviado.
- O estado (passos vistos, valores do formulário, chave de idempotência, chamado aberto) fica só em memória e é zerado ao trocar de problema.
- A Tela_de_Chamado e a Tela_de_Confirmacao reaproveitam foco no `h1`, barra de etapas (etapa 3) e `aria-live` das demais telas.

### Arquivos
- `js/chamado.js`: núcleo **sem DOM**, exposto como `window.TRESChamado` (no Node, `module.exports`). Contém validação, normalização, protocolo, chave de idempotência, payload, repositório local, camada de envio e resumo de métricas. Recebe `fetch`, `localStorage`, relógio e sorteio como parâmetros, o que permite testar sem navegador. Funções principais: `montarChamado`, `montarPayload`, `serializar`, `enviar` (via fábrica de envio), `resumirEventos`, `eventoChamado`, `eventoAvaliacao`.
- `js/data.js` → `TRES_DATA.CHAMADO`: `config` e `textos`. Os textos da funcionalidade ficam aqui, nunca no HTML.
- `js/app.js`: rotas `suporte` e `chamado`, montagem das telas, estrelas e registro de métricas. `index.html` e `css/styles.css` ganharam as duas views e tokens semânticos novos (as variáveis de marca antigas não mudaram).
- `tests/`: ver "Suíte de testes" abaixo. Não faz parte do site.

### Modo_Prototipo e Modo_API
- **Modo_Prototipo (padrão):** `TRES_DATA.CHAMADO.config.API_CHAMADOS_URL` vazia. Nenhuma requisição de rede; o chamado é gravado no `localStorage` (chave `tres-autoatendimento-chamados`, com limite de itens) e o protocolo é gerado no navegador.
- **Modo_API:** basta preencher `API_CHAMADOS_URL` com uma URL válida. O `enviar` faz `POST` JSON com `AbortController` e tempo limite (`TIMEOUT_ENVIO_MS`, 10000 ms) e devolve `{ ok, protocolo }` ou `{ ok: false, categoria }`. A tela não sabe qual modo está ativo.
- O payload leva só os 14 campos do contrato (`montarPayload`): sem protocolo, sem `modoEnvio` e sem campo extra.
- A URL **deve continuar vazia** no repositório/entrega do protótipo.
- Formato do protocolo: `TRES-AAAAMMDD-XXXXXX` (6 caracteres de A-Z e 0-9).

### Métricas (sem dados pessoais)
- Eventos no `localStorage` (`tres-autoatendimento-eventos`): `resolvido` e `suporte` (como antes), mais `chamado` (`problema`, `modelo`, `protocolo`, `modo` `api`/`prototipo`, `passos`) e `avaliacao` (agora com `desfecho`: `resolvido`, `suporte` ou `chamado`; o de chamado leva também `protocolo`).
- **Nenhum evento guarda nome, e-mail, telefone ou descrição.** O `app.js` filtra as chaves de dados pessoais de `extras` (lista de chaves proibidas), e há um cenário de UI que verifica isso (`23-dados-pessoais`).
- `TRESMetricas.resumo()` devolve os quatro valores de antes (resolvidos, encaminhados ao suporte, deflexão percentual, por problema), calculados **só** com eventos `resolvido` e `suporte`, e acrescenta `chamadosAbertos`. Eventos `chamado` e `avaliacao` não alteram a deflexão.

### Estrelas na confirmação
A avaliação aparece na Tela_de_Confirmacao, reaproveitando `montarEstrelas` com `desfecho: 'chamado'` e o protocolo. As estrelas são remontadas a cada render e o status é limpo. O espaço entre as estrelas é `gap: 0.5rem` em `.estrelas`.

### Suíte de testes (`tests/`)
Os testes ficam em `tests/` com `package.json` próprio (única dependência de desenvolvimento: `fast-check` 4.10.2). Dentro de `tests/`, rode `npm install` uma vez.
- `npm test`: roda `node --test "*.test.js" "nucleo/*.test.js"`. Cobre o núcleo `js/chamado.js` (propriedades com fast-check e exemplos), os dados (`dados.test.js`), o teste estático (`estatico.test.js`, que usa `estatico.js`) e `smoke.test.js`. Não precisa de navegador.
- `npm run test:ui`: roda `node ui/rodar.js`, que dirige o Edge por CDP (`ui/cdp.js`), com um servidor local de teste (`ui/servidor-teste.js`, usado por `ui/cenarios.js`; ele troca `API_CHAMADOS_URL` só em memória, sem escrever em `js/data.js`), executando os cenários de `ui/cenarios/` (fumaça, fluxo feliz no protótipo, validação, termos, Modo_API, duplo toque, navegação, estrelas, texto literal, responsivo, movimento reduzido, regressão de rotas e dados pessoais). Há também `ui/roteiro-manual.md`.
- `tests/estatico.js`: verificações estáticas dos arquivos do site (consumido pelo teste estático).
- `node tests/verificar-protegidos.js --conferir`: compara com `tests/baseline-protegidos.json` e confirma que nada em `material/`, `img/*.png` originais e no `.glb` original mudou (nem foi criado, movido ou excluído arquivo em `material/`).

### Lições desta funcionalidade
- **`ui/rodar.js` encerra TODOS os processos de Edge de teste** (os que usam o perfil temporário dos testes) ao terminar/limpar. Por isso, para rodar cenários **em paralelo**, não use `npm run test:ui`: chame `node --test` direto nos arquivos de `ui/cenarios/`, para um não matar o navegador do outro.
- **Bug do gap das estrelas:** o espaço entre as estrelas estava errado e foi corrigido para `0.5rem` (`.estrelas { gap: 0.5rem }`). Se mexer nesse CSS, rode o cenário `18-estrelas`.
- Continua valendo a lição da seção 8: o Edge sem tela recarrega a aba depois de uns 5 s; manter cenários curtos.

### Pendências desta funcionalidade
- **Prazo de resposta:** o "2 dias úteis" mostrado na confirmação é **ILUSTRATIVO**. Precisa ser definido pelo time de Customer Success.
- **Texto jurídico/LGPD dos termos:** o texto atual é provisório e precisa de revisão jurídica.
- **Controlador dos dados e contato do encarregado (DPO):** `PENDENTE`. Não inventar; preencher quando a 3corações informar.
- **Back end (para o Modo_API):** URL do endpoint por ambiente, autenticação, **CORS**, esquema do banco, formato da resposta (protocolo) e tratamento de **idempotência** pela chave enviada. Tudo `PENDENTE`/ilustrativo em `data.js`.
- **Figma:** a aplicação do visual do Figma fica para depois (os tokens semânticos já foram preparados no CSS).
- **NÃO VERIFICADO:** leitor de tela (NVDA, VoiceOver, TalkBack), celular real, Firefox e Safari. Os testes de UI rodam só no Edge.

### Observações de ambiente e repositório
- **O diretório `D:\autoatendimento-3coracoes` não é um repositório git** (não há `.git`). Nenhum commit foi feito, conforme as regras da seção 9.
- **Se um dia virar repositório, `tests/node_modules` não deve ser versionado** (adicionar ao `.gitignore`). Manter `tests/package.json` e `tests/package-lock.json`. Não existe `package.json` na raiz e não deve existir: o site continua sem build.

## 13. Funcionalidade: comentário opcional na tela de problema resolvido (spec `resolved-feedback-comment`)

Spec em `.kiro/specs/resolved-feedback-comment/` (`requirements.md`, `design.md`, `tasks.md`). Continua tudo em HTML, CSS e JS puros, sem build e sem dependência nova no site. Não há rota nova: o bloco mora na Tela_de_Resolvido (`#/resolvido/ID`).

### O que mudou na jornada
- Depois de "Sim, resolvi", a Tela_de_Resolvido mostra, **dentro do bloco "Como foi a ajuda?"**, logo abaixo das estrelas (`#estrelas` e `#status-aval`), o `form#form-feedback`. Ordem na tela: estrelas, comentário, "Cuidados com a sua máquina", links "Tenho outro problema" e "Voltar ao início". O `h1`, o `h2` "Como foi a ajuda?", as estrelas e os links finais mantêm os textos de sempre.
- O formulário tem um `textarea#f-comentario` (rótulo "Deixe um comentário sobre a ajuda (opcional)", `maxlength="500"`, `autocomplete="off"`), o aviso de não identificação, o contador "N de 500 caracteres", a mensagem de erro, o botão "Enviar comentário", a região do agradecimento (`#feedback-agradecimento`, `role="status"`, `aria-live="polite"`, `tabindex="-1"`) e a área da falha (`#feedback-falha-area`).
- O comentário é **opcional** e **independente das estrelas**: dá para mandar só a nota (como antes), só o comentário ou os dois. O botão funciona sem nota escolhida e não exibe mensagem que exija a nota.
- Os textos do bloco **não ficam no HTML**: `index.html` só tem `data-texto-feedback="chave"`, e o `app.js` preenche por `textContent` com `TRES_DATA.FEEDBACK.textos`. O bloco não cria título novo; o título é o `h2` que já existia.

### Arquivos
- `js/feedback.js` (novo): núcleo **sem DOM**, módulo UMD com **fábrica `criar(base)`**. `base` é o `TRESChamado`, o que evita copiar código e evita `require(` dentro de `js/` (o teste estático proíbe). No navegador: `window.TRESFeedback = criar(window.TRESChamado)` (ou `null` se o `chamado.js` não carregou; então o `app.js` omite o formulário). Em Node: `module.exports = { criar }`. O mundo externo (relógio, sorteio, `storage`, `fetch`, `AbortController`, temporizadores) entra por parâmetro. Funções: `normalizarComentario`, `validarComentario` (`null`, `'vazio'`, `'tamanho'`), `limitarComentario`, `formatarContador`, `novoEstado`, `garantirEstado`, `aoExibir`, `editarTexto`, `escolherNota`, `prepararEnvio`, `concluirEnvio`, `montarPayload`, `serializar`, `desserializar`, `modoDoFeedback`, `criarPontoDeIntegracao`, `eventoComentario`, `textosValidos`; constantes `LIMITES` (comentário de 1 a 500, no máximo 50 registros), `CHAVE_REPOSITORIO`, `CAMPOS_PAYLOAD`, `CHAVES_TEXTOS_OBRIGATORIOS`. Contagem de caracteres por `String.length`, o mesmo critério do `maxlength`.
- `js/chamado.js` (mudanças aditivas): `resumirEventos` passa a contar `comentarios`, e `formatarIsoComFuso` passou a ser exportada. Nada mais mudou na camada do chamado.
- `js/data.js`: novo `TRES_DATA.FEEDBACK` (abaixo). `TRES_DATA.CHAMADO` ficou como estava.
- `index.html`: `<script src="js/feedback.js">` entre `chamado.js` e `app.js` e o `#form-feedback`.
- `css/styles.css`: token novo `--campo-fundo-desabilitado: var(--creme)` e um bloco "Comentário opcional (Tela_de_Resolvido)" no fim do arquivo (`.feedback`, `.feedback__agradecimento`, `.campo textarea:disabled/[readonly]`, `.feedback .btn[disabled]`, `.cuidados p a`).
- `js/app.js`: `state.feedback`, `renderFeedback`, `iniciarFeedback`, `aoSubmeterFeedback`, `aoEnviarFeedback`, `concluirFeedback`, `mostrarEnviado`, `mostrarFalhaFeedback`, `definirEnviandoFeedback`, `obterStorage()` (extraída da escolha do `localStorage`, agora usada também pelo chamado). `montarEstrelas` ganhou um 5º parâmetro opcional `aoEscolher(n)`; sem ele o comportamento é o de antes.

### `TRES_DATA.FEEDBACK`
- `config.API_FEEDBACK_URL`: **vazia** por padrão (Modo_Prototipo). Independente de `API_CHAMADOS_URL`.
- `config.TIMEOUT_FEEDBACK_MS`: 10000.
- `config.VERSAO_CONTRATO_FEEDBACK`: `'1'`. Observação: no código lido, o `app.js` **não repassa** esse valor ao `montarPayload`; o núcleo usa `'1'` por padrão. Se um dia a versão mudar, ligar os dois.
- `textos`: `rotulo`, `opcional`, `avisoNaoIdentificacao`, `contador` (`'{n} de {max} caracteres'`), `botaoEnviar`, `botaoEnviando`, `erroVazio`, `anuncioErroVazio`, `agradecimento`, `falha`. Os marcadores `{chave}` são trocados por texto literal, nunca por HTML. Cada valor de `config` e o aviso têm comentário `PENDENTE` ou `ILUSTRATIVO` em `data.js`.
- Se `FEEDBACK`, `config`, `textos` ou qualquer chave obrigatória faltar ou estiver vazia (após `trim`), `textosValidos` devolve `false` e o formulário fica oculto, sem mensagem técnica. Estrelas, cuidados e links continuam funcionando.

### Modo_Prototipo e Modo_API
- **Modo_Prototipo (padrão):** `API_FEEDBACK_URL` vazia (ou inválida). Nenhuma requisição de rede. O payload é gravado no `localStorage`, chave **`tres-autoatendimento-feedbacks`**, com **no máximo 50 registros** (o mais antigo sai). Se a mesma `chaveIdempotencia` já estiver gravada, devolve sucesso sem gravar de novo. Falha de leitura ou gravação vira a categoria `armazenamento`, sem apagar o que existia. A leitura dos comentários, nesse modo, é direto no `localStorage`; não há painel.
- **Modo_API:** basta preencher `API_FEEDBACK_URL` com uma URL válida. Um único `POST` JSON (`Content-Type: application/json`), com `AbortController` e `TIMEOUT_FEEDBACK_MS`, `credentials: 'omit'`, `cache: 'no-store'`, `referrerPolicy: 'no-referrer'`. **Qualquer 2xx é sucesso**, com ou sem corpo (o corpo nunca é lido). Fora de 2xx vira `http` (só o número do status); falha de rede, `rede`; tempo estourado, `timeout`. Sem retentativa automática e sem gravar no repositório local.
- Só `API_FEEDBACK_URL` decide o modo. **Com `API_CHAMADOS_URL` preenchida e `API_FEEDBACK_URL` vazia, o feedback segue em Modo_Prototipo** e nada vai ao endpoint de chamados.
- **Payload provisório (versão `"1"`), exatamente 7 campos:** `versaoContrato`, `chaveIdempotencia` (UUID v4), `enviadoEm` (ISO 8601 com fuso), `comentario` (sem espaços nas pontas), `nota` (1 a 5 ou `null`), `problemaId`, `modelo` (id escolhido ou `null`). Qualquer outro campo recebido é ignorado.
- **Idempotência:** a chave é criada no primeiro envio válido e **reutilizada** nas retentativas depois de uma falha. Não há cabeçalho `Idempotency-Key`; a chave só vai no corpo.
- As URLs `API_FEEDBACK_URL` e `API_CHAMADOS_URL` **devem continuar vazias** no repositório e na entrega do protótipo.

### Métricas (sem texto)
- Cada envio bem-sucedido grava **um** evento `comentario` em `tres-autoatendimento-eventos`, só com `tipo`, `em`, `problema` e `modelo` (`'nao-informado'` sem modelo). **Sem texto, sem nota, sem tamanho e sem chave de idempotência.** Falha de gravação da métrica não altera a tela.
- `TRESMetricas.resumo()` ganhou **`comentarios`** (contagem de eventos `comentario`, 0 se não houver). `resolvidos`, `encaminhadosAoSuporte`, `deflexaoPercentual`, `porProblema` e `chamadosAbertos` continuam calculados como antes: eventos `comentario` não entram neles. A deflexão não muda.
- O evento `avaliacao` **não ganha** nenhuma indicação de comentário. Enviar o comentário não grava `avaliacao`; escolher estrela continua gravando `avaliacao` com `desfecho: 'resolvido'`. `comentario`, `texto` e `feedback` entraram na lista de chaves proibidas em `extras` dos eventos (`CHAVES_EXTRAS_PROIBIDAS` no `app.js`).

### Regras do comportamento
- **Um comentário por jornada.** Depois do sucesso, campo e botão ficam desabilitados com o texto enviado visível, e o agradecimento aparece (foco nele). O estado "já enviado" fica só em memória: voltar a `#/resolvido/ID` na mesma jornada mostra "já enviado"; escolher um problema (`cartaoProblema`) ou recarregar a página zera tudo; sair sem enviar e voltar mostra o campo vazio.
- **Nota independente.** A nota escolhida na mesma exibição da tela acompanha o comentário (`nota: 1..5`); sem nota, vai `null`. Estrelas são remontadas neutras a cada exibição, então a nota em memória é zerada a cada exibição. Estrela tocada depois do envio grava `avaliacao` normalmente e não altera o feedback já enviado. Falha de um envio não desfaz o outro.
- **Sem identificação.** Nenhum campo de nome, e-mail, telefone, aceite ou "Ler os termos". Valores do formulário do chamado nunca entram no feedback. O sistema **não detecta nem apaga** dados pessoais digitados no texto livre; a prevenção é só o aviso visível, associado ao campo por `aria-describedby`.
- **Sem aviso de protótipo.** O agradecimento é o mesmo texto de `data.js` nos dois modos (decisão do usuário).
- **Validação:** comentário vazio ou só espaços e quebras de linha: nada é gravado nem enviado, aparece a mensagem sob o campo (`aria-invalid="true"`), o foco vai ao campo e a frase de `anuncioErroVazio` é anunciada. Editar remove o erro. Enter no `textarea` só insere quebra de linha. O texto passa de 500: é truncado em 500, digitado ou colado.
- **Falha de envio:** bloco `role="alert"` (`.msg-falha`) com o texto de `falha`, foco nele, campo e botão reabilitados, texto e chave preservados, nenhum evento, nenhum agradecimento. A nova tentativa reaproveita a mesma chave.
- **Duplo toque:** o estado muda para `enviando` antes de qualquer espera, então dois cliques geram no máximo um registro (Modo_Prototipo) ou uma requisição (Modo_API).
- **Texto sempre literal:** o comentário entra na página só por `value` ou `textContent`; nenhum `innerHTML` com dado do consumidor. O texto não vai para console, URL, cookies, `sessionStorage`, `tres-autoatendimento-eventos` nem `tres-autoatendimento-chamados`. Só existe em `tres-autoatendimento-feedbacks` (Modo_Prototipo) ou no corpo da requisição (Modo_API).
- **Foco no `h1` (exceção nova):** na primeira rota, o `mostrarView` já não movia o foco, exceto em `suporte` e `chamado`; agora `resolvido` também está na exceção. Abertura direta da URL, resposta "Sim", voltar e avançar levam o foco ao `h1` (nunca ao campo).
- **Sair da rota durante o envio:** o resultado atualiza `state.feedback` só se a chave ainda for a da tentativa, grava a métrica no sucesso e só mexe na tela se a rota ainda for `resolvido`.

### Mudança deliberada em requisito anterior
A spec `ticket-opening-screen` (requisito 12.1) exigia a Tela_de_Resolvido **idêntica** à da versão anterior. Esta funcionalidade muda isso de propósito: a tela ganha o bloco de comentário e o foco no `h1` na abertura direta. Os testes que fixavam a tela idêntica foram atualizados (ver abaixo). Cabeçalho, rodapé, barra de etapas (3 itens, etapa 3) e as demais rotas seguem sem mudança.

### Testes
- **Núcleo (Node, `fast-check` 4.10.2), arquivos novos em `tests/nucleo/`:** `feedback-texto.test.js` (normalização, validação, limite e contador, conteúdo indisponível), `feedback-payload.test.js` (conteúdo e ida e volta do payload, chave de idempotência), `feedback-repositorio.test.js` (ida e volta, leitura tolerante, limite de 50, idempotência por chave, armazenamento isolado, falha sem rastro), `feedback-envio.test.js` (modo e destino, requisição em Modo_API, classificação do resultado), `feedback-estado.test.js` (máquina de estados e reinício por jornada), `feedback-metricas.test.js` (evento sem texto e `resumo()` com `comentarios`) e `feedback-exemplos.test.js` (exemplos e bordas). Geradores novos no fim de `tests/geradores.js`.
- **Interface (Edge por CDP), cenários novos em `tests/ui/cenarios/`:** `24-comentario-resolvido.test.js` (Modo_Prototipo: fluxos, validação, contador, falha, estrutura, conteúdo indisponível) e `25-comentario-api.test.js` (Modo_API: sucesso, erro 500, rede, tempo limite, mesma chave na nova tentativa, destino independente do chamado). Para isso, `tests/ui/cenarios.js` e `tests/ui/servidor-teste.js` ganharam `modoApiFeedback`, `apiFeedback`, `semTextosFeedback`, `configNumerica` com `TIMEOUT_FEEDBACK_MS`, a rota falsa `POST api/feedbacks` e `ctx.feedbacksLocais()`.
- **O que mudou nos testes existentes:** `tests/nucleo/textos-metricas.test.js` (formato de `resumirEventos` com `comentarios`), `tests/smoke.test.js` (carrega `feedback.js` e confere a API pública), `tests/dados.test.js` (`FEEDBACK`: URLs vazias, chaves, aviso de 1 a 200 caracteres, marcação `PENDENTE`/`ILUSTRATIVO`, `CHAMADO` intacto), `tests/estatico.js` e `tests/estatico.test.js` (`feedback.js` entra nas checagens de sem `console.*`, sem HTML dinâmico, núcleo puro e sem `require(`; textos só de `data.js`; pares de contraste novos), e os cenários de UI `15-modo-api`, `16-duplo-toque`, `17-navegacao`, `18-estrelas`, `19-texto-literal`, `20-responsivo`, `21-movimento-reduzido`, `22-regressao-rotas` (ordem estrelas, formulário, cuidados, links; `resumo()` com `comentarios: 0`; foco no `h1` na abertura direta) e `23-dados-pessoais` (nova chave e chaves proibidas). `tests/ui/roteiro-manual.md` ganhou a seção 8 do comentário.
- **Como rodar** (a lista de arquivos vem do `package.json` de `tests/`): `npm test` dentro de `tests/`; `node tests/ui/rodar.js` **em série**, uma execução por vez (ele encerra os Edge de teste e uma segunda execução mata a primeira); para paralelo, `node --test` direto nos arquivos de `tests/ui/cenarios/`; `node tests/verificar-protegidos.js --conferir` para os arquivos protegidos (não usar `--gerar`; a linha de base já existe).
- Não rodei a suíte ao escrever esta seção; o que está aqui vem da leitura dos arquivos. Rode `npm test` e a suíte de UI antes de afirmar que passam.

### Lições desta funcionalidade
- **Botão desabilitado e contraste:** a regra global `.btn[disabled]` aplica `opacity: 0.45`, o que derruba o contraste do texto, e "Enviando" e o botão travado depois do envio carregam informação. Por isso o bloco novo tem `.feedback .btn[disabled]` com `opacity: 1`, texto `--texto` sobre `--campo-fundo-desabilitado` e borda própria, **sem editar a regra global**. O mesmo vale para o `textarea` travado (`:disabled` e `[readonly]`, com `-webkit-text-fill-color`). O teste de contraste cobre os pares novos (texto sobre `--campo-fundo-desabilitado` e sobre `--sucesso-fundo`, mínimo de 4,5:1).
- **CSS dos links de `.cuidados`:** a regra `.cuidados p a { display: inline-flex; align-items: center; min-height: var(--alvo-minimo); overflow-wrap: anywhere; }` garante alvo de **44 px** nos links de texto dentro de "Cuidados com a sua máquina" (guia rápido em PDF e "Escolha o seu modelo"). O cenário `20-responsivo` mede todos os alvos de toque de `#view-resolvido` e exige 44 px, então esses links entraram na conta. Como `.cuidados` também é usado na tela de problemas (`#cuidados-problema`), **a regra vale lá também**: ao mexer nela, conferir as duas telas. `inline-flex` mantém o link na linha e deixa quebrar em 360 px.
- **Cuidado ao editar CSS existente:** a spec manda não editar nenhuma regra existente; tudo foi acrescentado depois do marcador que o teste estático usa para separar as regras novas (`INICIO_NOVO`). Manter assim.
- **Agradecimento sem `anunciar()` em paralelo:** o `#feedback-agradecimento` já é `role="status"` e recebe o foco; não se chama `anunciar()` junto para não somar uma terceira leitura. Continua valendo a lição da seção 12 sobre o Edge sem tela (cenários curtos, menos de 4 s) e sobre `rodar.js` encerrar todos os Edge de teste.

### Pendências desta funcionalidade
- **Contrato com o back end (`PENDENTE`):** URL do endpoint por ambiente, autenticação e autorização, **CORS**, esquema do banco, formato da resposta de sucesso (o cliente aceita qualquer 2xx), tratamento de **chave repetida** (mesma resposta? 409?), se a chave também vai em cabeçalho `Idempotency-Key`, limites de tamanho, **limitação de taxa** e **retenção**. O contrato da versão `"1"` segue provisório, por decisão do usuário. O endpoint, se público, recebe texto livre sem autenticação do cliente; spam e abuso precisam ser tratados no back end (o cliente só faz `maxlength`, validação e envio único por tentativa).
- **LGPD do texto livre (`PENDENTE`):** o comentário pode conter dado pessoal digitado pelo consumidor. O texto do aviso de não identificação é `ILUSTRATIVO` e depende de revisão jurídica. Também faltam base legal e finalidade, política de retenção e descarte, e quem pode ler os comentários (não há painel nem moderação). Em Modo_Prototipo o texto fica em texto puro no `localStorage` do navegador.
- **Possível leitura dupla do agradecimento:** a região `role="status"` é preenchida e recebe o foco ao mesmo tempo; alguns leitores de tela podem ler duas vezes. Se incomodar, a alternativa do design é tirar o `tabindex` e o foco e deixar só a região viva, o que exigiria mudar o requisito 7.6 (não mudar sem decisão do usuário).
- **Não foi verificado:** leitor de tela real (NVDA, VoiceOver, TalkBack), incluindo a leitura dupla; celular físico (teclado virtual, 360 px, alvos de toque, texto colado com mais de 500 caracteres); Firefox e Safari (os testes de UI rodam só no Edge); back end real em Modo_API; sensação visual do bloco. O roteiro está em `tests/ui/roteiro-manual.md`, seção 8, com os itens marcados como não verificados até alguém executá-lo.
- **Tarefas ainda abertas na spec ao escrever esta seção:** a 13 (verificação final: arquivos protegidos, revisão de console e `innerHTML`, suíte completa em série e limpeza de temporários). Esta seção não substitui essa verificação.
