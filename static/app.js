document.addEventListener('DOMContentLoaded', () => {
  const chipsContainer = document.getElementById('chips-container');
  const sectionCountBadge = document.getElementById('section-count-badge');
  const customSectionInput = document.getElementById('custom-section-input');
  const btnAddSection = document.getElementById('btn-add-section');
  const btnResetSections = document.getElementById('btn-reset-sections');
  const btnClearSections = document.getElementById('btn-clear-sections');

  const researchForm = document.getElementById('research-form');
  const btnSubmit = document.getElementById('btn-submit');
  const btnLabel = document.getElementById('btn-label');
  const btnSpinner = document.getElementById('btn-spinner');
  
  const stepperPanel = document.getElementById('stepper-panel');
  const resultsPanel = document.getElementById('results-panel');

  // The 9 Default Sections (provided as initial starting template)
  const defaultSections = [
    "Healthcare system overview",
    "Epidemiology",
    "Societal & Provider Perception of Obesity",
    "Clinical Guidelines & Treatment Practices",
    "Regulatory Framework & Approval Bodies",
    "Unmet Needs & Clinical Gaps",
    "Access, Coverage & Reimbursement Barriers",
    "Competitive Landscape & Product Intelligence",
    "Patient Advocacy, Public Affairs & Strategic Initiatives"
  ];

  // Dynamic user-modifiable array of sections
  let currentSections = [...defaultSections];

  function renderSectionChips() {
    chipsContainer.innerHTML = '';
    sectionCountBadge.textContent = currentSections.length;

    if (currentSections.length === 0) {
      chipsContainer.innerHTML = '<span style="color: var(--text-dim); font-size: 13px; font-style: italic;">No sections added yet. Type a section name below to add one!</span>';
      return;
    }

    currentSections.forEach((sec, idx) => {
      const chip = document.createElement('div');
      chip.className = 'section-chip';
      chip.innerHTML = `
        <span>${idx + 1}. ${escapeHtml(sec)}</span>
        <span class="chip-remove" data-index="${idx}" title="Remove this section">✕</span>
      `;
      chipsContainer.appendChild(chip);
    });

    // Add click listeners to remove buttons
    document.querySelectorAll('.chip-remove').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const index = parseInt(e.target.getAttribute('data-index'), 10);
        currentSections.splice(index, 1);
        renderSectionChips();
      });
    });
  }

  function addCustomSection() {
    const val = customSectionInput.value.trim();
    if (!val) return;
    if (currentSections.includes(val)) {
      alert('This section is already in your list.');
      return;
    }
    currentSections.push(val);
    customSectionInput.value = '';
    renderSectionChips();
  }

  // Button actions for section manager
  btnAddSection.addEventListener('click', addCustomSection);
  customSectionInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addCustomSection();
    }
  });

  btnResetSections.addEventListener('click', () => {
    currentSections = [...defaultSections];
    renderSectionChips();
  });

  btnClearSections.addEventListener('click', () => {
    currentSections = [];
    renderSectionChips();
  });

  // Initial render of section chips
  renderSectionChips();

  // Tab switching
  const tabButtons = document.querySelectorAll('.tab-btn');
  const tabContents = document.querySelectorAll('.tab-content');

  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      tabButtons.forEach(b => b.classList.remove('active'));
      tabContents.forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const targetId = btn.getAttribute('data-tab');
      const targetContent = document.getElementById(targetId);
      if (targetContent) targetContent.classList.add('active');
    });
  });

  // Form Submission
  researchForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const topic = document.getElementById('topic-input').value.trim();
    const countriesStr = document.getElementById('country-input').value.trim();
    const countries = countriesStr.split(',').map(c => c.trim()).filter(Boolean);
    const minPubYear = Number(document.getElementById('year-cutoff-input').value);
    const periodStartYear = Number(document.getElementById('period-start-input').value);
    const periodEndYear = Number(document.getElementById('period-end-input').value);
    const maxSourcesVolume = parseInt(document.getElementById('volume-input').value.trim(), 10) || 20;

    if (!topic) {
      alert('Please enter a research topic or condition.');
      return;
    }

    if (countries.length === 0) {
      alert('Please specify at least one target country.');
      return;
    }

    if (currentSections.length === 0) {
      alert('Please add at least one research section.');
      return;
    }

    if (![minPubYear, periodStartYear, periodEndYear].every(year => Number.isInteger(year) && year >= 1900 && year <= 2100)) {
      alert('Enter valid years between 1900 and 2100 for the validation rules.');
      return;
    }

    if (periodStartYear > periodEndYear) {
      alert('Data Period Start Year must be less than or equal to End Year.');
      return;
    }

    // UI Loading state
    btnSubmit.disabled = true;
    btnSpinner.style.display = 'inline-block';
    btnLabel.textContent = `Orchestrating research on ${topic} across ${countries.length} countries...`;
    stepperPanel.style.display = 'block';
    resultsPanel.style.display = 'none';

    const progressTimer = animateSteps();

    try {
      const response = await fetch('/api/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic,
          disease: topic,
          countries,
          sections: currentSections,
          min_publication_year: minPubYear,
          data_period_start_year: periodStartYear,
          data_period_end_year: periodEndYear,
          max_sources_per_section: maxSourcesVolume
        })
      });

      const queued = await parseApiResponse(response);
      const data = await waitForResearchJob(queued.status_url);
      displayResults(data);

    } catch (err) {
      alert(`Research Execution Error: ${err.message}`);
      document.querySelectorAll('.stepper-step').forEach(step => step.classList.remove('active'));
    } finally {
      clearInterval(progressTimer);
      btnSubmit.disabled = false;
      btnSpinner.style.display = 'none';
      btnLabel.textContent = 'Execute Autonomous Multi-Agent Research';
    }
  });

  async function parseApiResponse(response) {
    const bodyText = await response.text();
    let body = {};
    try {
      body = bodyText ? JSON.parse(bodyText) : {};
    } catch {
      body = { message: bodyText.slice(0, 500) };
    }

    if (!response.ok) {
      const detail = body.detail || body.error || body.message || response.statusText || 'No error details were returned.';
      throw new Error(`HTTP ${response.status}: ${detail}`);
    }
    return body;
  }

  async function waitForResearchJob(statusUrl) {
    while (true) {
      await new Promise(resolve => setTimeout(resolve, 2500));
      const response = await fetch(statusUrl, { cache: 'no-store' });
      const job = await parseApiResponse(response);
      if (job.status === 'completed') return job.result;
      if (job.status === 'failed') throw new Error(job.error || 'The research job failed.');
    }
  }

  function animateSteps() {
    const steps = [1, 2, 3, 4, 5, 6, 7];
    steps.forEach(i => {
      const el = document.getElementById(`step-${i}`);
      if (el) el.classList.remove('active', 'completed');
    });

    let current = 1;
    return setInterval(() => {
      steps.forEach(i => {
        const el = document.getElementById(`step-${i}`);
        if (el) el.classList.remove('active');
      });
      const currentStep = document.getElementById(`step-${current}`);
      if (currentStep) currentStep.classList.add('active');
      current = current % steps.length + 1;
    }, 1200);
  }

  function displayResults(data) {
    for (let i = 1; i <= 7; i++) {
      const step = document.getElementById(`step-${i}`);
      if (step) {
        step.classList.remove('active');
        step.classList.add('completed');
      }
    }

    const statusPill = document.getElementById('status-pill');
    const projectStatus = String(data.status || 'INCOMPLETE').toUpperCase();
    const statusLabels = {
      COMPLETED: '✓ STATUS: COMPLETED',
      COMPLETED_WITH_LIMITATIONS: '⚠ COMPLETED WITH LIMITATIONS',
      INCOMPLETE: '⚠ STATUS: INCOMPLETE',
      FAILED: '✕ STATUS: FAILED'
    };
    statusPill.textContent = statusLabels[projectStatus] || `STATUS: ${projectStatus.replaceAll('_', ' ')}`;
    statusPill.classList.remove('badge-emerald', 'badge-cyan');
    statusPill.classList.add(projectStatus === 'COMPLETED' ? 'badge-emerald' : 'badge-cyan');

    // Metrics
    document.getElementById('metric-validated').textContent = data.validated_sources_count || 0;
    const reviewSources = data.review_sources || (data.rejected_sources || []).filter(
      source => source.validation_status === 'Needs review'
    );
    const hardRejectedSources = (data.rejected_sources || []).filter(
      source => source.validation_status !== 'Needs review'
    );
    const flaggedSources = [...new Map(
      [...hardRejectedSources, ...reviewSources].map(source => [
        source.id || source.source_link || source.source_title,
        source
      ])
    ).values()];
    const reviewSourceKeys = new Set(reviewSources.map(
      source => source.id || source.source_link || source.source_title
    ));
    const hardRejectedCount = hardRejectedSources.length;
    const reviewCandidateCount = reviewSources.length;
    document.getElementById('metric-rejected').textContent = flaggedSources.length;
    document.getElementById('metric-rejected-detail').textContent =
      `${hardRejectedCount} rejected · ${reviewCandidateCount} review candidate${reviewCandidateCount === 1 ? '' : 's'}`;
    const totalInsights = (data.insights || []).length;
    const totalVerbatims = (data.verbatims || []).filter(
      item => item.match_verified === true && item.verification_status === 'verified_exact_match'
    ).length;
    document.getElementById('metric-verbatims').textContent = totalVerbatims;
    
    const qcScore = data.qc_report?.completion_score_percent ?? 0;
    document.getElementById('metric-coverage').textContent = `${qcScore}%`;
    document.getElementById('metric-coverage').title =
      `QC pass rate: ${data.qc_report?.qc_checks_passed ?? 0} passed, ${data.qc_report?.qc_checks_failed ?? 0} failed, and ${data.qc_report?.qc_checks_review ?? 0} need review out of ${data.qc_report?.qc_checks_total ?? 0} applicable checks. Review remains in the denominator; research coverage gaps are separate.`;

    // Counts on tab buttons
    document.getElementById('count-sources').textContent = data.validated_sources_count || 0;
    document.getElementById('count-rejected').textContent = flaggedSources.length;

    // Headings
    document.getElementById('results-heading').textContent = `Research Monograph: ${data.topic} (${data.countries.join(', ')})`;
    const rules = data.validation_rules || {};
    document.getElementById('results-subheading').textContent =
      `Project Reference: ${data.project_id} | Publication from ${rules.min_publication_year ?? 'configured year'} | Preferred data period ${rules.data_period_start_year ?? '—'}–${rules.data_period_end_year ?? '—'}`;
    
    // Download Links (fallback to static files if API fails)
    const linkExcel = document.getElementById('link-excel');
    const linkWord = document.getElementById('link-word');
    const origin = window.location.origin;
    // Prefer API route, but static files are guaranteed to exist in OUTPUT_DIR
    const excelUrl = data.excel_download_url || `/download/${data.excel_filename}`;
    const wordUrl  = data.docx_download_url  || `/download/${data.docx_filename}`;
    linkExcel.href = `${origin}${excelUrl}`;
    linkWord.href = `${origin}${wordUrl}`;
    // Ensure the saved file uses the correct name
    if (data.excel_filename) linkExcel.setAttribute('download', data.excel_filename);
    if (data.docx_filename) linkWord.setAttribute('download', data.docx_filename);

    // 1. Populate Validated Sources Table with pagination
    // Store sources globally for pagination
    window._sourcesData = (data.validated_sources || []).filter(
      source => source.validation_status !== 'Needs review'
    );
    const PAGE_SIZE = 10; // rows per page
    let currentPage = 1;
    const totalPages = Math.max(1, Math.ceil(window._sourcesData.length / PAGE_SIZE));
    const sourcesBody = document.getElementById('sources-table-body');
    const prevBtn = document.getElementById('sources-prev');
    const nextBtn = document.getElementById('sources-next');
    const pageInfo = document.getElementById('sources-page-info');

    function renderSourcesPage(page) {
      if (page < 1) page = 1;
      if (page > totalPages) page = totalPages;
      currentPage = page;
      sourcesBody.innerHTML = '';
      const startIdx = (currentPage - 1) * PAGE_SIZE;
      const pageItems = window._sourcesData.slice(startIdx, startIdx + PAGE_SIZE);
      pageItems.forEach((s, idx) => {
        const tr = document.createElement('tr');
        const isReview = s.validation_status === 'Needs review';
        const badgeClass = isReview ? 'tag-review' : 'tag-passed';
        const statusText = isReview ? 'Needs Review' : 'Verified Eligible';
        const displayIdx = startIdx + idx + 1;
        tr.innerHTML = `
          <td style="color: var(--text-dim);">${displayIdx}</td>
          <td>
            <div style="font-weight: 600;">${escapeHtml(s.source_title)}</div>
            <div style="font-size: 11px; color: var(--text-muted);">${escapeHtml(s.name_of_source)}</div>
          </td>
          <td><span class="tag-badge" style="background: rgba(255,255,255,0.06);">${s.publication_year || 'Unknown'}</span></td>
          <td title="${escapeHtml([s.data_period_evidence, s.data_period_location, s.source_link].filter(Boolean).join(' | '))}">
            <span style="font-size: 12px; color: var(--text-muted);">${escapeHtml(s.data_period || 'Unknown')}</span>
            <div style="font-size: 10px; color: var(--text-dim);">${escapeHtml(s.data_period_status || 'Unknown')}</div>
          </td>
          <td><span style="font-size: 12px; color: var(--accent-cyan);">${escapeHtml((s.sections_covered || []).join(', '))}</span></td>
          <td><span class="tag-badge ${badgeClass}">${statusText}</span></td>
          <td><a href="${s.source_link}" target="_blank" style="color: #60A5FA; text-decoration: none; font-size: 12px;">Link ↗</a></td>
        `;
        sourcesBody.appendChild(tr);
      });
      pageInfo.textContent = `Page ${currentPage} of ${totalPages}`;
      prevBtn.disabled = currentPage === 1;
      nextBtn.disabled = currentPage === totalPages;
    }

    // Initial render
    renderSourcesPage(1);
    // Attach handlers
    if (prevBtn && nextBtn) {
      prevBtn.addEventListener('click', () => renderSourcesPage(currentPage - 1));
      nextBtn.addEventListener('click', () => renderSourcesPage(currentPage + 1));
    }

    // 2. Show one insight/verbatim pair per source in the website UI.
    // The spreadsheet exporter keeps the full multi-finding strings on each source.
    const firstInsightBySource = new Map();
    (data.insights || []).forEach(insight => {
      if (insight.source_id && !firstInsightBySource.has(insight.source_id)) {
        firstInsightBySource.set(insight.source_id, insight);
      }
    });
    const verbatimsBySource = new Map();
    (data.verbatims || []).forEach(verbatim => {
      if (!verbatim.source_id) return;
      if (!verbatimsBySource.has(verbatim.source_id)) verbatimsBySource.set(verbatim.source_id, []);
      verbatimsBySource.get(verbatim.source_id).push(verbatim);
    });
    window._insightsData = (data.validated_sources || []).map(source => {
      const insight = firstInsightBySource.get(source.id) || null;
      const sourceVerbatims = verbatimsBySource.get(source.id) || [];
      const matchingVerbatim = sourceVerbatims.find(v => insight && v.section === insight.section) || sourceVerbatims[0] || null;
      return { source, insight, verbatim: matchingVerbatim };
    });
    // The UI still shows one insight/quote pair per source, but this badge reports
    // the full finding totals included in the spreadsheet.
    document.getElementById('count-insights').textContent = `${totalInsights}`;
    const PAGE_SIZE_INSIGHTS = 10; // rows per page
    let currentInsightsPage = 1;
    const totalInsightsPages = Math.max(1, Math.ceil(window._insightsData.length / PAGE_SIZE_INSIGHTS));
    const insightsBody = document.getElementById('insights-table-body');
    const insightsPrevBtn = document.getElementById('insights-prev');
    const insightsNextBtn = document.getElementById('insights-next');
    const insightsPageInfo = document.getElementById('insights-page-info');

    function renderInsightsPage(page) {
      if (page < 1) page = 1;
      if (page > totalInsightsPages) page = totalInsightsPages;
      currentInsightsPage = page;
      insightsBody.innerHTML = '';
      const startIdx = (currentInsightsPage - 1) * PAGE_SIZE_INSIGHTS;
      const pageItems = window._insightsData.slice(startIdx, startIdx + PAGE_SIZE_INSIGHTS);
      pageItems.forEach(({ source, insight, verbatim }) => {
        const tr = document.createElement('tr');
        const verificationText = verbatim
          ? (verbatim.match_verified ? '✓ Exact Match' : 'Review Quote')
          : 'No Quote';
        const verificationClass = verbatim?.match_verified ? 'tag-passed' : 'tag-review';
        tr.innerHTML = `
          <td>${source.source_link ? `<a href="${escapeHtml(source.source_link)}" target="_blank" rel="noopener noreferrer" style="color: var(--text-main); text-decoration: none; font-weight: 600;">${escapeHtml(source.source_title)}</a>` : `<span style="font-weight: 600;">${escapeHtml(source.source_title)}</span>`}</td>
          <td><span class="tag-badge" style="background: rgba(99,102,241,0.15); color: #818CF8;">${escapeHtml(insight?.section || (source.sections_covered || [])[0] || 'General')}</span></td>
          <td><div style="font-size: 13px;">${escapeHtml(insight?.insight_text || 'No insight extracted for this source.')}</div></td>
          <td><div style="font-size: 12px; color: var(--text-muted); font-style: italic;">${escapeHtml(verbatim?.exact_quote || 'No verbatim quote extracted for this source.')}</div></td>
          <td><span class="tag-badge ${verificationClass}">${verificationText}</span></td>
        `;
        insightsBody.appendChild(tr);
      });
      insightsPageInfo.textContent = `Page ${currentInsightsPage} of ${totalInsightsPages}`;
      insightsPrevBtn.disabled = currentInsightsPage === 1;
      insightsNextBtn.disabled = currentInsightsPage === totalInsightsPages;
    }

    // Initial render and attach handlers
    renderInsightsPage(1);
    if (insightsPrevBtn && insightsNextBtn) {
      insightsPrevBtn.addEventListener('click', () => renderInsightsPage(currentInsightsPage - 1));
      insightsNextBtn.addEventListener('click', () => renderInsightsPage(currentInsightsPage + 1));
    }

    // 3. Populate rejected sources and data-period review candidates
    const rejectedBody = document.getElementById('rejected-table-body');
    rejectedBody.innerHTML = '';
    flaggedSources.forEach(r => {
      const tr = document.createElement('tr');
      const reviewKey = r.id || r.source_link || r.source_title;
      const reviewCandidate = reviewSourceKeys.has(reviewKey) || r.validation_status === 'Needs review';
      tr.innerHTML = `
        <td style="font-weight: 600;">${escapeHtml(r.source_title)}</td>
        <td style="color: var(--text-muted); font-size: 12px;">${escapeHtml(r.name_of_source)}</td>
        <td><span class="tag-badge tag-rejected">${r.publication_year || 'Unknown'}</span></td>
        <td><span class="tag-badge ${reviewCandidate ? 'tag-review' : 'tag-rejected'}">${reviewCandidate ? 'Review candidate' : 'Rejected'}</span></td>
        <td>${r.source_link ? `<a href="${escapeHtml(r.source_link)}" target="_blank" rel="noopener noreferrer" style="color: var(--accent-cyan); text-decoration: none; font-size: 12px;">Open source ↗</a>` : '<span style="color: var(--text-dim); font-size: 12px;">Unavailable</span>'}</td>
      `;
      rejectedBody.appendChild(tr);
    });

    // 4. Populate QC Coverage Matrix Table
    const qcBody = document.getElementById('qc-table-body');
    qcBody.innerHTML = '';
    const matrix = data.coverage_matrix || {};
    Object.keys(matrix).forEach(key => {
      const count = matrix[key];
      const isSatisfied = count > 0;
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="font-weight: 600;">${escapeHtml(key)}</td>
        <td><span class="tag-badge" style="background: rgba(255,255,255,0.08);">${count} sources</span></td>
        <td><span class="tag-badge ${isSatisfied ? 'tag-passed' : 'tag-rejected'}">${isSatisfied ? '✓ Satisfied' : '⚠ Missing Gap'}</span></td>
      `;
      qcBody.appendChild(tr);
    });

    const yearCoverageBody = document.getElementById('year-coverage-table-body');
    yearCoverageBody.innerHTML = '';
    const yearCoverage = data.year_wise_coverage || {};
    Object.entries(yearCoverage).forEach(([key, cell]) => {
      const covered = cell.status === 'Covered';
      const partial = cell.status === 'Partial evidence';
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="font-weight: 600;">${escapeHtml(key)}</td>
        <td><span class="tag-badge" style="background: rgba(255,255,255,0.08);">${cell.verified_sources_count || 0}</span></td>
        <td><span class="tag-badge" style="background: rgba(255,255,255,0.08);">${cell.partial_sources_count || 0}</span></td>
        <td><span class="tag-badge ${covered ? 'tag-passed' : 'tag-review'}">${covered ? '✓ Verified coverage' : (partial ? 'Partial evidence' : '⚠ Missing year')}</span></td>
      `;
      yearCoverageBody.appendChild(tr);
    });

    // 5. Populate Console Log
    const logBox = document.getElementById('console-log-box');
    logBox.innerHTML = '';
    (data.audit_trail || []).forEach(log => {
      const line = document.createElement('div');
      line.className = 'console-line';
      line.textContent = `> ${log}`;
      logBox.appendChild(line);
    });

    // Reveal results panel smoothly
    resultsPanel.style.display = 'block';
    resultsPanel.scrollIntoView({ behavior: 'smooth' });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
});
