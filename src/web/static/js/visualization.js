/* visualization.js — DocuGalaxy interactive graph */
(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Project colour map  (add new projects here)
  // ---------------------------------------------------------------------------
  const PROJECT_COLORS = {
    'landscape-documentation':       '#79c0ff',  // sky blue
    'ubuntu-server-documentation':   '#56d364',  // green
    'ubuntu-security-documentation': '#ffa657',  // orange
  };
  const DEFAULT_PROJECT_COLOR = '#8b949e';

  function projectColor(project) {
    return project ? (PROJECT_COLORS[project] || DEFAULT_PROJECT_COLOR) : null;
  }

  // ---------------------------------------------------------------------------
  // Colour maps (fallback when no project is set)
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

  // Edge types that belong to each view
  const INTERNAL_EDGE_TYPES = new Set([
    'doc_link', 'ref_link', 'include', 'anchor_link', 'link', 'term_link', 'image',
  ]);
  const EXTERNAL_EDGE_TYPES = new Set(['external_link']);

  // ---------------------------------------------------------------------------
  // Cytoscape stylesheet
  // ---------------------------------------------------------------------------
  function buildStylesheet(hasProjects) {
    // Base node type colours (always applied)
    const nodeTypeRules = Object.entries(NODE_COLORS).map(([type, color]) => ({
      selector: `node.${type}`,
      style: { 'background-color': color },
    }));

    // Project colour overrides (applied AFTER node type rules → higher specificity wins in order)
    const projectRules = hasProjects
      ? Object.entries(PROJECT_COLORS).map(([proj, color]) => ({
          selector: `node[project = "${proj}"]`,
          style: { 'background-color': color },
        }))
      : [];

    const edgeRules = Object.entries(EDGE_COLORS).map(([type, color]) => ({
      selector: `edge.${type}`,
      style: { 'line-color': color, 'target-arrow-color': color },
    }));

    return [
      {
        selector: 'node',
        style: {
          label: 'data(label)',
          'font-size': 10,
          color: '#e6edf3',
          'text-valign': 'bottom',
          'text-margin-y': 4,
          'text-outline-color': '#0e1117',
          'text-outline-width': 2,
          width: 22,
          height: 22,
          'border-width': 0,
        },
      },
      {
        selector: 'node:selected',
        style: {
          'border-width': 3,
          'border-color': '#ffffff',
          width: 28,
          height: 28,
        },
      },
      {
        selector: 'node.highlighted',
        style: {
          'border-width': 2,
          'border-color': '#f8e3a1',
          width: 26,
          height: 26,
        },
      },
      {
        selector: 'node.dimmed',
        style: { opacity: 0.15 },
      },
      {
        selector: 'edge',
        style: {
          width: 1.5,
          'curve-style': 'bezier',
          'target-arrow-shape': 'triangle',
          opacity: 0.7,
        },
      },
      {
        selector: 'edge.dimmed',
        style: { opacity: 0.05 },
      },
      {
        selector: 'edge:selected',
        style: { width: 3, opacity: 1 },
      },
      ...nodeTypeRules,
      ...projectRules,
      ...edgeRules,
    ];
  }

  // ---------------------------------------------------------------------------
  // View management  (internal / external)
  // ---------------------------------------------------------------------------
  let currentView = 'internal';

  function applyView(view, cy) {
    currentView = view;

    cy.batch(() => {
      // Reset all
      cy.elements().style('display', 'element');

      if (view === 'internal') {
        // Hide external_link edges
        cy.edges().forEach(e => {
          if (!INTERNAL_EDGE_TYPES.has(e.data('type'))) {
            e.style('display', 'none');
          }
        });
        // Hide external nodes with no remaining visible edges
        cy.nodes('[type = "external"]').forEach(n => {
          const hasVisible = n.connectedEdges().some(
            e => e.style('display') !== 'none',
          );
          if (!hasVisible) n.style('display', 'none');
        });
      } else {
        // external view: show only external_link edges
        cy.edges().forEach(e => {
          if (!EXTERNAL_EDGE_TYPES.has(e.data('type'))) {
            e.style('display', 'none');
          }
        });
        // Hide nodes not connected to any external_link edge
        cy.nodes().forEach(n => {
          const hasExternal = n.connectedEdges().some(
            e => e.data('type') === 'external_link',
          );
          if (!hasExternal) n.style('display', 'none');
        });
      }
    });

    // Re-apply edge checkbox overrides
    document.querySelectorAll('.edge-toggle').forEach(cb => {
      if (!cb.checked) {
        cy.edges(`.${cb.value}`).style('display', 'none');
      }
    });

    runLayout(cy, false);
  }

  function runLayout(cy, animate) {
    const name = document.getElementById('layout-select').value;
    const visibleEles = cy.elements(':visible');
    cy.layout({
      name,
      animate: animate && visibleEles.length < 400,
      randomize: false,
      nodeDimensionsIncludeLabels: true,
      padding: 30,
      eles: visibleEles,
    }).run();
    cy.fit(visibleEles, 30);
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------
  function showError(msg) {
    const banner = document.getElementById('error-banner');
    banner.textContent = msg;
    banner.style.display = 'block';
  }

  function hideLoading() {
    document.getElementById('loading').style.display = 'none';
  }

  function formatNumber(n) {
    return n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n);
  }

  function escHtml(str) {
    return str
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ---------------------------------------------------------------------------
  // Main
  // ---------------------------------------------------------------------------
  async function init() {
    let elements;
    let statsData;

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

    // Detect whether the graph has project tags
    const projects = [...new Set(
      elements
        .filter(el => el.data && el.data.type && !el.data.source && el.data.project)
        .map(el => el.data.project)
    )].sort();
    const hasProjects = projects.length > 1;

    // Populate stats
    if (statsData) {
      document.getElementById('stat-nodes').textContent = formatNumber(statsData.total_nodes);
      document.getElementById('stat-edges').textContent = formatNumber(statsData.total_edges);
      document.getElementById('stat-docs').textContent  = formatNumber(statsData.node_types?.document ?? 0);
      document.getElementById('stat-ext').textContent   = formatNumber(statsData.node_types?.external ?? 0);
    }

    document.getElementById('graph-title').textContent =
      document.querySelector('title').textContent.replace('DocuGalaxy — ', '');

    // ---- Populate project legend ----
    const projLegend = document.getElementById('project-legend-section');
    if (hasProjects) {
      projLegend.style.display = 'block';
      const list = document.getElementById('project-legend-list');
      list.innerHTML = projects.map(p => {
        const color = PROJECT_COLORS[p] || DEFAULT_PROJECT_COLOR;
        return `<div class="legend-item">
          <div class="legend-dot" style="background:${color}"></div>
          <span>${p}</span>
        </div>`;
      }).join('');
    }

    // ---- Init Cytoscape ----
    const cy = cytoscape({
      container: document.getElementById('cy'),
      elements,
      style: buildStylesheet(hasProjects),
      layout: { name: 'cose', animate: false, randomize: false, nodeDimensionsIncludeLabels: true },
      minZoom: 0.05,
      maxZoom: 6,
    });

    // Apply initial view AFTER layout
    applyView('internal', cy);

    hideLoading();

    // ---- View tabs ----
    document.querySelectorAll('.view-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.view-tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        applyView(btn.dataset.view, cy);
      });
    });

    // ---- Layout controls ----
    document.getElementById('btn-run-layout').addEventListener('click', () => runLayout(cy, true));
    document.getElementById('btn-fit').addEventListener('click', () =>
      cy.fit(cy.elements(':visible'), 30)
    );

    // ---- Edge type toggles ----
    document.querySelectorAll('.edge-toggle').forEach(cb => {
      cb.addEventListener('change', () => {
        cy.edges(`.${cb.value}`).style('display', cb.checked ? 'element' : 'none');
        // Re-hide edges hidden by current view
        applyView(currentView, cy);
      });
    });

    // ---- Search / filter ----
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
        n.data('label').toLowerCase().includes(q) ||
        n.data('id').toLowerCase().includes(q)
      );
      cy.elements().addClass('dimmed');
      matched.removeClass('dimmed').addClass('highlighted');
      matched.connectedEdges().removeClass('dimmed');
      searchInfo.textContent = `${matched.length} match${matched.length !== 1 ? 'es' : ''}`;
    });

    // ---- Node info panel ----
    const infoPanel = document.getElementById('info-panel');
    const infoTitle = document.getElementById('info-title');
    const infoBody  = document.getElementById('info-body');
    const infoNeigh = document.getElementById('info-neighbours');
    const infoClose = document.getElementById('info-close');

    infoClose.addEventListener('click', () => {
      infoPanel.classList.remove('visible');
      cy.elements().removeClass('dimmed');
    });

    cy.on('tap', 'node', evt => {
      const node = evt.target;
      const data = node.data();

      cy.elements().addClass('dimmed');
      node.removeClass('dimmed');
      node.neighborhood().removeClass('dimmed');

      infoTitle.textContent = data.label || data.id;

      const projColor = projectColor(data.project);
      const projChip = data.project
        ? `<span style="display:inline-block;padding:1px 8px;border-radius:10px;
                        background:${projColor}22;border:1px solid ${projColor};
                        color:${projColor};font-size:11px">${data.project}</span> `
        : '';

      const rows = [
        ['id', data.id],
        ['type', data.type],
        data.path   ? ['path',   data.path]   : null,
        data.url    ? ['url',    data.url]     : null,
        data.project ? ['project', data.project] : null,
        ['in-degree',  node.indegree()],
        ['out-degree', node.outdegree()],
      ].filter(Boolean);

      infoBody.innerHTML = projChip + rows.map(([k, v]) =>
        `<div class="info-row"><span class="info-key">${k}</span><span class="info-val">${escHtml(String(v))}</span></div>`
      ).join('');

      const neighbours = node.neighborhood('node').toArray().slice(0, 20);
      if (neighbours.length) {
        infoNeigh.innerHTML =
          `<h4>Connected nodes (${node.neighborhood('node').length})</h4><ul>` +
          neighbours.map(n =>
            `<li data-id="${escHtml(n.id())}">${escHtml(n.data('label') || n.id())}</li>`
          ).join('') +
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

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Colour maps
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

  // ---------------------------------------------------------------------------
  // Cytoscape stylesheet
  // ---------------------------------------------------------------------------
  function buildStylesheet() {
    const nodeRules = Object.entries(NODE_COLORS).map(([type, color]) => ({
      selector: `node.${type}`,
      style: { 'background-color': color },
    }));

    const edgeRules = Object.entries(EDGE_COLORS).map(([type, color]) => ({
      selector: `edge.${type}`,
      style: { 'line-color': color, 'target-arrow-color': color },
    }));

    return [
      {
        selector: 'node',
        style: {
          label: 'data(label)',
          'font-size': 10,
          color: '#e6edf3',
          'text-valign': 'bottom',
          'text-margin-y': 4,
          'text-outline-color': '#0e1117',
          'text-outline-width': 2,
          width: 22,
          height: 22,
          'border-width': 0,
        },
      },
      {
        selector: 'node:selected',
        style: {
          'border-width': 3,
          'border-color': '#ffffff',
          width: 28,
          height: 28,
        },
      },
      {
        selector: 'node.highlighted',
        style: {
          'border-width': 2,
          'border-color': '#f8e3a1',
          width: 26,
          height: 26,
        },
      },
      {
        selector: 'node.dimmed',
        style: { opacity: 0.15 },
      },
      {
        selector: 'edge',
        style: {
          width: 1.5,
          'curve-style': 'bezier',
          'target-arrow-shape': 'triangle',
          opacity: 0.7,
        },
      },
      {
        selector: 'edge.dimmed',
        style: { opacity: 0.05 },
      },
      {
        selector: 'edge:selected',
        style: { width: 3, opacity: 1 },
      },
      ...nodeRules,
      ...edgeRules,
    ];
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------
  function showError(msg) {
    const banner = document.getElementById('error-banner');
    banner.textContent = msg;
    banner.style.display = 'block';
  }

  function hideLoading() {
    document.getElementById('loading').style.display = 'none';
  }

  function formatNumber(n) {
    return n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n);
  }

  // ---------------------------------------------------------------------------
  // Main
  // ---------------------------------------------------------------------------
  async function init() {
    let elements;
    let statsData;

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

    // Populate stats
    if (statsData) {
      document.getElementById('stat-nodes').textContent = formatNumber(statsData.total_nodes);
      document.getElementById('stat-edges').textContent = formatNumber(statsData.total_edges);
      document.getElementById('stat-docs').textContent  = formatNumber(statsData.node_types?.document ?? 0);
      document.getElementById('stat-ext').textContent   = formatNumber(statsData.node_types?.external ?? 0);
    }

    // Graph title
    document.getElementById('graph-title').textContent =
      document.querySelector('title').textContent.replace('DocuGalaxy — ', '');

    // ---- Init Cytoscape ----
    const cy = cytoscape({
      container: document.getElementById('cy'),
      elements,
      style: buildStylesheet(),
      layout: { name: 'cose', animate: false, randomize: false, nodeDimensionsIncludeLabels: true },
      minZoom: 0.05,
      maxZoom: 6,
    });

    hideLoading();

    // ---- Layout controls ----
    document.getElementById('btn-run-layout').addEventListener('click', () => {
      const name = document.getElementById('layout-select').value;
      cy.layout({
        name,
        animate: elements.length < 500,
        randomize: false,
        nodeDimensionsIncludeLabels: true,
        padding: 30,
      }).run();
    });

    document.getElementById('btn-fit').addEventListener('click', () => cy.fit(30));

    // ---- Edge type toggles ----
    document.querySelectorAll('.edge-toggle').forEach(cb => {
      cb.addEventListener('change', () => {
        const type = cb.value;
        cy.edges(`.${type}`).style('display', cb.checked ? 'element' : 'none');
      });
    });

    // ---- Search / filter ----
    const searchInput = document.getElementById('search-input');
    const searchInfo  = document.getElementById('search-info');

    searchInput.addEventListener('input', () => {
      const q = searchInput.value.trim().toLowerCase();
      if (!q) {
        cy.elements().removeClass('highlighted dimmed');
        searchInfo.textContent = '';
        return;
      }
      const matched = cy.nodes().filter(n =>
        n.data('label').toLowerCase().includes(q) ||
        n.data('id').toLowerCase().includes(q)
      );
      cy.elements().addClass('dimmed');
      matched.removeClass('dimmed').addClass('highlighted');
      matched.connectedEdges().removeClass('dimmed');
      searchInfo.textContent = `${matched.length} match${matched.length !== 1 ? 'es' : ''}`;
    });

    // ---- Node info panel ----
    const infoPanel  = document.getElementById('info-panel');
    const infoTitle  = document.getElementById('info-title');
    const infoBody   = document.getElementById('info-body');
    const infoNeigh  = document.getElementById('info-neighbours');
    const infoClose  = document.getElementById('info-close');

    infoClose.addEventListener('click', () => {
      infoPanel.classList.remove('visible');
      cy.elements().removeClass('dimmed');
    });

    cy.on('tap', 'node', evt => {
      const node = evt.target;
      const data = node.data();

      // Dim non-neighbours
      cy.elements().addClass('dimmed');
      node.removeClass('dimmed');
      node.neighborhood().removeClass('dimmed');

      // Populate panel
      infoTitle.textContent = data.label || data.id;

      const rows = [
        ['id', data.id],
        ['type', data.type],
        data.path ? ['path', data.path] : null,
        data.url  ? ['url',  data.url]  : null,
        ['in-degree',  node.indegree()],
        ['out-degree', node.outdegree()],
      ].filter(Boolean);

      infoBody.innerHTML = rows.map(([k, v]) =>
        `<div class="info-row"><span class="info-key">${k}</span><span class="info-val">${escHtml(String(v))}</span></div>`
      ).join('');

      // Neighbours list
      const neighbours = node.neighborhood('node').toArray().slice(0, 20);
      if (neighbours.length) {
        infoNeigh.innerHTML = `<h4>Connected nodes (${node.neighborhood('node').length})</h4><ul>` +
          neighbours.map(n =>
            `<li data-id="${escHtml(n.id())}">${escHtml(n.data('label') || n.id())}</li>`
          ).join('') +
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

  function escHtml(str) {
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  init();
})();
