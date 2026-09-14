(() => {
  const key = 'procureai-theme';
  let preference;
  try { preference = localStorage.getItem(key); } catch (_) {}
  let theme = preference === 'dark' || preference === 'light' ? preference :
    (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  const originals = new WeakMap();
  const brand = value => typeof value === 'string' &&
    (/^#(7354d8|8b6ce8|5d43b3|ded3ff|c6b5ff|a98df5|a78bfa|8b5cf6|7c3aed)$/i.test(value) || /rgba\(139,108,232/.test(value));
  const recolor = value => Array.isArray(value) ? value.map(recolor) :
    brand(value) ? (value.startsWith('rgba') ? 'rgba(194,138,82,.10)' : '#c28a52') : value;
  function chart(plot) {
    if (!window.Plotly || !plot.data || !plot.layout) return;
    if (!originals.has(plot)) originals.set(plot, plot.data.map(t => ({
      line: t.line?.color, marker: t.marker?.color, fill: t.fillcolor,
    })));
    const dark = theme === 'dark';
    const text = dark ? '#c1b8b0' : '#5f596a';
    const muted = dark ? '#a99f96' : '#746d80';
    const grid = dark ? 'rgba(194,138,82,.10)' : 'rgba(222,211,255,.55)';
    const update = {
      'paper_bgcolor': 'rgba(0,0,0,0)', 'plot_bgcolor': 'rgba(0,0,0,0)',
      'font.color': text, 'legend.font.color': text,
      'hoverlabel.bgcolor': dark ? '#29221d' : '#ffffff',
      'hoverlabel.bordercolor': dark ? '#44382f' : '#ded3ff',
      'hoverlabel.font.color': dark ? '#f4efea' : '#25232a',
    };
    Object.keys(plot.layout).filter(k => /^([xy]axis\d*)$/.test(k)).forEach(axis => {
      update[axis + '.tickfont.color'] = muted;
      update[axis + '.title.font.color'] = text;
      update[axis + '.gridcolor'] = grid;
      update[axis + '.linecolor'] = dark ? '#44382f' : '#ded3ef';
    });
    window.Plotly.relayout(plot, update);
    originals.get(plot).forEach((o, index) => {
      const patch = {'textfont.color': dark ? '#e3d9cf' : '#4f485a'};
      if (o.line != null) patch['line.color'] = dark ? recolor(o.line) : o.line;
      if (o.marker != null) patch['marker.color'] = [dark ? recolor(o.marker) : o.marker];
      if (o.fill != null) patch.fillcolor = dark ? recolor(o.fill) : o.fill;
      if (Object.keys(patch).length) window.Plotly.restyle(plot, patch, [index]);
    });
  }
  function controls() {
    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      const label = theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
      button.setAttribute('aria-label', label); button.title = label;
      const icon = button.querySelector('.q-icon');
      if (icon) icon.textContent = theme === 'dark' ? 'light_mode' : 'dark_mode';
    });
  }
  function apply() {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    controls(); document.querySelectorAll('.js-plotly-plot').forEach(chart);
  }
  window.ProcureAITheme = {
    get: () => theme,
    set: next => { theme = next === 'dark' ? 'dark' : 'light'; try { localStorage.setItem(key, theme); } catch (_) {} apply(); },
    toggle: () => window.ProcureAITheme.set(theme === 'dark' ? 'light' : 'dark'),
  };
  function start() {
    apply();
    let pending;
    new MutationObserver(() => {
      clearTimeout(pending);
      pending = setTimeout(() => {
        controls();
        document.querySelectorAll('.js-plotly-plot').forEach(plot => { if (!originals.has(plot)) chart(plot); });
      }, 120);
    }).observe(document.body, {childList: true, subtree: true});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
