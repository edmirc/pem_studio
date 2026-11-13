/*
 * Calculadora de precificação de peças impressas.
 * Uso:  const calc = new Calculadora(elementoRaiz, dados);  calc.resultado()
 * O HTML vem de encomendas/parciais/calculadora.html.
 */
(function () {
  const brl = v => ((Number.isFinite(v) ? v : 0) + 0 || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  const num = v => { const n = parseFloat(String(v ?? '').replace(',', '.')); return Number.isFinite(n) ? n : 0; };
  const r2 = v => Math.round(v * 100) / 100;

  class Calculadora {
    constructor(raiz, dados) {
      this.raiz = raiz;
      this.d = dados;
      this.$ = sel => raiz.querySelector(sel);
      this.montar();
      raiz.addEventListener('input', () => this.atualizar());
      raiz.addEventListener('change', () => this.atualizar());
      this.limpar();
    }

    montar() {
      const imp = this.$('[data-c=impressora]');
      imp.innerHTML = this.d.impressoras.map(i =>
        `<option value="${i.id}">${i.nome} — R$ ${i.custo_hora.toFixed(2).replace('.', ',')}/h</option>`).join('');
      const fil = this.$('[data-c=filamento]');
      fil.innerHTML = `<option value="">Custo médio das compras (R$ ${this.d.config.custo_kg_medio.toFixed(2).replace('.', ',')}/kg)</option>` +
        this.d.filamentos.map(f => `<option value="${f.id}">${f.nome}${f.custo_kg ? ' — R$ ' + f.custo_kg.toFixed(2).replace('.', ',') + '/kg' : ''}</option>`).join('') +
        '<option value="manual">Digitar o preço por kg…</option>';
      this.$('[data-c=add-insumo]').addEventListener('click', () => { this.addInsumo(); this.atualizar(); });
      this.$('[data-c=lista-insumos]').addEventListener('click', e => {
        if (e.target.closest('[data-c=rm-insumo]')) { e.target.closest('.linha-insumo').remove(); this.atualizar(); }
      });
      this.$('[data-c=lista-insumos]').addEventListener('change', e => {
        const sel = e.target.closest('select');
        if (!sel) return;
        const ins = this.d.insumos.find(i => String(i.id) === sel.value);
        const custo = sel.closest('.linha-insumo').querySelector('[data-i=custo]');
        if (ins && ins.custo != null) custo.value = ins.custo.toFixed(2);
      });
      fil.addEventListener('change', () => {
        const manual = fil.value === 'manual';
        this.$('[data-c=grupo-kg]').hidden = !manual;
        if (manual) this.$('[data-c=custo_kg]').focus();
      });
    }

    addInsumo(dados) {
      const opts = '<option value="">Escolha…</option>' + this.d.insumos.map(i =>
        `<option value="${i.id}">${i.nome}${i.custo != null ? ' (R$ ' + i.custo.toFixed(2).replace('.', ',') + '/' + i.unidade.toLowerCase() + ')' : ''}</option>`).join('');
      const div = document.createElement('div');
      div.className = 'linha-insumo';
      div.innerHTML = `<select class="campo" data-i="id">${opts}</select>
        <input class="campo" type="number" step="0.01" min="0" data-i="qnt" value="1" title="Quantidade por peça" inputmode="decimal">
        <input class="campo" type="number" step="0.01" min="0" data-i="custo" placeholder="R$ unit." title="Custo unitário" inputmode="decimal">
        <button type="button" class="botao icone" data-c="rm-insumo" title="Remover">×</button>`;
      this.$('[data-c=lista-insumos]').appendChild(div);
      if (dados) {
        div.querySelector('[data-i=id]').value = dados.id || '';
        div.querySelector('[data-i=qnt]').value = dados.qnt;
        div.querySelector('[data-i=custo]').value = dados.custo;
      }
    }

    v(nome) { return this.$(`[data-c=${nome}]`).value; }
    set(nome, valor) { const el = this.$(`[data-c=${nome}]`); if (el && valor !== undefined && valor !== null) el.value = valor; }

    limpar() {
      this.set('nome', ''); this.set('pecas', 1); this.set('horas', ''); this.set('minutos', '');
      this.set('gramas', ''); this.set('acabamento', 0); this.set('outros', 0);
      this.set('lucro', this.d.config.lucro_padrao); this.set('arred', '1');
      this.set('filamento', ''); this.$('[data-c=grupo-kg]').hidden = true;
      this.$('[data-c=lista-insumos]').innerHTML = '';
      this.atualizar();
    }

    carregar(c) {
      if (!c) return this.limpar();
      this.limpar();
      ['nome', 'pecas', 'horas', 'minutos', 'gramas', 'acabamento', 'outros', 'lucro', 'arred'].forEach(k => this.set(k, c[k]));
      if (c.impressora_id) this.set('impressora', c.impressora_id);
      this.set('filamento', c.filamento_id ?? '');
      if (c.filamento_id === 'manual') { this.$('[data-c=grupo-kg]').hidden = false; this.set('custo_kg', c.custo_kg); }
      (c.insumos || []).forEach(i => this.addInsumo(i));
      this.atualizar();
    }

    resultado() {
      const cfg = this.d.config;
      const pecas = Math.max(1, Math.round(num(this.v('pecas'))) || 1);
      const horas = num(this.v('horas')) + num(this.v('minutos')) / 60;
      const imp = this.d.impressoras.find(i => String(i.id) === this.v('impressora')) || { custo_hora: 2, watts: 0, nome: '' };
      const filSel = this.v('filamento');
      let custoKg = cfg.custo_kg_medio;
      if (filSel === 'manual') custoKg = num(this.v('custo_kg'));
      else if (filSel) { const f = this.d.filamentos.find(x => String(x.id) === filSel); if (f && f.custo_kg) custoKg = f.custo_kg; }
      const gramas = num(this.v('gramas'));

      // custos da mesa inteira -> por peça
      const maquina = horas * imp.custo_hora / pecas;
      const energia = horas * imp.watts / 1000 * cfg.preco_kwh / pecas;
      const filamento = gramas / 1000 * custoKg / pecas;
      const falha = (maquina + filamento) * cfg.taxa_falha / 100;
      const mao = num(this.v('acabamento')) / 60 * cfg.valor_hora_trabalho;
      const insumosLista = [...this.raiz.querySelectorAll('.linha-insumo')].map(l => {
        const sel = l.querySelector('[data-i=id]');
        return { id: sel.value ? Number(sel.value) : null, nome: sel.value ? sel.selectedOptions[0].textContent.replace(/ \(R\$.*$/, '') : '',
                 qnt: num(l.querySelector('[data-i=qnt]').value), custo: num(l.querySelector('[data-i=custo]').value) };
      }).filter(i => i.qnt && (i.id || i.custo));
      const insumos = insumosLista.reduce((s, i) => s + i.qnt * i.custo, 0);
      const outros = num(this.v('outros'));
      const custo = maquina + filamento + falha + mao + insumos + outros;
      const lucroPct = num(this.v('lucro'));
      const arred = num(this.v('arred'));
      let preco = custo * (1 + lucroPct / 100);
      if (arred > 0) preco = Math.ceil(preco / arred - 1e-9) * arred;
      preco = Math.max(0, r2(preco)) || 0;

      return {
        nome: this.v('nome').trim(), pecas, horas: this.v('horas'), minutos: this.v('minutos'),
        impressora_id: imp.id || null, impressora: imp.nome, filamento_id: filSel || null,
        custo_kg: r2(custoKg), gramas, acabamento: num(this.v('acabamento')), insumos: insumosLista,
        outros, lucro: lucroPct, arred: this.v('arred'), horas_peca: r2(horas / pecas),
        partes: { maquina: r2(maquina), energia: r2(energia), filamento: r2(filamento), falha: r2(falha),
                  mao: r2(mao), insumos: r2(insumos), outros: r2(outros) },
        custo_peca: r2(custo), preco_peca: preco,
        lucro_valor: r2(preco - custo), margem: preco ? Math.round((preco - custo) * 100 / preco) : 0,
      };
    }

    atualizar() {
      const r = this.resultado();
      const out = (k, v) => { const el = this.$(`[data-r=${k}]`); if (el) el.textContent = v; };
      Object.entries(r.partes).forEach(([k, v]) => out(k, brl(v)));
      out('custo', brl(r.custo_peca)); out('preco', brl(r.preco_peca));
      out('lucro', `${brl(r.lucro_valor)} (${r.margem}% do preço)`);
      out('pecas', r.pecas > 1 ? `por peça · mesa com ${r.pecas} peças` : 'por peça');
      const tab = this.$('[data-r=cartao]');
      if (tab) {
        const linhas = [{ nome: 'Pix / dinheiro', parcelas: 1, taxa: 0 }, ...this.d.config.taxas];
        tab.innerHTML = linhas.map(t => {
          const total = r2(r.preco_peca / (1 - t.taxa / 100));
          const parc = t.parcelas > 1 ? `<small>${t.parcelas}× ${brl(r2(total / t.parcelas))}</small>` : '';
          return `<tr><td>${t.nome}</td><td class="num">${brl(total)} ${parc}</td></tr>`;
        }).join('');
      }
      this.raiz.dispatchEvent(new CustomEvent('calc:atualizado', { detail: r }));
    }
  }
  window.Calculadora = Calculadora;
})();
