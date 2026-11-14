/* =====================================================================
   PEM Studio — CONFIGURE AQUI os seus contatos (só precisa mexer nisto)
   ===================================================================== */
const CONFIG = {
  // WhatsApp com código do país e DDD, só números. Ex.: '5565999998888'
  whatsapp: '5565992325404',
  // Usuário do Instagram, sem @. Ex.: 'pemstudio3d'
  instagram: 'pem_studio',
  // E-mail de contato
  email: 'pem.studio3d@gmail.com',
};
/* ===================================================================== */

(function () {
  const numero = CONFIG.whatsapp.replace(/\D/g, '');
  const linkWhats = texto => `https://wa.me/${numero}${texto ? '?text=' + encodeURIComponent(texto) : ''}`;

  function formatarFone(n) {
    const local = n.startsWith('55') ? n.slice(2) : n;
    if (local.length === 11) return `(${local.slice(0, 2)}) ${local.slice(2, 7)}-${local.slice(7)}`;
    if (local.length === 10) return `(${local.slice(0, 2)}) ${local.slice(2, 6)}-${local.slice(6)}`;
    return n;
  }

  // links de WhatsApp e Instagram
  document.querySelectorAll('[data-whatsapp]').forEach(a => {
    a.href = linkWhats('Olá! Vim pelo site da PEM Studio.');
    a.target = '_blank'; a.rel = 'noopener';
    if (a.hasAttribute('data-mostrar-numero') && numero) a.textContent = 'WhatsApp ' + formatarFone(numero);
  });
  document.querySelectorAll('[data-instagram]').forEach(a => {
    a.href = CONFIG.instagram ? `https://instagram.com/${CONFIG.instagram.replace('@', '')}` : 'https://instagram.com/';
    a.target = '_blank'; a.rel = 'noopener';
    if (a.hasAttribute('data-mostrar-usuario') && CONFIG.instagram) a.textContent = '@' + CONFIG.instagram.replace('@', '');
  });

  document.querySelectorAll('[data-email]').forEach(a => {
    if (!CONFIG.email) { a.closest('p').hidden = true; return; }
    a.href = 'mailto:' + CONFIG.email;
    a.textContent = CONFIG.email;
  });
  // Instagram ainda não configurado: esconde os links para não levar a uma página vazia
  if (!CONFIG.instagram) document.querySelectorAll('[data-instagram]').forEach(a => {
    (a.closest('p') && !a.classList.contains('botao') ? a.closest('p') : a).hidden = true;
  });

  // borda do topo ao rolar
  const topo = document.querySelector('.topo');
  const marcar = () => topo.classList.toggle('rolou', window.scrollY > 8);
  window.addEventListener('scroll', marcar, { passive: true }); marcar();

  // ano no rodapé
  document.getElementById('ano').textContent = new Date().getFullYear();

  // formulário de orçamento -> mensagem pronta no WhatsApp
  const form = document.getElementById('form-orcamento');
  const erro = document.getElementById('form-erro');
  form.addEventListener('submit', e => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(form));
    if (!d.nome.trim() || !d.ideia.trim()) {
      erro.textContent = 'Preencha seu nome e conte o que você quer.';
      erro.hidden = false;
      (d.nome.trim() ? form.ideia : form.nome).focus();
      return;
    }
    erro.hidden = true;
    const linhas = [
      `Olá! Sou ${d.nome.trim()} e gostaria de um orçamento.`,
      '',
      `*O que eu quero:* ${d.ideia.trim()}`,
    ];
    if (d.tamanho.trim()) linhas.push(`*Tamanho aproximado:* ${d.tamanho.trim()}`);
    if (d.quantidade && d.quantidade !== '1') linhas.push(`*Quantidade:* ${d.quantidade}`);
    if (d.data) {
      const [a, m, dia] = d.data.split('-');
      linhas.push(`*Preciso até:* ${dia}/${m}/${a}`);
    }
    linhas.push('', 'Vou mandar as fotos de referência aqui na conversa.');
    window.open(linkWhats(linhas.join('\n')), '_blank', 'noopener');
  });
})();
