# Site da PEM Studio

Site estático (HTML, CSS e JS): roda em qualquer hospedagem, inclusive a compartilhada da Hostinger.

## 1. Antes de publicar: seus contatos

Abra `js/site.js` e preencha no topo:

```js
const CONFIG = {
  whatsapp: '5565999998888',   // com 55 + DDD, só números
  instagram: 'seuusuario',     // sem @
};
```

Todos os botões de WhatsApp, o formulário de orçamento e o rodapé usam esses dados.

## 2. Publicar na Hostinger

**Hospedagem compartilhada (hPanel):** Arquivos → Gerenciador de arquivos → pasta `public_html`
do seu domínio → envie **o conteúdo** desta pasta (`index.html`, `css`, `js`, `img`, `fonts`).
Não envie este LEIA-ME.

**VPS:** copie a pasta para o servidor (ex.: `/var/www/pemstudio`) e aponte o nginx ou o Caddy para ela.

## 3. Arquivos

- `index.html` — textos do site
- `css/estilo.css` — cores e visual (as cores da marca estão no topo do arquivo)
- `img/logo.svg`, `img/logo-claro.svg` — logo em vetor (versão para fundo claro e escuro)
- `img/favicon.svg` — ícone da aba (os três losangos)
- `img/compartilhar.png` — imagem que aparece ao compartilhar o link no WhatsApp/Instagram
- `fonts/` — fonte Montserrat (hospedada junto, sem depender do Google)
