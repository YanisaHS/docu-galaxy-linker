/* visualization.js — DocuGalaxy interactive graph */
(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Diataxis sections (Canonical / Landscape docs convention)
  // ---------------------------------------------------------------------------
  const DIATAXIS_COLORS = {
    tutorial:    '#f0883e',  // orange — guided learning
    'how-to':    '#7ee787',  // green  — task-oriented
    reference:   '#79c0ff',  // blue   — information lookup
    explanation: '#bc8cff',  // purple — understanding
    meta:        '#8b949e',  // grey   — contributing, index, release-notes
  };

  function diataxisSection(node) {
    if (node.type !== 'document') return null;
    const path = (node.path || node.id || '').toLowerCase();
    if (path.startsWith('tutorial')) return 'tutorial';
    if (path.startsWith('how-to')) return 'how-to';
    if (path.startsWith('reference')) return 'reference';
    if (path.startsWith('explanation')) return 'explanation';
    return 'meta';
  }

  // ---------------------------------------------------------------------------
  // Fallback colours by node type
  // ---------------------------------------------------------------------------
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

  // ---------------------------------------------------------------------------
  // Node size scaling — intensity = sqrt(in + out degree)
  // ---------------------------------------------------------------------------
  const MIN_SIZE = 14;
  const MAX_SIZE = 80;

  function computeSizes(elements) {
    const inDeg  = new Map();
    const outDeg = new Map();
    for (const el of elements) {
      const d = el.data;
      if (!d.source) continue; // node
    }
    for (const el of elements) {
      const d = el.data;
      if (!d.source) continue; // edge only
      outDeg.set(d.source, (outDeg.get(d.source) || 0) + 1);
      inDeg.set(d.target,  (inDeg.get(d.target)  || 0) + 1);
    }
    let maxIntensity = 0;
    for (const el of elements) {
      const d = el.data;
      if (d.source) continue;
      const intensity = Math.sqrt((inDeg.get(d.id) || 0) + (outDeg.get(d.id) || 0));
      d._intensity = intensity;
      d._inDeg  = inDeg.get(d.id)  || 0;
      d._outDeg = outDeg.get(d.id) || 0;
      if (intensity > maxIntensity) maxIntensity = intensity;
    }
    for (const el of elements) {
      const d = el.data;
      if (d.source) continue;
      const t = maxIntensity > 0 ? d._intensity / maxIntensity : 0;
      d.size = Math.round(MIN_SIZE + t * (MAX_SIZE - MIN_SIZE));
    }
    return { inDeg, outDeg, maxIntensity };
  }

  // ---------------------------------------------------------------------------
  // Cytoscape stylesheet
  // ---------------------------------------------------------------------------
  function buildStylesheet() {
    const diataxisRules = Object.entries(DIATAXIS_COLORS).map(([sec, color]) => ({
      selector: `node[diataxis = "${sec}"]`,
      style: { 'background-color': color },
    }));

    const nodeTypeRules = Object.entries(NODE_COLORS).map(([type, color]) => ({
      selector: `node[type = "${type}"]`,
      style: { 'background-color': color },
    }));

    const edgeRules = Object.entries(EDGE_COLORS).map(([type, color]) => ({
      selector: `edge[type = "${type}"]`,
      style: { 'line-color': color, 'target-arrow-color': color },
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
          'overlay-padding': 4,
        },
      },
      // Hide labels for tiny nodes unless hovered/selected
      {
        selector: 'node[size <= 22]',
        style: { 'text-opacity': 0 },
      },
      ...nodeTypeRules,    // type fallback (applied first)
      ...diataxisRules,    // diataxis overrides type for documents
      ...edgeRules,
      {
        selector: 'node:selected, node.highlighted',
        style: {
          'border-width': 3,
          'border-color': '#f8e3a1',
          'text-opacity': 1,
        },
      },
      {
        selector: 'node.dimmed',
        style: { opacity: 0.08, 'text-opacity': 0 },
      },
      {
        selector: 'edge',
        style: {
          width:  'mapData(weight, 1, 10, 1, 5)',
          'curve-style': 'bezier',
          'target-arrow-shape': 'triangle',
          'arrow-scale': 0.7,
          opacity: 0.55,
        },
      },
      {
        selector: 'edge.dimmed',
        style: { opacity: 0.03 },
      },
      {
        selector: 'edge:selected, edge.highlighted',
        style: { width: 3, opacity: 1 },
      },
      {
        selector: 'node:active',
        style: { 'overlay-opacity': 0.2, 'overlay-color': '#f8e3a1' },
      },
    ];
  }

  // ---------------------------------------------------------------------------
  // Edge dedup: collapse parallel edges between the same (source,target) pair
  // ---------------------------------------------------------------------------
  function dedupeEdges(elements) {
    const edges = [];
    const nodes = [];
    const seen = new Map();
    for (const el of elements) {
      const d = el.data;
      if (!d.source) { nodes.push(el); continue; }
      const key = `${d.source}->${d.target}`;
      if (seen.has(key)) {
        const existing = seen.get(key);
        existing.data.weight += 1;
        // Keep the strongest edge type label
        existing.data.labels = (existing.data.labels || [existing.data.label || existing.data.type]);
        existing.data.labels.push(d.label || d.type);
        continue;
      }
      d.weight = 1;
      seen.set(key, el);
      edges.push(el);
    }
    return nodes.concat(edges);
  }

  // ---------------------------------------------------------------------------
  // Layout helpers
  // ---------------------------------------------------------------------------
  function layoutOptions(name, visibleEles) {
    const animate = visibleEles.length < 350;
    if (name === 'fcose') {
      return {
        name: 'fcose',
        animate,
        randomize: false,
        quality: 'default',
        nodeRepulsion: 8000,
        idealEdgeLength: 90,
        edgeElasticity: 0.45,
        gravity: 0.25,
        numIter: 2500,
        nodeDimensionsIncludeLabels: true,
        padding: 30,
      };
    }
    if (name === 'concentric') {
      return {
        name: 'concentric',
        animate,
        concentric: n => (n.data('_intensity') || 0),
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
    const opts = layoutOptions(name, visibleEles);
    opts.eles = visibleEles;
    if (!animate) opts.animate = false;
    cy.layout(opts).run();
    cy.fit(visibleEles, 40);
  }

  // ---------------------------------------------------------------------------
  // View management  (internal / external)
  // ---------------------------------------------------------------------------
  let currentView = 'internal';
  let currentPreset = 'all';

  function applyView(view, cy) {
    currentView = view;
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
          const hasExternal = n.connectedEdges().some(e => e.data('type') === 'external_link');
          if (!hasExternal) n.style('display', 'none');
        });
      }
    });

    document.querySelectorAll('.edge-toggle').forEach(cb => {
      if (!cb.checked) cy.edges(`[type = "${cb.value}"]`).style('display', 'none');
    });

    applyPreset(currentPreset, cy);
    runLayout(cy, false);
  }

  function applyPreset(preset, cy) {
    currentPreset = preset;
    document.querySelectorAll('.preset-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.preset === preset);
    });

    if (preset === 'all') {
      // Nothing extra to hide beyond view filtering
      return;
    }

    cy.batch(() => {
      if (preset === 'docs') {
        cy.nodes().forEach(n => {
          if (n.data('type') !== 'document') n.style('display', 'none');
        });
      } else if (preset === 'orphans') {
        // Documents with in-degree 0 (no incoming internal links)
        cy.nodes().forEach(n => {
          const isDoc = n.data('type') === 'document';
          const orphan = (n.data('_inDeg') || 0) === 0;
          if (!isDoc || !orphan) n.style('display', 'none');
        });
      } else if (preset === 'deadends') {
        cy.nodes().forEach(n => {
          const isDoc = n.data('type') === 'document';
          const dead  = (n.data('_outDeg') || 0) === 0;
          if (!isDoc || !dead) n.style('display', 'none');
        });
      } else if (preset === 'hubs') {
        const docs = cy.nodes('[type = "document"]').toArray()
          .sort((a, b) => (b.data('_intensity') || 0) - (a.data('_intensity') || 0))
          .slice(0, 25);
        const keep = new Set(docs.map(n => n.id()));
        // Also keep direct neighbours of the hubs
        docs.forEach(n => n.neighborhood('node').forEach(m => keep.add(m.id())));
        cy.nodes().forEach(n => {
          if (!keep.has(n.id())) n.style('display', 'none');
        });
      }
    });
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

    let elements, statsData;
    try {
      const [elemRes, statsRes] = await Promise.all([
        fetch('/api/graph'),
        fetch('/api/stats'),
      ]);
      if (!elemRes.ok) throw new Error(`/api/graph returned ${elemRes.status}`);
      elements = await elemRes.json();
      statsData = statsRes.ok ? await statsRes.json() : null;
    } catch (err) {
      hideLoading();
      showError(`Failed to load graph: ${err.message}`);
      return;
    }

    // Pre-process: dedupe parallel edges, tag Diataxis section, compute sizes
    elements = dedupeEdges(elements);
    for (const el of elements) {
      const d = el.data;
      if (d.source) continue;
      const sec = diataxisSection(d);
      if (sec) d.diataxis = sec;
    }
    computeSizes(elements);

    // Populate stats
    if (statsData) {
      document.getElementById('stat-nodes').textContent = formatNumber(statsData.total_nodes);
      document.getElementById('stat-edges').textContent = formatNumber(statsData.total_edges);
      document.getElementById('stat-docs').textContent  = formatNumber(statsData.node_types?.document ?? 0);
      document.getElementById('stat-ext').textContent   = formatNumber(statsData.node_types?.external ?? 0);
    }
    document.getElementById('graph-title').textContent =
      document.querySelector('title').textContent.replace('DocuGalaxy — ', '');

    // Init Cytoscape
    const fcoseAvail = typeof cytoscapeFcose !== 'undefined';
    const cy = cytoscape({
      container: document.getElementById('cy'),
      elements,
      style: buildStylesheet(),
      layout: fcoseAvail
        ? { name: 'fcose', animate: false, randomize: false, quality: 'default',
            nodeRepulsion: 8000, idealEdgeLength: 90, padding: 30 }
        : { name: 'cose', animate: false, randomize: false, padding: 30 },
      minZoom: 0.05,
      maxZoom: 6,
      wheelSensitivity: 0.3,
    });

    // Set default layout option in the dropdown
    const layoutSelect = document.getElementById('layout-select');
    if (fcoseAvail) layoutSelect.value = 'fcose';

    applyView('internal', cy);
    hideLoading();

    // View tabs
    document.querySelectorAll('.view-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.view-tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        applyView(btn.dataset.view, cy);
      });
    });

    // Preset buttons
    document.querySelectorAll('.preset-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        applyView(currentView, cy); // resets visibility
        applyPreset(btn.dataset.preset, cy);
        runLayout(cy, false);
      });
    });

    // Layout controls
    document.getElementById('btn-run-layout').addEventListener('click', () => runLayout(cy, true));
    document.getElementById('btn-fit').addEventListener('click',
      () => cy.fit(cy.elements(':visible'), 40));

    // Edge type toggles
    document.querySelectorAll('.edge-toggle').forEach(cb => {
      cb.addEventListener('change', () => {
        cy.edges(`[type = "${cb.value}"]`).style('display', cb.checked ? 'element' : 'none');
        applyView(currentView, cy);
      });
    });

    // Search / filter
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

    // Hover highlight (1-hop)
    cy.on('mouseover', 'node', evt => {
      const node = evt.target;
      cy.elements().addClass('dimmed');
      node.removeClass('dimmed').addClass('highlighted');
      node.neighborhood().removeClass('dimmed');
      node.connectedEdges().addClass('highlighted');
    });
    cy.on('mouseout', 'node', () => {
      if (!cy.$('node:selected').length) {
        cy.elements().removeClass('dimmed highlighted');
      }
    });

    // Info panel
    const infoPanel = document.getElementById('info-panel');
    const infoTitle = document.getElementById('info-title');
    const infoBody  = document.getElementById('info-body');
    const infoNeigh = document.getElementById('info-neighbours');
    const infoClose = document.getElementById('info-close');

    infoClose.addEventListener('click', () => {
      infoPanel.classList.remove('visible');
      cy.elements().removeClass('dimmed highlighted');
      cy.$('node:selected').unselect();
    });

    cy.on('tap', 'node', evt => {
      const node = evt.target;
      const data = node.data();

      cy.elements().addClass('dimmed');
      node.removeClass('dimmed');
      node.neighborhood().removeClass('dimmed');

      infoTitle.textContent = data.label || data.id;

      const diaChip = data.diataxis
        ? `<span style="display:inline-block;padding:1px 8px;border-radius:10px;
                       background:${DIATAXIS_COLORS[data.diataxis]}22;
                       border:1px solid ${DIATAXIS_COLORS[data.diataxis]};
                       color:${DIATAXIS_COLORS[data.diataxis]};font-size:11px">
            ${data.diataxis}</span> `
        : '';

      const rows = [
        ['id', data.id],
        ['type', data.type],
        data.path ? ['path', data.path] : null,
        data.url  ? ['url', `<a href="${escHtml(data.url)}" target="_blank" rel="noopener" style="color:var(--accent)">${escHtml(data.url)}</a>`] : null,
        ['in-degree',  data._inDeg ?? node.indegree()],
        ['out-degree', data._outDeg ?? node.outdegree()],
        ['intensity',  (data._intensity || 0).toFixed(2)],
      ].filter(Boolean);

      infoBody.innerHTML = diaChip + rows.map(([k, v]) =>
        `<div class="info-row"><span class="info-key">${k}</span><span class="info-val">${k === 'url' ? v : escHtml(v)}</span></div>`
      ).join('');

      const neigh = node.neighborhood('node').toArray().slice(0, 20);
      if (neigh.length) {
        infoNeigh.innerHTML =
          `<h4>Connected nodes (${node.neighborhood('node').length})</h4><ul>` +
          neigh.map(n => `<li data-id="${escHtml(n.id())}">${escHtml(n.data('label') || n.id())}</li>`).join('') +
          (node.neighborhood('node').length > 20 ? '<li style="color:var(--muted)">…and more</li>' : '') +
          '</ul>';
        infoNeigh.querySelectorAll('li[data-id]').forEach(li => {
          li.addEventListener('click', () => {
            const target = cy.getElementById(li.dataset.id);
            if (target.length) {
              cy.animate({ fit: { eles: target, padding: 80 }, duration: 400 });
              target.emit('tap');
            }
          });
        });
      } else {
        infoNeigh.innerHTML = '';
      }

      infoPanel.classList.add('visible');
    });

    cy.on('tap', evt => {
      if (evt.target === cy) {
        infoPanel.classList.remove('visible');
        cy.elements().removeClass('dimmed highlighted');
        searchInput.value = '';
        searchInfo.textContent = '';
      }
    });
  }

  init();
})();
