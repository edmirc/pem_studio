/* Tela "Nova impressão": escolhe a peça, usa a calculadora e manda para a fila. */
(function () {
  const $ = id => document.getElementById(id);
  const ler = id => JSON.parse($(id).textContent);
  const brl = v => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  const info = ler('info-produtos'), itens = ler('info-itens'), ocupadas = ler('ocupadas'), fatiadorDe = ler('fatiador-impressora');
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function htmlArquivo(a) {
    if (!a) return '';
    const sel = raiz.querySelector('[data-c=impressora]');
    const pref = fatiadorDe[sel.value] || 'creality';
    const fat = a.fatiadores.slice().sort((x, y) => (x.chave !== pref) - (y.chave !== pref));
    const bot = fat.map((f, i) => `<a class="botao${i ? '' : ' primario'}" href="${esc(f.url)}">Abrir no ${esc(f.nome)}</a>`).join('');
    return `<div class="info-arquivo"><code>${esc(a.caminho)}</code><span>${bot}<a class="botao" href="${esc(a.pasta)}">Abrir a pasta</a></span></div>`;
  }
  const raiz = document.getElementById('calc');
  const calc = new Calculadora(raiz, ler('dados-calc'));
  const form = $('form-nova'), modo = $('modo');
  const selProd = $('f-produto'), selItem = $('f-item');
  let mexeu = false;  // o usuário já digitou na calculadora?
  raiz.addEventListener('input', () => { mexeu = true; });

  const inicial = ler('calc-inicial');
  if (inicial) calc.carregar(inicial);

  function trocarModo(m) {
    modo.value = m;
    document.querySelectorAll('[data-modo]').forEach(b => b.classList.toggle('ativo', b.dataset.modo === m));
    document.querySelectorAll('[data-painel]').forEach(p => { p.hidden = p.dataset.painel !== m; });
    if (m === 'novo') $('f-novo').focus();
    atualizarInfo();
  }
  document.querySelectorAll('[data-modo]').forEach(b => b.addEventListener('click', () => trocarModo(b.dataset.modo)));

  function produtoAtual() {
    if (modo.value === 'catalogo') return info[selProd.value] ? selProd.value : '';
    if (modo.value === 'encomenda') { const it = itens[selItem.value]; return it && it.produto ? String(it.produto) : ''; }
    return '';
  }

  function atualizarInfo() {
    const el = $('info-produto'), pid = produtoAtual(), p = info[pid];
    const linhaPreco = $('linha-preco'), chkPreco = $('f-preco');
    if (modo.value === 'novo') {
      el.hidden = false;
      el.textContent = 'O produto será cadastrado ao mandar para a fila. Quando a peça ficar pronta, ela entra no estoque.';
      linhaPreco.hidden = false;
    } else if (p) {
      el.hidden = false;
      el.innerHTML = (p.mini ? `<img class="info-foto" src="${esc(p.mini)}" alt="">` : '') + '<div>' +
        `Em estoque: <b>${p.estoque}</b> · ` + (p.venda ? `preço de venda atual <b>${brl(p.venda)}</b>${p.custo ? ` (custo ${brl(p.custo)})` : ''}` : 'ainda sem preço cadastrado') +
        htmlArquivo(p.arquivo) + '</div>';
      linhaPreco.hidden = false;
      if (!chkPreco.dataset.mexeu) chkPreco.checked = !p.venda;
    } else if (modo.value === 'encomenda' && itens[selItem.value]) {
      el.hidden = false;
      el.textContent = 'Peça personalizada: vai para o pedido, não para o estoque.';
      linhaPreco.hidden = true; chkPreco.checked = false;
    } else {
      el.hidden = true; linhaPreco.hidden = !pid;
    }
    resumo();
  }
  $('f-preco').addEventListener('change', e => { e.target.dataset.mexeu = '1'; });

  selProd.addEventListener('change', () => {
    const p = info[selProd.value];
    if (p) {
      if (p.calculo && (!mexeu || confirm('Carregar os números da última impressão deste produto?'))) { calc.carregar(p.calculo); mexeu = false; }
      calc.set('nome', p.nome); calc.atualizar();
    }
    atualizarInfo();
  });
  selItem.addEventListener('change', () => {
    const it = itens[selItem.value];
    if (it) {
      if (it.calculo) calc.carregar(it.calculo);
      calc.set('nome', it.nome);
      if (it.falta) calc.set('pecas', it.falta);
      calc.atualizar(); mexeu = false;
    }
    atualizarInfo();
  });

  function resumo() {
    const r = calc.resultado();
    const mesas = Math.max(1, parseInt($('f-mesas').value, 10) || 1);
    const sel = raiz.querySelector('[data-c=impressora]');
    const nomeImp = sel.selectedOptions[0] ? sel.selectedOptions[0].textContent.split(' — ')[0] : 'impressora escolhida';
    $('nome-impressora').textContent = nomeImp;
    const ocup = ocupadas[sel.value];
    const aviso = $('aviso-ocupada');
    aviso.hidden = !(ocup && $('f-comecar').checked);
    aviso.textContent = ocup ? `A ${nomeImp} está imprimindo ${ocup}. A impressão vai ficar na fila esperando.` : '';
    const horas = (parseFloat(r.horas) || 0) + (parseFloat(r.minutos) || 0) / 60;
    let t = `Vai gerar ${r.pecas * mesas} peça${r.pecas * mesas > 1 ? 's' : ''}`;
    if (mesas > 1) t += ` em ${mesas} impressões de ${r.pecas}`;
    if (horas) {
      const fim = new Date(Date.now() + horas * 3600e3);
      t += ` · ${Math.floor(horas)}h${String(Math.round((horas % 1) * 60)).padStart(2, '0')} de máquina por mesa`;
      if ($('f-comecar').checked && !ocup) t += ` · termina por volta das ${fim.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`;
    }
    if (r.preco_peca) t += ` · preço sugerido ${brl(r.preco_peca)} por peça`;
    $('resumo-envio').textContent = t + '.';
    $('b-enviar').textContent = $('f-comecar').checked && !ocup ? 'Começar a imprimir' : 'Mandar para a fila';
  }
  raiz.addEventListener('calc:atualizado', resumo);
  raiz.querySelector('[data-c=impressora]').addEventListener('change', atualizarInfo);
  ['f-mesas', 'f-comecar'].forEach(id => $(id).addEventListener('input', resumo));
  $('f-comecar').addEventListener('change', resumo);

  form.addEventListener('submit', e => {
    const m = modo.value;
    if (m === 'catalogo' && !selProd.value) { e.preventDefault(); alert('Escolha o produto.'); return; }
    if (m === 'novo' && (!$('f-novo').value.trim() || !$('f-cat').value)) { e.preventDefault(); alert('Digite o nome e escolha a categoria do produto novo.'); return; }
    if (m === 'encomenda' && !selItem.value) { e.preventDefault(); alert('Escolha o item do pedido.'); return; }
    // só vai o campo do modo escolhido
    if (m !== 'catalogo') selProd.value = '';
    if (m !== 'encomenda') selItem.value = '';
    form.calculo.value = JSON.stringify(calc.resultado());
  });

  trocarModo(modo.value);
  if (!inicial && produtoAtual()) selProd.dispatchEvent(new Event('change'));
  else if (inicial && !raiz.querySelector('[data-c=nome]').value && info[produtoAtual()]) calc.set('nome', info[produtoAtual()].nome);
  calc.atualizar();
})();
