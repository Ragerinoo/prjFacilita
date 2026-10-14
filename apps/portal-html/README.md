# Portal HTML do Autoatendimento TRES

Front estático (HTML, CSS e JS puros, sem build) do autoatendimento: jornada, chamado e comentário opcional.
Leia CONTEXTO-PROJETO.md. Para rodar: na pasta, `python -m http.server 8080` e abra http://localhost:8080.
Testes: `cd tests && npm install && npm test` (núcleo) e `node tests/ui/rodar.js` (Edge).
A integração com a API em apps/ e services/api esta planejada em .kiro/specs/api-integration (BASE_URL vazia = modo local).
Nao incluidos neste envio por tamanho: material/ (PDFs do hackathon), o .glb original de 48 MB e as imagens originais de img/ (o site usa img/web e modelos3d/maquina-web.glb).
