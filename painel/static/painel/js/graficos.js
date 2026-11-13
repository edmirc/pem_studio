/* Gráficos de barras padronizados do painel (Chart.js) */
(function () {
  const CORES = { receita: '#2f7d6d', despesa: '#d9822b', linha: '#1c1f26' };
  const brl = v => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });

  window.graficoBarras = function (id, rotulos, series, linhaResultado) {
    const el = document.getElementById(id);
    if (!el || !window.Chart) return;
    const datasets = series.map(s => ({
      type: 'bar', label: s.label, data: s.data,
      backgroundColor: CORES[s.cor] || s.cor, borderRadius: 4, maxBarThickness: 28,
    }));
    if (linhaResultado) {
      datasets.push({ type: 'line', label: 'Resultado', data: linhaResultado, borderColor: CORES.linha,
        backgroundColor: CORES.linha, pointRadius: 3, borderWidth: 2, tension: 0.25 });
    }
    new Chart(el, {
      data: { labels: rotulos, datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: datasets.length > 1, position: 'bottom', labels: { boxWidth: 12, usePointStyle: true } },
          tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${brl(c.parsed.y)}` } },
        },
        scales: {
          x: { grid: { display: false } },
          y: { beginAtZero: true, ticks: { callback: v => brl(v) }, grid: { color: '#ecebe6' } },
        },
      },
    });
  };
})();
