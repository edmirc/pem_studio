/* Montagem do kit: peças, custo, preço e quantos dá para montar. */
(function () {
  const $ = id => document.getElementById(id);
  const ler = id => JSON.parse($(id).textContent);
  const info = ler('info-pecas'), hora = parseFloat(ler('valor-hora')) || 0;
  const corpo = $('pecas'), sel = $('nova-peca');
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const brl = v => Number(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  const num = v => { let s = String(v || '').replace(/[R$\s]/g, ''); if (s.includes(',')) s = s.replace(/\./g, '').replace(',', '.'); const n = parseFloat(s); return isFinite(n) && n > 0 ? n : 0; };
  const dec = v => v.toFixed(2).replace('.', ',');

  function opcoes() {
    const usados = new Set([...corpo.querySelectorAll('input[name=peca]')].map(i => i.value));
    const grupos = {};
    Object.entries(info).forEach(([id, p]) => { if (!usados.has(id)) (grupos[p.cat] = grupos[p.cat] || []).push([id, p]); });
    sel.innerHTML = '<option value="">+ Adicionar peça…</option>' + Object.keys(grupos).sort().map(g =>
      `<optgroup label="${esc(g)}">` + grupos[g].sort((a, b) => a[1].nome.localeCompare(b[1].nome))
        .map(([id, p]) => `<option value="${id}">${esc(p.nome)}</option>`).join('') + '</optgroup>').join('');
  }

  function adicionar(id, qnt) {
    const p = info[id];
    if (!p) return;
    const tr = document.createElement('tr');
    tr.dataset.id = id;
    tr.innerHTML = `<td><input type="hidden" name="peca" value="${id}"><span class="com-foto">${p.mini ? `<img src="${esc(p.mini)}" alt="">` : '<span class="sem-foto"></span>'}<span>${esc(p.nome)}</span></span></td>
      <td class="num"><input class="campo campo-qnt" type="number" name="qnt" min="1" value="${qnt}" inputmode="numeric" aria-label="Quantidade de ${esc(p.nome)}"></td>
      <td class="num c-custo"></td><td class="num c-venda"></td><td class="num c-disp"></td>
      <td class="acoes-linha"><button type="button" class="link pequeno perigo" aria-label="Tirar ${esc(p.nome)} do kit">Tirar</button></td>`;
    tr.querySelector('button').addEventListener('click', () => { tr.remove(); opcoes(); calcular(); });
    tr.querySelector('input[name=qnt]').addEventListener('input', calcular);
    corpo.appendChild(tr);
  }

  function calcular() {
    let custoPecas = 0, avulso = 0, semCusto = [], semPreco = 0, montar = Infinity, limite = '';
    corpo.querySelectorAll('tr').forEach(tr => {
      const p = info[tr.dataset.id], q = Math.max(1, parseInt(tr.querySelector('[name=qnt]').value, 10) || 1);
      if (p.custo !== null) custoPecas += parseFloat(p.custo) * q; else semCusto.push(p.nome);
      if (p.venda !== null) avulso += parseFloat(p.venda) * q; else semPreco++;
      tr.querySelector('.c-custo').textContent = p.custo !== null ? brl(parseFloat(p.custo) * q) : 'sem custo';
      tr.querySelector('.c-custo').classList.toggle('negativo', p.custo === null);
      tr.querySelector('.c-venda').textContent = p.venda !== null ? brl(parseFloat(p.venda) * q) : '—';
      const d = tr.querySelector('.c-disp'); d.textContent = p.disp; d.classList.toggle('negativo', p.disp < q);
      const k = Math.max(0, Math.floor(p.disp / q));
      if (k < montar) { montar = k; limite = p.nome; }
    });
    const vazio = !corpo.children.length;
    const emb = num($('f-emb').value) + num($('f-outros').value);
    const mao = (parseInt($('f-min').value, 10) || 0) / 60 * hora;
    const custo = custoPecas + emb + mao;
    $('r-pecas').textContent = brl(custoPecas); $('r-mao').textContent = brl(mao);
    $('r-emb').textContent = brl(emb); $('r-custo').textContent = brl(custo);
    $('r-avulso').textContent = avulso ? brl(avulso) + (semPreco ? ' *' : '') : '—';
    const aviso = $('r-sem-custo');
    aviso.hidden = !semCusto.length;
    aviso.textContent = semCusto.length ? `Sem precificação: ${semCusto.join(', ')}. O custo do kit está incompleto.` : '';

    // atalhos de preço
    const sugestoes = [];
    if (avulso) {
      sugestoes.push(['Igual às avulsas', avulso]);
      sugestoes.push(['10% mais barato', Math.round(avulso * 0.9)]);
      sugestoes.push(['15% mais barato', Math.round(avulso * 0.85)]);
    }
    if (custo) sugestoes.push(['Dobro do custo', Math.ceil(custo * 2)]);
    $('atalhos').innerHTML = sugestoes.map(([n, v]) => `<button type="button" class="chip" data-v="${v.toFixed(2)}">${n} · ${brl(v)}</button>`).join('');

    const preco = num($('f-preco').value);
    const res = $('r-resultado');
    if (preco && custo) {
      const lucro = preco - custo;
      let t = `<b class="${lucro < 0 ? 'negativo' : 'positivo'}">Lucro ${brl(lucro)} por kit</b> (${Math.round(lucro / custo * 100)}% sobre o custo)`;
      if (avulso) {
        const dif = Math.round((1 - preco / avulso) * 100);
        t += dif > 0 ? `<br>${dif}% mais barato que comprar as peças separadas` : dif < 0 ? `<br>${-dif}% mais caro que as peças separadas` : '<br>mesmo preço das peças separadas';
      }
      res.innerHTML = t;
    } else res.textContent = vazio ? 'Adicione as peças para calcular.' : '';
    $('r-montar').innerHTML = vazio ? '' : montar > 0
      ? `Com o estoque de hoje dá para montar <b>${montar} kit${montar > 1 ? 's' : ''}</b>${corpo.children.length > 1 ? ` (limitado por ${esc(limite)})` : ''}.`
      : `<span class="negativo">Sem estoque para montar: falta ${esc(limite)}.</span>`;
  }

  $('atalhos').addEventListener('click', e => {
    const b = e.target.closest('[data-v]');
    if (b) { $('f-preco').value = dec(parseFloat(b.dataset.v)); calcular(); }
  });
  sel.addEventListener('change', () => { if (sel.value) { adicionar(sel.value, 1); opcoes(); calcular(); } });
  ['f-emb', 'f-outros', 'f-min', 'f-preco'].forEach(id => $(id).addEventListener('input', calcular));

  // valores que vêm do servidor com ponto viram vírgula
  ['f-emb', 'f-outros', 'f-preco'].forEach(id => { const n = num($(id).value); $(id).value = n ? dec(n) : ''; });
  ler('linhas-kit').forEach(l => adicionar(String(l.peca), l.qnt));
  opcoes(); calcular();

  // foto: escolher, colar ou arrastar
  const input = $('f-foto'), previa = $('previa'), caixa = $('caixa-foto');
  function mostrar(f) {
    if (!f || !f.type.startsWith('image/')) return;
    previa.src = URL.createObjectURL(f); previa.hidden = false; caixa.classList.add('tem-foto');
    caixa.querySelector('.cf-texto').firstChild.textContent = 'Trocar a foto';
  }
  function usar(f) { const dt = new DataTransfer(); dt.items.add(f); input.files = dt.files; mostrar(f); }
  input.addEventListener('change', () => mostrar(input.files[0]));
  document.addEventListener('paste', e => {
    const it = [...((e.clipboardData || {}).items || [])].find(i => i.type.startsWith('image/'));
    if (!it) return;
    e.preventDefault();
    const f = it.getAsFile();
    usar(new File([f], 'colada.' + (f.type.split('/')[1] || 'png'), { type: f.type }));
  });
  ['dragover', 'drop'].forEach(ev => caixa.addEventListener(ev, e => {
    e.preventDefault();
    if (ev === 'drop' && e.dataTransfer.files[0]) usar(e.dataTransfer.files[0]);
  }));
})();
