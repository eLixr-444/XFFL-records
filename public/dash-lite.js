// dash-lite: a small stand-in for the Claude dashboard runtime, so the record book
// page runs as a plain public web page. Loads data/*.json, runs the page's
// calculations and drawings, and redraws on resize and tab changes.
(function () {
  const SOURCES = ['games', 'seasons', 'champions'];
  const sources = {};          // id -> {status, data}
  const calcs = {};            // id -> {inputs, fn}
  const calcCache = {};        // id -> {status, data}
  const draws = {};            // name -> {fn} or {mount, update, unmount}
  const made = new WeakMap();  // element -> value returned by mount

  SOURCES.forEach((id) => { sources[id] = { status: 'loading', data: [] }; });

  const data = (id) => {
    if (sources[id]) return sources[id];
    if (calcs[id]) {
      if (calcCache[id]) return calcCache[id];
      const ins = calcs[id].inputs.map(data);
      if (ins.some((r) => r.status === 'error')) return { status: 'error', data: null };
      if (ins.some((r) => r.status !== 'ok')) return { status: 'loading', data: null };
      try {
        calcCache[id] = { status: 'ok', data: calcs[id].fn(...ins.map((r) => r.data)) };
      } catch (e) {
        console.error('Calculation failed:', id, e);
        calcCache[id] = { status: 'error', data: null, message: String(e) };
      }
      return calcCache[id];
    }
    return { status: 'missing', data: [] };
  };

  const isShown = (el) => !el.closest('[hidden]');

  const runDraw = (name) => {
    const d = draws[name];
    if (!d) return;
    document.querySelectorAll('[data-draw="' + name + '"]').forEach((el) => {
      if (!isShown(el)) return;
      try {
        if (d.fn) d.fn(el);
        else {
          if (!made.has(el)) { el.replaceChildren(); made.set(el, d.mount ? d.mount(el) : undefined); }
          if (d.update) d.update(el, made.get(el));
        }
      } catch (e) { console.error('Drawing failed:', name, e); }
    });
  };
  const runAll = () => Object.keys(draws).forEach(runDraw);

  window.dash = {
    data,
    calc: (id, def) => { calcs[id] = def; },
    loader: () => {},
    onData: (fn) => { try { fn(); } catch (e) { console.error(e); } },
    draw: (name, def) => {
      if (def === undefined) { runDraw(name); return; }
      draws[name] = typeof def === 'function' ? { fn: def } : def;
    },
    colors: ['var(--series-1)', 'var(--series-2)', 'var(--series-3)', 'var(--series-4)'],
    refresh: () => {},
    params: () => ({}),
    setParams: () => {},
    resetParams: () => {},
    setLink: (name) => {
      const hash = name ? '#' + name : '';
      if (location.hash !== hash) history.replaceState(null, '', hash || location.pathname + location.search);
      setTimeout(runAll, 0);
    },
  };

  const start = () => {
    runAll();
    Promise.all(SOURCES.map((id) =>
      fetch('data/' + id + '.json', { cache: 'no-cache' })
        .then((r) => { if (!r.ok) throw new Error(r.status + ' ' + r.statusText); return r.json(); })
        .then((j) => { sources[id] = { status: 'ok', data: Array.isArray(j) ? j : j.rows || [] }; })
        .catch((e) => { console.error('Could not load', id, e); sources[id] = { status: 'error', data: [], message: String(e) }; })
    )).then(runAll);
    let t;
    window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(runAll, 150); });
  };
  window.dashStart = start;
})();
