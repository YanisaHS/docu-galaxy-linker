/* concept-map.js — DocuGalaxy Concept Map visualisation */
(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Diátaxis colour palette  (https://diataxis.fr/)
  // ---------------------------------------------------------------------------
  const SECTION_COLORS = {
    'tutorial':     '#ffd700',   // gold
    'how-to':       '#56d364',   // green
    'explanation':  '#58a6ff',   // blue
    'reference':    '#bc8cff',   // purple
  };
  const DEFAULT_COLOR = '#8b949e';

  function sectionColor(key) {
    return SECTION_COLORS[key] || DEFAULT_COLOR;
  }

  // Map section_key -> human label (populated from data)
  const sectionLabels = {};

  // ---------------------------------------------------------------------------
  // Node sizing:  map word_count → node diameter (12–52 px)
  // ---------------------------------------------------------------------------
  function nodeSize(wordCount) {
    const minW = 50, maxW = 3000, minS = 12, maxS = 28;
    const clamped = Math.max(minW, Math.min(maxW, wordCount || minW));
    const t = (Math.log(clamped) - Math.log(minW)) / (Math.log(maxW) - Math.log(minW));
    return Math.round(minS + t * (maxS - minS));
  }

  // ---------------------------------------------------------------------------
  // Cytoscape stylesheet
  // ---------------------------------------------------------------------------
  function buildStylesheet() {
    const nodeTypeRules = Object.entries(SECTION_COLORS).map(([key, color]) => ({
      selector: `node.${key}`,
      style: { 'background-color': color },
    }));

    return [
      {
        selector: 'node',
        style: {
          label: 'data(label)',
          'font-size': 9,
          color: '#e6edf3',
          'text-valign': 'bottom',
          'text-margin-y': 5,
          'text-outline-color': '#0e1117',
          'text-outline-width': 2,
          'text-wrap': 'ellipsis',
          'text-max-width': 90,
          width: 'data(size)',
          height: 'data(size)',
          'border-width': 0,
        },
      },
      {
        selector: 'node:selected',
        style: {
          'border-width': 3,
          'border-color': '#ffffff',
        },
      },
      {
        selector: 'node.highlighted',
        style: { 'border-width': 2, 'border-color': '#f8e3a1' },
      },
      {
        selector: 'node.dimmed',
        style: { opacity: 0.12 },
      },
      // Edges
      {
        selector: 'edge',
        style: {
          width: 1.2,
          'curve-style': 'bezier',
          'target-arrow-shape': 'triangle',
          opacity: 0.55,
          'line-color': '#58a6ff',
          'target-arrow-color': '#58a6ff',
        },
      },
      {
        selector: 'edge.cross_ref',
        style: {
          'line-color': '#58a6ff',
          'target-arrow-color': '#58a6ff',
          width: 1.5,
        },
      },
      {
        selector: 'edge.shared_concept',
        style: {
          'line-color': '#56d364',
          'target-arrow-color': '#56d364',
          'line-style': 'dashed',
          'line-dash-pattern': [6, 4],
          width: 1.2,
          opacity: 0.45,
          'target-arrow-shape': 'none',
        },
      },
      {
        selector: 'edge.dimmed',
        style: { opacity: 0.04 },
      },
      {
        selector: 'edge:selected',
        style: { width: 3, opacity: 1 },
      },
      ...nodeTypeRules,
    ];
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------
  function showError(msg) {
    const b = document.getElementById('error-banner');
    b.textContent = msg;
    b.style.display = 'block';
  }

  function hideLoading() {
    document.getElementById('loading').style.display = 'none';
  }

  function esc(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function fmt(n) {
    return n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n);
  }

  // ---------------------------------------------------------------------------
  // Layout runner
  // ---------------------------------------------------------------------------

  const COSE_OPTS = {
    name: 'cose',
    nodeRepulsion: 2048000,
    nodeOverlap: 800,
    idealEdgeLength: 120,
    edgeElasticity: 32,
    nestingFactor: 1.2,
    gravity: 0.5,
    numIter: 2000,
    initialTemp: 1000,
    coolingFactor: 0.99,
    minTemp: 1.0,
    nodeDimensionsIncludeLabels: true,
    randomize: true,
    padding: 80,
    tile: true,
    tilingPaddingVertical: 30,
    tilingPaddingHorizontal: 50,
  };

  function runLayout(cy, animate) {
    const name = document.getElementById('layout-select').value;
    const opts = name === 'cose'
      ? { ...COSE_OPTS, animate: animate && cy.elements(':visible').length < 200 }
      : { name, animate: animate && cy.elements(':visible').length < 300,
          nodeDimensionsIncludeLabels: true, padding: 80 };
    opts.eles = cy.elements(':visible');
    cy.layout(opts).run();
    cy.fit(cy.elements(':visible'), 80);
  }

  // ---------------------------------------------------------------------------
  // Section visibility management
  // ---------------------------------------------------------------------------
  const hiddenSections = new Set();

  function applySectionFilter(cy) {
    cy.batch(() => {
      cy.nodes().forEach(n => {
        const key = n.data('type');
        n.style('display', hiddenSections.has(key) ? 'none' : 'element');
      });
      // Hide edges where either endpoint is hidden
      cy.edges().forEach(e => {
        const srcHidden = e.source().style('display') === 'none';
        const tgtHidden = e.target().style('display') === 'none';
        e.style('display', (srcHidden || tgtHidden) ? 'none' : 'element');
      });
    });
    // Re-apply edge type filter
    applyEdgeFilter(cy);
  }

  let showCrossRef = true;
  let showSharedConcept = false;  // off by default — too many edges for a clean layout

  function applyEdgeFilter(cy) {
    cy.batch(() => {
      cy.edges().forEach(e => {
        const t = e.data('type');
        const hidden =
          (t === 'cross_ref' && !showCrossRef) ||
          (t === 'shared_concept' && !showSharedConcept);
        e.style('display', hidden ? 'none' : 'element');
      });
    });
  }

  // ---------------------------------------------------------------------------
  // Main
  // ---------------------------------------------------------------------------
  async function init() {
    let elements, statsData;

    try {
      const [elRes, stRes] = await Promise.all([
        fetch('/api/graph'),
        fetch('/api/stats'),
      ]);
      if (!elRes.ok) throw new Error(`/api/graph returned ${elRes.status}`);
      elements = await elRes.json();
      statsData = stRes.ok ? await stRes.json() : null;
    } catch (err) {
      hideLoading();
      showError(`Failed to load graph: ${err.message}`);
      return;
    }

    // Inject node size into data and collect section info
    const sectionCounts = {};
    elements.forEach(el => {
      if (el.data && !el.data.source) {
        // It's a node
        el.data.size = nodeSize(el.data.word_count || 0);
        const key = el.data.type || 'other';
        const sec = el.data.section || key;
        sectionLabels[key] = sec;
        sectionCounts[key] = (sectionCounts[key] || 0) + 1;
      }
    });

    // Stats
    if (statsData) {
      const et = statsData.edge_types || {};
      const nXref = et.cross_ref || 0;
      const nSim  = et.shared_concept || 0;
      document.getElementById('stat-nodes').textContent = fmt(statsData.total_nodes);
      document.getElementById('stat-edges').textContent = fmt(nXref + nSim);
      document.getElementById('stat-xref').textContent  = fmt(nXref);
      document.getElementById('stat-sim').textContent   = fmt(nSim);
    }

    // Build section legend
    const legendEl = document.getElementById('section-legend');
    Object.entries(sectionCounts)
      .sort((a, b) => b[1] - a[1])
      .forEach(([key, count]) => {
        const color = sectionColor(key);
        const label = sectionLabels[key] || key;
        const div = document.createElement('div');
        div.className = 'legend-item';
        div.dataset.sectionKey = key;
        div.innerHTML = `
          <div class="legend-dot" style="background:${color}"></div>
          <span>${esc(label)}</span>
          <span class="legend-count">${count}</span>`;
        div.addEventListener('click', () => {
          if (hiddenSections.has(key)) {
            hiddenSections.delete(key);
            div.classList.remove('hidden-section');
          } else {
            hiddenSections.add(key);
            div.classList.add('hidden-section');
          }
          applySectionFilter(cy);
        });
        legendEl.appendChild(div);
      });

    // Init Cytoscape
    const cy = cytoscape({
      container: document.getElementById('cy'),
      elements,
      style: buildStylesheet(),
      layout: { name: 'preset', positions: {}, padding: 80 },  // overridden by runLayout() below
      minZoom: 0.04,
      maxZoom: 8,
    });

    // Apply initial edge filter (topic overlaps hidden by default)
    applyEdgeFilter(cy);

    // Apply initial layout now that nodes are sized and filtered
    runLayout(cy, false);

    hideLoading();

    // ---- Layout controls ----
    document.getElementById('btn-run-layout').addEventListener('click', () => runLayout(cy, true));
    document.getElementById('btn-fit').addEventListener('click', () =>
      cy.fit(cy.elements(':visible'), 40)
    );

    // ---- Edge type toggles ----
    // Sync initial checkbox state with showSharedConcept default
    document.getElementById('toggle-shared-concept').checked = showSharedConcept;

    document.getElementById('toggle-cross-ref').addEventListener('change', e => {
      showCrossRef = e.target.checked;
      applyEdgeFilter(cy);
    });
    document.getElementById('toggle-shared-concept').addEventListener('change', e => {
      showSharedConcept = e.target.checked;
      applyEdgeFilter(cy);
    });

    // ---- Search ----
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
        n.data('section').toLowerCase().includes(q)
      );
      cy.elements().addClass('dimmed');
      matched.removeClass('dimmed').addClass('highlighted');
      matched.connectedEdges().removeClass('dimmed');
      searchInfo.textContent = `${matched.length} match${matched.length !== 1 ? 'es' : ''}`;
    });

    // ---- Node info panel ----
    const infoPanel    = document.getElementById('info-panel');
    const infoTitle    = document.getElementById('info-title');
    const infoBody     = document.getElementById('info-body');
    const infoHeadings = document.getElementById('info-headings');
    const infoNeigh    = document.getElementById('info-neighbours');

    document.getElementById('info-close').addEventListener('click', () => {
      infoPanel.classList.remove('visible');
      cy.elements().removeClass('dimmed');
    });

    cy.on('tap', 'node', evt => {
      const node = evt.target;
      const d = node.data();

      cy.elements().addClass('dimmed');
      node.removeClass('dimmed');
      node.neighborhood().removeClass('dimmed');

      infoTitle.textContent = d.label || d.id;

      const sectionColor = SECTION_COLORS[d.type] || DEFAULT_COLOR;
      const chip = `<span style="display:inline-block;padding:1px 8px;border-radius:10px;
                    background:${sectionColor}22;border:1px solid ${sectionColor};
                    color:${sectionColor};font-size:11px;margin-bottom:8px;">${esc(d.section)}</span>`;

      const rows = [
        ['words', (d.word_count || 0).toLocaleString()],
        ['in-links', node.indegree()],
        ['out-links', node.outdegree()],
        ['path', d.path],
      ];

      infoBody.innerHTML = chip + rows.map(([k, v]) =>
        `<div class="info-row"><span class="info-key">${k}</span><span class="info-val">${esc(String(v))}</span></div>`
      ).join('');

      // Headings
      const headings = d.headings || [];
      if (headings.length) {
        infoHeadings.innerHTML =
          `<div style="margin-top:8px;font-size:11px;color:var(--muted);font-weight:600">Sections in this page:</div>` +
          `<ul class="headings-list">` +
          headings.map(h => `<li>${esc(h)}</li>`).join('') +
          `</ul>`;
      } else {
        infoHeadings.innerHTML = '';
      }

      // Neighbours
      const neighbours = node.neighborhood('node').toArray().slice(0, 20);
      if (neighbours.length) {
        infoNeigh.innerHTML =
          `<h4>Connected topics (${node.neighborhood('node').length})</h4><ul>` +
          neighbours.map(n =>
            `<li data-id="${esc(n.id())}">${esc(n.data('label') || n.id())}</li>`
          ).join('') +
          (node.neighborhood('node').length > 20 ? '<li style="color:var(--muted)">…and more</li>' : '') +
          '</ul>';

        infoNeigh.querySelectorAll('li[data-id]').forEach(li => {
          li.addEventListener('click', () => {
            const t = cy.getElementById(li.dataset.id);
            if (t.length) {
              cy.animate({ fit: { eles: t, padding: 100 }, duration: 400 });
              t.emit('tap');
            }
          });
        });
      } else {
        infoNeigh.innerHTML = '';
      }

      infoPanel.classList.add('visible');
    });

    // ---- Edge tooltip on hover ----
    const tooltip = document.getElementById('edge-tooltip');

    cy.on('mouseover', 'edge', evt => {
      const e = evt.target;
      const t = e.data('type');
      const label = e.data('label') || '';
      const sim = e.data('similarity');

      if (t === 'shared_concept' && label) {
        tooltip.innerHTML =
          `<strong>Shared concepts:</strong><br>${esc(label)}` +
          (sim ? `<br><span style="color:var(--muted)">similarity: ${sim}</span>` : '');
        tooltip.style.display = 'block';
      } else if (t === 'cross_ref') {
        tooltip.innerHTML = `<strong>Cross-reference</strong>`;
        tooltip.style.display = 'block';
      }
    });

    cy.on('mouseout', 'edge', () => {
      tooltip.style.display = 'none';
    });

    cy.on('mousemove', evt => {
      if (tooltip.style.display === 'block') {
        tooltip.style.left = (evt.originalEvent.clientX + 14) + 'px';
        tooltip.style.top  = (evt.originalEvent.clientY - 10) + 'px';
      }
    });

    // Click on background to clear selection
    cy.on('tap', evt => {
      if (evt.target === cy) {
        infoPanel.classList.remove('visible');
        cy.elements().removeClass('dimmed highlighted');
        searchInput.value = '';
        searchInfo.textContent = '';
      }
    });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
