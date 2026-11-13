/* Anexos: escolher, arrastar ou colar (Ctrl+V) arquivos; visualizador de fotos. */
(function () {
  // ---------- zonas de anexo ----------
  const zonas = [...document.querySelectorAll('[data-zona]')];
  const tamanho = b => b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB';

  zonas.forEach(zona => {
    const entrada = zona.querySelector('[data-entrada]');
    const alvo = zona.querySelector('[data-alvo]');
    const previas = zona.querySelector('[data-previas]');
    let arquivos = [];

    function sincronizar() {
      const dt = new DataTransfer();
      arquivos.forEach(f => dt.items.add(f));
      entrada.files = dt.files;
      previas.innerHTML = '';
      arquivos.forEach((f, i) => {
        const item = document.createElement('div');
        item.className = 'previa';
        if (f.type.startsWith('image/')) {
          const img = document.createElement('img');
          img.src = URL.createObjectURL(f);
          item.appendChild(img);
        } else {
          item.innerHTML = `<span class="etiqueta">${(f.name.split('.').pop() || '').toUpperCase()}</span>`;
        }
        const leg = document.createElement('small');
        leg.textContent = `${f.name} · ${tamanho(f.size)}`;
        const rm = document.createElement('button');
        rm.type = 'button'; rm.className = 'previa-rm'; rm.textContent = '×'; rm.title = 'Remover';
        rm.onclick = () => { arquivos.splice(i, 1); sincronizar(); };
        item.append(leg, rm);
        previas.appendChild(item);
      });
      zona.classList.toggle('com-arquivos', arquivos.length > 0);
      const form = zona.closest('form');
      if (form && form.hasAttribute('data-auto-envio')) {
        const b = form.querySelector('[data-enviar]');
        if (b) { b.hidden = !arquivos.length; b.textContent = `Enviar ${arquivos.length} arquivo${arquivos.length > 1 ? 's' : ''}`; }
      }
    }
    function adicionar(lista) {
      [...lista].forEach(f => arquivos.push(f));
      sincronizar();
    }
    zona.adicionar = adicionar;

    alvo.addEventListener('click', () => entrada.click());
    alvo.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); entrada.click(); } });
    entrada.addEventListener('change', () => {
      const novos = [...entrada.files];
      // entrada.files foi substituída pela seleção; recompõe com os anteriores
      arquivos = arquivos.concat(novos.filter(n => !arquivos.includes(n)));
      sincronizar();
    });
    ['dragenter', 'dragover'].forEach(ev => alvo.addEventListener(ev, e => { e.preventDefault(); alvo.classList.add('sobre'); }));
    ['dragleave', 'drop'].forEach(ev => alvo.addEventListener(ev, e => { e.preventDefault(); alvo.classList.remove('sobre'); }));
    alvo.addEventListener('drop', e => adicionar(e.dataTransfer.files));
    zona.addEventListener('focusin', () => { zonas.forEach(z => z.classList.remove('ativa')); zona.classList.add('ativa'); });
  });

  // colar (Ctrl+V): vai para a zona ativa, ou a primeira da página
  document.addEventListener('paste', e => {
    if (!zonas.length || !e.clipboardData) return;
    const imgs = [...e.clipboardData.items].filter(i => i.kind === 'file').map(i => i.getAsFile()).filter(Boolean);
    if (!imgs.length) return;
    e.preventDefault();
    const agora = new Date();
    const carimbo = agora.toISOString().slice(0, 19).replace(/[T:]/g, '-');
    const renomeados = imgs.map((f, i) => new File([f], f.name && f.name !== 'image.png' ? f.name : `colado-${carimbo}-${i + 1}.${(f.type.split('/')[1] || 'png')}`, { type: f.type }));
    const foco = document.activeElement && document.activeElement.closest('form');
    const zona = (foco && foco.querySelector('[data-zona]')) || document.querySelector('[data-zona].ativa') || zonas[0];
    zona.adicionar(renomeados);
    zona.scrollIntoView({ block: 'nearest' });
  });

  // ---------- visualizador de fotos ----------
  const vz = document.getElementById('visualizador');
  if (!vz) return;
  const img = vz.querySelector('img');
  let fotos = [], atual = 0;
  function mostrar(i) {
    atual = (i + fotos.length) % fotos.length;
    img.src = fotos[atual];
    vz.querySelector('.vz-baixar').href = fotos[atual] + '?baixar=1';
  }
  document.addEventListener('click', e => {
    const a = e.target.closest('[data-foto]');
    if (!a) return;
    e.preventDefault();
    const gal = a.closest('[data-galeria]');
    fotos = [...gal.querySelectorAll('[data-foto]')].map(x => x.getAttribute('href'));
    mostrar(fotos.indexOf(a.getAttribute('href')));
    vz.showModal();
  });
  vz.querySelector('.vz-fechar').onclick = () => vz.close();
  vz.querySelector('.vz-ant').onclick = () => mostrar(atual - 1);
  vz.querySelector('.vz-prox').onclick = () => mostrar(atual + 1);
  vz.addEventListener('click', e => { if (e.target === vz) vz.close(); });
  document.addEventListener('keydown', e => {
    if (!vz.open) return;
    if (e.key === 'ArrowLeft') mostrar(atual - 1);
    if (e.key === 'ArrowRight') mostrar(atual + 1);
  });
})();
