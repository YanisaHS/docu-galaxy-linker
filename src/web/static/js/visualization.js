/* visualization.js — DocuGalaxy interactive graph
 *
 * Data source adapter:
 *   - If window.__DGL_DATA__ = { elements, stats } is set (standalone bundle),
 *     use it.
 *   - Otherwise fetch /api/graph + /api/stats (Flask server).
 *
 * This indirection means the bundler doesn't have to patch this file.
 */
(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Diataxis sections + colours
  // ---------------------------------------------------------------------------
  const DIATAXIS_COLORS = {
    tutorial:    '#f0883e',
    'how-to':    '#7ee787',
    reference:   '#79c0ff',
    explanation: '#bc8cff',
    meta:        '#8b949e',
  };

  const NODE_COLORS = {
    document: '#58a6ff',
    external: '#f0883e',
    label:    '#bc8cff',
    anchor:   '#7ee787',
    asset:    '#8b949e',
    unknown:  '#8b949e',
  };

  const EDGE_COLORS = {
    doc_link:      '#58a6ff',
    external_link: '#f0883e',
    link:          '#79c0ff',
    ref_link:      '#bc8cff',
    include:       '#ffa657',
    anchor_link:   '#7ee787',
    image:         '#56d364',
    term_link:     '#d2a8ff',
    unknown:       '#8b949e',
  };

  const INTERNAL_EDGE_TYPES = new Set([
    'doc_link', 'ref_link', 'include', 'anchor_link', 'link', 'term_link', 'image',
  ]);
  const EXTERNAL_EDGE_TYPES = new Set(['external_link']);

  const MIN_SIZE = 14;
  const MAX_SIZE = 80;

  // ---------------------------------------------------------------------------
  // Data loader (adapter pattern)
  // ---------------------------------------------------------------------------
  async function loadData() {
    if (window.__DGL_DATA__) {
      return window.__DGL_DATA__;
    }
    const [g, s] = await Promise.all([
      fetch('/api/graph'),
      fetch('/api/stats'),
    ]);
    if (!g.ok) throw new Error(`/api/graph returned ${g.status}`);
    return {
      elements: await g.json(),
      stats: s.ok ? await s.json() : null,
    };
  }

  // ---------------------------------------------------------------------------
  // Pre-processing
  // ---------------------------------------------------------------------------
  function dedupeAndAnnotate(elements) {
    const nodes = [];
    const edgeMap = new Map(); // key=src->tgt
    for (const el of elements) {
      const d = el.data;
      if (!d.source) { nodes.push(el); continue; }
      const key = `${d.source}->${d.target}`;
      const existing = edgeMap.get(key);
      if (existing) {
        existing.data.weight += 1;
      } else {
        d.weight = 1;
        edgeMap.set(key, el);
      }
    }
    const edges = Array.from(edgeMap.values());

    // Compute in/out degree + node size (intensity = sqrt(in+out))
    const inDeg  = new Map();
    const outDeg = new Map();
    for (const e of edges) {
      const d = e.data;
      outDeg.set(d.source, (outDeg.get(d.source) || 0) + 1);
      inDeg.set(d.target,  (inDeg.get(d.target)  || 0) + 1);
    }
    let maxI = 0;
    for (const n of nodes) {
      const d = n.data;
      d._inDeg  = inDeg.get(d.id)  || 0;
      d._outDeg = outDeg.get(d.id) || 0;
      d._intensity = Math.sqrt(d._inDeg + d._outDeg);
      if (d._intensity > maxI) maxI = d._intensity;
    }
    for (const n of nodes) {
      const d = n.data;
      const t = maxI > 0 ? d._intensity / maxI : 0;
      d.size = Math.round(MIN_SIZE + t * (MAX_SIZE - MIN_SIZE));
    }

    return nodes.concat(edges);
  }

  // ---------------------------------------------------------------------------
  // Stylesheet
  // ---------------------------------------------------------------------------
  function buildStylesheet() {
    const dia = Object.entries(DIATAXIS_COLORS).map(([sec, c]) => ({
      selector: `node[diataxis = "${sec}"]`,
      style: { 'background-color': c },
    }));
    const nodeType = Object.entries(NODE_COLORS).map(([t, c]) => ({
      selector: `node[type = "${t}"]`,
      style: { 'background-color': c },
    }));
    const edgeType = Object.entries(EDGE_COLORS).map(([t, c]) => ({
      selector: `edge[type = "${t}"]`,
      style: { 'line-color': c, 'target-arrow-color': c },
    }));
    return [
      {
        selector: 'node',
        style: {
          label: 'data(label)',
          'font-size': 'mapData(size, 14, 80, 6, 14)',
          color: '#e6edf3',
          'text-valign': 'bottom',
          'text-margin-y': 4,
          'text-outline-color': '#0e1117',
          'text-outline-width': 2,
          width:  'data(size)',
          height: 'data(size)',
          'border-width': 0,
        },
      },
      { selector: 'node[size <= 22]', style: { 'text-opacity': 0 } },
      ...nodeType,
      ...dia,
      ...edgeType,
      {
        selector: 'node[broken = "true"]',
        style: {
          'border-width': 2,
          'border-color': '#f85149',
          'border-style': 'dashed',
        },
      },
      {
        selector: 'node:selected, node.highlighted',
        style: {
          'border-width': 3,
          'border-color': '#f8e3a1',
          'text-opacity': 1,
        },
      },
      { selector: 'node.dimmed', style: { opacity: 0.08, 'text-opacity': 0 } },
      {
        selector: 'edge',
        style: {
          width: 'mapData(weight, 1, 10, 1, 5)',
          'curve-style': 'bezier',
          'target-arrow-shape': 'triangle',
          'arrow-scale': 0.7,
          opacity: 0.55,
        },
      },
      { selector: 'edge.dimmed', style: { opacity: 0.03 } },
      { selector: 'edge:selected, edge.highlighted', style: { width: 3, opacity: 1 } },
    ];
  }

  // ---------------------------------------------------------------------------
  // Layout
  // ---------------------------------------------------------------------------
  function layoutOptions(name, visibleEles) {
    const n = visibleEles.length;
    const animate = n < 350;
    if (name === 'fcose') {
      // Scale spacing with the number of visible elements so small graphs
      // don't drift apart and big graphs don't pile up.
      const ideal = Math.max(70, Math.min(180, 60 + Math.sqrt(n) * 4));
      return {
        name: 'fcose',
        animate,
        randomize: true,           // bad initial positions otherwise
        quality: 'default',
        nodeRepulsion: 6500,
        idealEdgeLength: ideal,
        edgeElasticity: 0.35,
        gravity: 0.2,
        gravityRangeCompound: 1.5,
        numIter: 2500,
        nodeDimensionsIncludeLabels: true,
        uniformNodeDimensions: false,
        packComponents: true,      // lay out disconnected components nicely
        padding: 40,
      };
    }
    if (name === 'concentric') {
      return {
        name: 'concentric',
        animate,
        concentric: node => (node.data('_intensity') || 0),
        levelWidth: () => 1,
        minNodeSpacing: 14,
        padding: 30,
      };
    }
    return { name, animate, randomize: false, nodeDimensionsIncludeLabels: true, padding: 30 };
  }

  function runLayout(cy, animate) {
    const name = document.getElementById('layout-select').value;
    const visibleEles = cy.elements(':visible');
    if (visibleEles.length === 0) return;
    const opts = layoutOptions(name, visibleEles);
    opts.eles = visibleEles;
    if (!animate) opts.animate = false;
    cy.layout(opts).run();
    cy.fit(visibleEles, 40);
  }

  // ---------------------------------------------------------------------------
  // View / preset state (URL-synced)
  // ---------------------------------------------------------------------------
  const state = { view: 'internal', preset: 'all', sel: null };

  function readHash() {
    const h = window.location.hash.replace(/^#/, '');
    const params = new URLSearchParams(h);
    if (params.has('view'))   state.view   = params.get('view');
    if (params.has('preset')) state.preset = params.get('preset');
    if (params.has('sel'))    state.sel    = params.get('sel');
  }

  function writeHash() {
    const params = new URLSearchParams();
    if (state.view !== 'internal') params.set('view', state.view);
    if (state.preset !== 'all')    params.set('preset', state.preset);
    if (state.sel)                 params.set('sel', state.sel);
    const h = params.toString();
    const newHash = h ? '#' + h : '';
    if (newHash !== window.location.hash) {
      history.replaceState(null, '', window.location.pathname + window.location.search + newHash);
    }
  }

  // ---------------------------------------------------------------------------
  // View / preset filtering
  // ---------------------------------------------------------------------------
  function applyView(view, cy) {
    state.view = view;
    cy.batch(() => {
      cy.elements().style('display', 'element');
      if (view === 'internal') {
        cy.edges().forEach(e => {
          if (!INTERNAL_EDGE_TYPES.has(e.data('type'))) e.style('display', 'none');
        });
        cy.nodes('[type = "external"]').forEach(n => {
          const hasVisible = n.connectedEdges().some(e => e.style('display') !== 'none');
          if (!hasVisible) n.style('display', 'none');
        });
      } else {
        cy.edges().forEach(e => {
          if (!EXTERNAL_EDGE_TYPES.has(e.data('type'))) e.style('display', 'none');
        });
        cy.nodes().forEach(n => {
          const hasExt = n.connectedEdges().some(e => e.data('type') === 'external_link');
          if (!hasExt) n.style('display', 'none');
        });
      }
    });
    document.querySelectorAll('.edge-toggle').forEach(cb => {
      if (!cb.checked) cy.edges(`[type = "${cb.value}"]`).style('display', 'none');
    });
    applyPreset(state.preset, cy);
    writeHash();
  }

  function applyPreset(preset, cy) {
    state.preset = preset;
    document.querySelectorAll('.preset-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.preset === preset);
    });
    if (preset === 'all') {
      writeHash();
      return;
    }
    cy.batch(() => {
      if (preset === 'docs') {
        cy.nodes().forEach(n => {
          if (n.data('type') !== 'document') n.style('display', 'none');
        });
      } else if (preset === 'orphans') {
        cy.nodes().forEach(n => {
          const isDoc = n.data('type') === 'document';
          const broken = n.data('broken') === 'true';
          const orphan = (n.data('_inDeg') || 0) === 0;
          if (!isDoc || broken || !orphan) n.style('display', 'none');
        });
      } else if (preset === 'deadends') {
        cy.nodes().forEach(n => {
          const isDoc = n.data('type') === 'document';
          const broken = n.data('broken') === 'true';
          const dead   = (n.data('_outDeg') || 0) === 0;
          if (!isDoc || broken || !dead) n.style('display', 'none');
        });
      } else if (preset === 'hubs') {
        const docs = cy.nodes('[type = "document"]').toArray()
          .filter(n => n.data('broken') !== 'true')
          .sort((a, b) => (b.data('_intensity') || 0) - (a.data('_intensity') || 0))
          .slice(0, 25);
        const keep = new Set(docs.map(n => n.id()));
        docs.forEach(n => n.neighborhood('node').forEach(m => keep.add(m.id())));
        cy.nodes().forEach(n => {
          if (!keep.has(n.id())) n.style('display', 'none');
        });
      } else if (preset === 'broken') {
        // Show every node flagged broken + nodes that link to one.
        const broken = cy.nodes('[broken = "true"]');
        const keep = new Set(broken.map(n => n.id()));
        broken.forEach(n => n.incomers('node').forEach(m => keep.add(m.id())));
        cy.nodes().forEach(n => {
          if (!keep.has(n.id())) n.style('display', 'none');
        });
      }
    });
    writeHash();
  }

  // ---------------------------------------------------------------------------
  // Info panel — impact analysis split
  // ---------------------------------------------------------------------------
  let activeInfoTab = 'incoming';

  function showInfoPanel(node, cy) {
    const data = node.data();
    state.sel = node.id();
    writeHash();

    cy.elements().addClass('dimmed');
    node.removeClass('dimmed');
    node.neighborhood().removeClass('dimmed');

    document.getElementById('info-title').textContent = data.label || data.id;

    const diaChip = data.diataxis
      ? `<span style="display:inline-block;padding:1px 8px;border-radius:10px;
                     background:${DIATAXIS_COLORS[data.diataxis]}22;
                     border:1px solid ${DIATAXIS_COLORS[data.diataxis]};
                     color:${DIATAXIS_COLORS[data.diataxis]};font-size:11px">
          ${data.diataxis}</span> `
      : '';
    const brokenChip = data.broken === 'true'
      ? `<span style="display:inline-block;padding:1px 8px;border-radius:10px;
                      background:#f8514922;border:1px solid #f85149;
                      color:#f85149;font-size:11px">broken</span> `
      : '';

    const rows = [
      ['id', data.id],
      ['type', data.type],
      data.path ? ['path', data.path] : null,
      data.url  ? ['url', `<a href="${escHtml(data.url)}" target="_blank" rel="noopener" style="color:var(--accent)">${escHtml(data.url)}</a>`] : null,
      ['in-degree',  data._inDeg  ?? node.indegree()],
      ['out-degree', data._outDeg ?? node.outdegree()],
      ['intensity',  (data._intensity || 0).toFixed(2)],
    ].filter(Boolean);

    document.getElementById('info-body').innerHTML = diaChip + brokenChip + rows.map(([k, v]) =>
      `<div class="info-row"><span class="info-key">${k}</span><span class="info-val">${k === 'url' ? v : escHtml(v)}</span></div>`
    ).join('');

    // Action buttons (open source, open URL, copy markdown)
    const actions = [];
    if (data.source_url) {
      actions.push(`<a href="${escHtml(data.source_url)}" target="_blank" rel="noopener">📄 Open source</a>`);
    }
    if (data.render_url) {
      actions.push(`<a href="${escHtml(data.render_url)}" target="_blank" rel="noopener">🌐 Open page</a>`);
    }
    if (data.url && data.type === 'external') {
      actions.push(`<a href="${escHtml(data.url)}" target="_blank" rel="noopener">↗ Open URL</a>`);
    }
    actions.push(`<button id="info-copy">📋 Copy impact as Markdown</button>`);
    document.getElementById('info-actions').innerHTML = actions.join('');
    document.getElementById('info-copy').addEventListener('click', () => copyImpactMarkdown(node));

    renderInfoList(node, cy, activeInfoTab);

    document.getElementById('info-panel').classList.add('visible');
  }

  function renderInfoList(node, cy, tab) {
    activeInfoTab = tab;
    document.querySelectorAll('.info-tab').forEach(b => {
      b.classList.toggle('active', b.dataset.tab === tab);
    });
    const list = document.getElementById('info-list');
    const edges = tab === 'incoming' ? node.incomers('edge') : node.outgoers('edge');
    if (edges.length === 0) {
      list.innerHTML = `<div class="empty">No ${tab} links.</div>`;
      return;
    }
    const items = edges.toArray().map(e => {
      const other = tab === 'incoming' ? e.source() : e.target();
      const label = other.data('label') || other.id();
      const linkText = e.data('label');
      const annotation = linkText ? ` — <span style="color:var(--muted)">"${escHtml(linkText)}"</span>` : '';
      return `<li data-id="${escHtml(other.id())}">${escHtml(label)}${annotation}</li>`;
    });
    list.innerHTML = `<ul>${items.slice(0, 50).join('')}${items.length > 50 ? `<li style="color:var(--muted)">…and ${items.length - 50} more</li>` : ''}</ul>`;
    list.querySelectorAll('li[data-id]').forEach(li => {
      li.addEventListener('click', () => {
        const target = cy.getElementById(li.dataset.id);
        if (target.length) {
          cy.animate({ fit: { eles: target, padding: 80 }, duration: 400 });
          target.emit('tap');
        }
      });
    });
  }

  // ---------------------------------------------------------------------------
  // Copy impact as Markdown checklist
  // ---------------------------------------------------------------------------
  function copyImpactMarkdown(node) {
    const data = node.data();
    const title = data.path || data.label || data.id;
    const srcLink = data.source_url ? `[\`${title}\`](${data.source_url})` : `\`${title}\``;
    const incoming = node.incomers('node').toArray();
    const outgoing = node.outgoers('node').toArray();

    const lines = [];
    lines.push(`# Impact: ${title}`, '');
    lines.push(`Source: ${srcLink}`);
    if (data.diataxis) lines.push(`Diataxis: ${data.diataxis}`);
    lines.push('');
    lines.push(`## Linked from (${incoming.length}) — these break if this is renamed/removed`);
    if (incoming.length === 0) {
      lines.push('- _(no incoming links — orphan page)_');
    } else {
      for (const n of incoming) {
        const p = n.data('path') || n.id();
        const u = n.data('source_url');
        lines.push(`- [ ] ${u ? `[\`${p}\`](${u})` : `\`${p}\``}`);
      }
    }
    lines.push('');
    lines.push(`## Links to (${outgoing.length}) — these are this page's dependencies`);
    if (outgoing.length === 0) {
      lines.push('- _(no outgoing links — dead end)_');
    } else {
      for (const n of outgoing) {
        const p = n.data('path') || n.data('label') || n.id();
        const u = n.data('source_url') || n.data('url');
        lines.push(`- ${u ? `[\`${p}\`](${u})` : `\`${p}\``}`);
      }
    }

    const text = lines.join('\n');
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(
        () => toast('Impact list copied to clipboard.'),
        () => fallbackCopy(text),
      );
    } else {
      fallbackCopy(text);
    }
  }

  function fallbackCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); toast('Copied.'); }
    catch { toast('Copy failed — clipboard blocked.'); }
    document.body.removeChild(ta);
  }

  // ---------------------------------------------------------------------------
  // Toast + help
  // ---------------------------------------------------------------------------
  let toastTimer = null;
  function toast(msg) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.classList.add('visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('visible'), 1800);
  }

  function toggleHelp(show) {
    const overlay = document.getElementById('help-overlay');
    if (show === undefined) overlay.classList.toggle('visible');
    else overlay.classList.toggle('visible', show);
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------
  function showError(msg) {
    const banner = document.getElementById('error-banner');
    banner.textContent = msg;
    banner.style.display = 'block';
  }
  function hideLoading() { document.getElementById('loading').style.display = 'none'; }
  function formatNumber(n) { return n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n); }
  function escHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ---------------------------------------------------------------------------
  // Main
  // ---------------------------------------------------------------------------
  async function init() {
    // Register fcose if available
    if (typeof cytoscape !== 'undefined' && typeof cytoscapeFcose !== 'undefined') {
      try { cytoscape.use(cytoscapeFcose); } catch (e) { /* already registered */ }
    }

    let data;
    try { data = await loadData(); }
    catch (err) { hideLoading(); showError(`Failed to load graph: ${err.message}`); return; }

    // export_cytoscape_json flattens metadata (diataxis, source_url,
    // render_url, broken) directly onto each node's data dict, so no
    // post-processing is needed here.
    let elements = dedupeAndAnnotate(data.elements);

    // Populate stats
    const statsData = data.stats;
    if (statsData) {
      document.getElementById('stat-nodes').textContent = formatNumber(statsData.total_nodes);
      document.getElementById('stat-edges').textContent = formatNumber(statsData.total_edges);
      document.getElementById('stat-docs').textContent  = formatNumber(statsData.node_types?.document ?? 0);
      document.getElementById('stat-ext').textContent   = formatNumber(statsData.node_types?.external ?? 0);

      // Quality metrics
      const q = statsData.quality;
      if (q) {
        document.getElementById('quality-section').style.display = '';
        document.getElementById('q-purity').textContent =
          (q.diataxis_purity * 100).toFixed(0) + '%';
        document.getElementById('q-reach').textContent =
          (q.reachability_at_3 * 100).toFixed(0) + '%';

        const findings = document.getElementById('findings-list');
        const items = [
          { label: 'Orphans',         count: q.orphans,           preset: 'orphans',  cls: q.orphans > 0 ? 'warn' : '' },
          { label: 'Dead ends',       count: q.dead_ends,         preset: 'deadends', cls: q.dead_ends > 0 ? 'warn' : '' },
          { label: 'Broken doc refs', count: q.broken_doc_refs,   preset: 'broken',   cls: q.broken_doc_refs > 0 ? 'danger' : '' },
          { label: 'Broken anchors',  count: q.broken_anchors,    preset: 'broken',   cls: q.broken_anchors > 0 ? 'danger' : '' },
          { label: 'Broken labels',   count: q.broken_label_refs, preset: 'broken',   cls: q.broken_label_refs > 0 ? 'danger' : '' },
          { label: 'Diataxis crosses', count: q.diataxis_cross_edges, preset: 'all',  cls: '' },
        ];
        findings.innerHTML = items.map(it =>
          `<div class="finding-row ${it.cls}" data-preset="${it.preset}">
             <span>${escHtml(it.label)}</span>
             <span class="count">${it.count}</span>
           </div>`
        ).join('');
        findings.querySelectorAll('.finding-row[data-preset]').forEach(row => {
          row.addEventListener('click', () => {
            const btn = document.querySelector(`.preset-btn[data-preset="${row.dataset.preset}"]`);
            if (btn) btn.click();
          });
        });
      }
    }
    document.getElementById('graph-title').textContent =
      document.querySelector('title').textContent.replace('DocuGalaxy — ', '');

    // URL state
    readHash();

    const fcoseAvail = typeof cytoscapeFcose !== 'undefined';
    const cy = cytoscape({
      container: document.getElementById('cy'),
      elements,
      style: buildStylesheet(),
      // Use a preset (no positions) so we can run a proper layout once
      // visibility has been applied — avoids laying out hidden externals.
      layout: { name: 'preset' },
      minZoom: 0.05,
      maxZoom: 6,
      wheelSensitivity: 0.3,
    });

    const layoutSelect = document.getElementById('layout-select');
    if (fcoseAvail && !layoutSelect.value) layoutSelect.value = 'fcose';

    // Minimap
    if (typeof cy.navigator === 'function') {
      try {
        cy.navigator({
          container: document.getElementById('cy-minimap'),
          viewLiveFramerate: 0,
          thumbnailEventFramerate: 30,
          thumbnailLiveFramerate: false,
          dblClickDelay: 200,
          removeCustomContainer: false,
        });
      } catch (e) { /* minimap optional */ }
    }

    applyView(state.view, cy);
    if (state.preset !== 'all') applyPreset(state.preset, cy);

    // Run the layout exactly once on the *visible* element set. Without
    // this, the initial preset placement leaves every node at (0,0) and the
    // graph renders as a single point/line.
    runLayout(cy, false);

    // Restore selection if hash had one
    if (state.sel) {
      const node = cy.getElementById(state.sel);
      if (node.length) {
        cy.animate({ fit: { eles: node, padding: 80 }, duration: 400 });
        showInfoPanel(node, cy);
      }
    }

    hideLoading();

    // ----- View tabs -----
    document.querySelectorAll('.view-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.view-tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        applyView(btn.dataset.view, cy);
        runLayout(cy, false);
      });
    });

    // ----- Presets -----
    document.querySelectorAll('.preset-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        applyView(state.view, cy);
        applyPreset(btn.dataset.preset, cy);
        runLayout(cy, false);
      });
    });

    // ----- Layout -----
    document.getElementById('btn-run-layout').addEventListener('click', () => runLayout(cy, true));
    document.getElementById('btn-fit').addEventListener('click',
      () => cy.fit(cy.elements(':visible'), 40));

    // ----- Edge toggles -----
    document.querySelectorAll('.edge-toggle').forEach(cb => {
      cb.addEventListener('change', () => {
        cy.edges(`[type = "${cb.value}"]`).style('display', cb.checked ? 'element' : 'none');
        applyView(state.view, cy);
      });
    });

    // ----- Search -----
    const searchInput = document.getElementById('search-input');
    const searchInfo  = document.getElementById('search-info');
    searchInput.addEventListener('input', () => {
      const q = searchInput.value.trim().toLowerCase();
      if (!q) {
        cy.elements().removeClass('highlighted dimmed');
        searchInfo.textContent = '';
        return;
      }
      const matched = cy.nodes(':visible').filter(n =>
        (n.data('label') || '').toLowerCase().includes(q) ||
        (n.data('id')    || '').toLowerCase().includes(q)
      );
      cy.elements().addClass('dimmed');
      matched.removeClass('dimmed').addClass('highlighted');
      matched.connectedEdges().removeClass('dimmed');
      searchInfo.textContent = `${matched.length} match${matched.length !== 1 ? 'es' : ''}`;
    });

    // ----- Hover highlight -----
    cy.on('mouseover', 'node', evt => {
      const node = evt.target;
      if (cy.$('node:selected').length) return; // don't override selection
      cy.elements().addClass('dimmed');
      node.removeClass('dimmed').addClass('highlighted');
      node.neighborhood().removeClass('dimmed');
    });
    cy.on('mouseout', 'node', () => {
      if (!cy.$('node:selected').length) cy.elements().removeClass('dimmed highlighted');
    });

    // ----- Click node -----
    cy.on('tap', 'node', evt => showInfoPanel(evt.target, cy));

    cy.on('tap', evt => {
      if (evt.target === cy) {
        closeInfoPanel(cy);
        searchInput.value = '';
        searchInfo.textContent = '';
      }
    });

    document.getElementById('info-close').addEventListener('click', () => closeInfoPanel(cy));
    document.querySelectorAll('.info-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        const sel = cy.$('node:selected')[0];
        if (sel) renderInfoList(sel, cy, btn.dataset.tab);
      });
    });

    function closeInfoPanel(cy) {
      document.getElementById('info-panel').classList.remove('visible');
      cy.elements().removeClass('dimmed highlighted');
      cy.$('node:selected').unselect();
      state.sel = null;
      writeHash();
    }

    // ----- Help overlay -----
    document.getElementById('help-close').addEventListener('click', () => toggleHelp(false));
    document.getElementById('help-overlay').addEventListener('click', e => {
      if (e.target.id === 'help-overlay') toggleHelp(false);
    });

    // ----- Keyboard shortcuts -----
    document.addEventListener('keydown', e => {
      const inForm = ['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName);
      if (e.key === 'Escape') {
        if (document.getElementById('help-overlay').classList.contains('visible')) {
          toggleHelp(false); return;
        }
        if (inForm) { document.activeElement.blur(); return; }
        closeInfoPanel(cy);
        searchInput.value = ''; searchInfo.textContent = '';
        return;
      }
      if (inForm) return;
      if (e.key === '/') { e.preventDefault(); searchInput.focus(); return; }
      if (e.key === '?') { toggleHelp(); return; }
      if (e.key === 'f') { cy.fit(cy.elements(':visible'), 40); return; }
      if (e.key === 'r') { runLayout(cy, true); return; }
      if (e.key === 'i') {
        const next = state.view === 'internal' ? 'external' : 'internal';
        document.querySelectorAll('.view-tab').forEach(b => b.classList.toggle('active', b.dataset.view === next));
        applyView(next, cy);
        runLayout(cy, false);
        return;
      }
      if (e.key === 'o') {
        const sel = cy.$('node:selected')[0];
        if (sel) {
          const url = sel.data('source_url') || sel.data('url') || sel.data('render_url');
          if (url) window.open(url, '_blank', 'noopener');
        }
        return;
      }
      if (e.key === 'c') {
        const sel = cy.$('node:selected')[0];
        if (sel) copyImpactMarkdown(sel);
        return;
      }
      // 1..6: presets
      const btn = document.querySelector(`.preset-btn[data-key="${e.key}"]`);
      if (btn) btn.click();
    });

    // ----- Hashchange sync (back/forward, manual edits) -----
    window.addEventListener('hashchange', () => {
      const prev = { ...state };
      readHash();
      if (prev.view !== state.view || prev.preset !== state.preset) {
        applyView(state.view, cy);
        applyPreset(state.preset, cy);
        runLayout(cy, false);
      }
      if (prev.sel !== state.sel) {
        if (state.sel) {
          const n = cy.getElementById(state.sel);
          if (n.length) showInfoPanel(n, cy);
        } else {
          closeInfoPanel(cy);
        }
      }
    });
  }

  init();
})();
