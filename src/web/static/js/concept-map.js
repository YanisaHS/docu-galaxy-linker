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
        selector: 'edge.duplicate',
        style: {
          'line-color': '#f0a030',
          'target-arrow-color': '#f0a030',
          'line-style': 'dashed',
          'line-dash-pattern': [4, 3],
          width: 3,
          opacity: 0.85,
          'target-arrow-shape': 'none',
          'z-index': 5,
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
      {
        selector: 'node.split-candidate',
        style: {
          'border-width': 3,
          'border-color': '#f8b500',
          'border-style': 'dashed',
        },
      },
      {
        selector: 'node.split-candidate.dimmed',
        style: { opacity: 0.12 },
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
  let showDuplicate = true;

  function applyEdgeFilter(cy) {
    cy.batch(() => {
      cy.edges().forEach(e => {
        const t = e.data('type');
        const hidden =
          (t === 'cross_ref'      && !showCrossRef) ||
          (t === 'shared_concept' && !showSharedConcept) ||
          (t === 'duplicate'      && !showDuplicate);
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

    // Count split candidates
    const splitNodes = cy.nodes('.split-candidate');
    document.getElementById('stat-splits').textContent = splitNodes.length;

    // Count duplicate edges (shingle-Jaccard detected)
    const dupEdgesAll = cy.edges('[type = "duplicate"]');
    document.getElementById('stat-dups').textContent = dupEdgesAll.length;

    // ---- Split candidate highlight controls ----
    document.getElementById('btn-highlight-splits').addEventListener('click', () => {
      document.getElementById('btn-highlight-splits').style.display = 'none';
      document.getElementById('btn-clear-splits').style.display = '';
      cy.elements().addClass('dimmed');
      splitNodes.removeClass('dimmed');
    });
    document.getElementById('btn-clear-splits').addEventListener('click', () => {
      document.getElementById('btn-highlight-splits').style.display = '';
      document.getElementById('btn-clear-splits').style.display = 'none';
      cy.elements().removeClass('dimmed highlighted');
      searchInput.value = '';
      searchInfo.textContent = '';
    });

    // ---- Layout controls ----
    document.getElementById('btn-run-layout').addEventListener('click', () => runLayout(cy, true));
    document.getElementById('btn-fit').addEventListener('click', () =>
      cy.fit(cy.elements(':visible'), 40)
    );

    // ---- Edge type toggles ----
    // Sync initial checkbox states with defaults
    document.getElementById('toggle-shared-concept').checked = showSharedConcept;
    document.getElementById('toggle-duplicate').checked = showDuplicate;

    document.getElementById('toggle-cross-ref').addEventListener('change', e => {
      showCrossRef = e.target.checked;
      applyEdgeFilter(cy);
    });
    document.getElementById('toggle-shared-concept').addEventListener('change', e => {
      showSharedConcept = e.target.checked;
      applyEdgeFilter(cy);
    });
    document.getElementById('toggle-duplicate').addEventListener('change', e => {
      showDuplicate = e.target.checked;
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

      const splitBadge = d.split_candidate
        ? `<div style="display:inline-block;padding:2px 10px;border-radius:10px;
            background:#f8b50022;border:1px dashed #f8b500;color:#f8b500;
            font-size:11px;margin-bottom:8px;">✂ Consider splitting</div>`
        : '';

      const rows = [
        ['words', (d.word_count || 0).toLocaleString()],
        ['sections', d.num_sections || 0],
        ['in-links', node.indegree()],
        ['out-links', node.outdegree()],
        ['path', d.path],
      ];
      if (d.split_candidate) {
        rows.splice(2, 0, ['divergence', Math.round(d.split_score * 100) + '%']);
      }

      infoBody.innerHTML = chip + splitBadge + rows.map(([k, v]) =>
        `<div class="info-row"><span class="info-key">${k}</span><span class="info-val">${esc(String(v))}</span></div>`
      ).join('');
      if (d.split_candidate) {
        infoBody.innerHTML += `<div style="margin-top:8px;font-size:11px;color:var(--muted)">` +
          `This page's sections have low vocabulary overlap — they may cover distinct topics that could each stand alone as a separate page.</div>`;

        const sections = d.split_sections || [];
        if (sections.length) {
          infoBody.innerHTML +=
            `<div style="margin-top:10px;font-size:11px;color:#f8b500;font-weight:600">Sections detected as divergent:</div>` +
            `<ol style="margin:6px 0 0 16px;padding:0;font-size:11px;color:var(--text);line-height:1.8">` +
            sections.map(s => `<li>${esc(s)}</li>`).join('') +
            `</ol>` +
            `<div style="margin-top:8px;font-size:11px;color:var(--muted)">` +
            `Each item above could potentially become its own page. Consider whether a reader looking for any one of these topics would benefit from a dedicated page with its own title, introduction, and cross-references.</div>`;
        }
      }

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

    // ---- Edge click → info panel ----
    cy.on('tap', 'edge', evt => {
      const edge = evt.target;
      const d = edge.data();
      const src = cy.getElementById(d.source);
      const tgt = cy.getElementById(d.target);
      const srcLabel = src.data('label') || d.source;
      const tgtLabel = tgt.data('label') || d.target;
      const srcColor = SECTION_COLORS[src.data('type')] || DEFAULT_COLOR;
      const tgtColor = SECTION_COLORS[tgt.data('type')] || DEFAULT_COLOR;

      cy.elements().addClass('dimmed');
      edge.removeClass('dimmed');
      src.removeClass('dimmed');
      tgt.removeClass('dimmed');

      const nodeChip = (label, color) =>
        `<span style="display:inline-block;padding:2px 10px;border-radius:6px;
          background:${color}22;border:1px solid ${color};color:${color};font-size:11px">${esc(label)}</span>`;

      if (d.type === 'cross_ref') {
        infoTitle.textContent = 'Cross-reference';
        infoBody.innerHTML =
          `<div style="margin-bottom:8px">${nodeChip(srcLabel, srcColor)}</div>` +
          `<div style="font-size:11px;color:var(--muted);margin-bottom:8px">↓ explicitly links to ↓</div>` +
          `<div style="margin-bottom:10px">${nodeChip(tgtLabel, tgtColor)}</div>` +
          `<div style="margin-top:8px;font-size:11px;color:var(--muted)">` +
          `This link was written by the documentation author.</div>`;
      } else if (d.type === 'shared_concept') {
        const sim = d.similarity || 0;
        const simPct = Math.round(sim * 100);
        const isDup = !!d.potential_duplicate;
        const ov = d.overlap_coefficient != null ? Math.round(d.overlap_coefficient * 100) + '%' : null;
        const hOverlap = d.heading_overlap || 0;
        const dupBadge = isDup
          ? `<div class="dup-badge">⚠ Potential duplicate</div>`
          : '';
        const terms = Array.isArray(d.shared_terms) && d.shared_terms.length
          ? d.shared_terms
          : (d.label ? d.label.split(', ') : []);
        infoTitle.textContent = 'Topic overlap';
        infoBody.innerHTML =
          dupBadge +
          `<div style="margin-bottom:8px">${nodeChip(srcLabel, srcColor)}</div>` +
          `<div style="font-size:11px;color:var(--muted);margin-bottom:8px">and</div>` +
          `<div style="margin-bottom:10px">${nodeChip(tgtLabel, tgtColor)}</div>` +
          `<div class="info-row"><span class="info-key">content overlap</span>` +
          `<span class="info-val" style="font-weight:600;color:${isDup ? '#f0a030' : 'var(--text)'}">` +
          `${ov ?? '—'}</span></div>` +
          `<div class="info-row"><span class="info-key">shared headings</span>` +
          `<span class="info-val">${hOverlap}</span></div>` +
          `<div class="info-row"><span class="info-key">vocab similarity</span>` +
          `<span class="info-val" style="color:var(--muted)">${simPct}%</span></div>`;
        if (terms.length) {
          infoBody.innerHTML +=
            `<div style="margin-top:8px;font-size:11px;color:var(--muted);font-weight:600">Related terms:</div>` +
            `<div style="margin-top:4px">${terms.map(t => `<span class="term-chip">${esc(t)}</span>`).join('')}</div>`;
        }
        const note = isDup
          ? 'High content overlap — these pages may cover the same material. Consider merging or adding a clear distinction.'
          : 'These pages cover related topics and may benefit from cross-references.';
        infoBody.innerHTML += `<div style="margin-top:10px;font-size:11px;color:var(--muted)">${note}</div>`;
      } else if (d.type === 'duplicate') {
        const jaccard = d.jaccard != null ? Math.round(d.jaccard * 100) + '%' : (d.label || '—');
        infoTitle.textContent = 'Potential duplicate';
        infoBody.innerHTML =
          `<div class="dup-badge">⚠ Potential duplicate</div>` +
          `<div style="margin-bottom:8px">${nodeChip(srcLabel, srcColor)}</div>` +
          `<div style="font-size:11px;color:var(--muted);margin-bottom:8px">and</div>` +
          `<div style="margin-bottom:10px">${nodeChip(tgtLabel, tgtColor)}</div>` +
          `<div class="info-row"><span class="info-key">text overlap</span>` +
          `<span class="info-val" style="font-weight:600;color:#f0a030">${jaccard}</span></div>` +
          `<div style="margin-top:10px;font-size:11px;color:var(--muted)">` +
          `High phrase-level overlap detected. These pages likely contain copy-pasted content and may need to be merged or differentiated.</div>`;
      }

      infoHeadings.innerHTML = '';
      infoNeigh.innerHTML = '';
      infoPanel.classList.add('visible');
    });

    // ---- Duplicate highlight controls ----
    document.getElementById('btn-highlight-dups').addEventListener('click', () => {
      document.getElementById('btn-highlight-dups').style.display = 'none';
      document.getElementById('btn-clear-dups').style.display = '';
      // Ensure duplicate edges are visible before highlighting
      if (!showDuplicate) {
        showDuplicate = true;
        document.getElementById('toggle-duplicate').checked = true;
        applyEdgeFilter(cy);
      }
      cy.elements().addClass('dimmed');
      const dupEdges = cy.edges('[type = "duplicate"]');
      dupEdges.removeClass('dimmed');
      dupEdges.connectedNodes().removeClass('dimmed');
    });
    document.getElementById('btn-clear-dups').addEventListener('click', () => {
      document.getElementById('btn-highlight-dups').style.display = '';
      document.getElementById('btn-clear-dups').style.display = 'none';
      cy.elements().removeClass('dimmed highlighted');
      searchInput.value = '';
      searchInfo.textContent = '';
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
      } else if (t === 'duplicate') {
        const j = e.data('jaccard');
        tooltip.innerHTML = `<strong style="color:#f0a030">⚠ Potential duplicate</strong>` +
          (j != null ? `<br><span style="color:var(--muted)">text overlap: ${Math.round(j * 100)}%</span>` : '');
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
