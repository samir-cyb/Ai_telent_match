/* ================================================================
   AI TALENT MATCH — Poster Charts  (Chart.js 4.x)
   ================================================================ */
'use strict';

const C = {
  bg:      '#030c1a',
  accent:  '#38bdf8',
  accent2: '#818cf8',
  green:   '#22c55e',
  yellow:  '#f59e0b',
  red:     '#ef4444',
  purple:  '#a855f7',
  muted:   '#475569',
  text:    '#e2e8f0',
  border:  '#153060',
};

Chart.defaults.color           = C.muted;
Chart.defaults.borderColor     = C.border;
Chart.defaults.font.family     = "'Inter', sans-serif";
Chart.defaults.font.size       = 10;
Chart.defaults.plugins.legend.labels.boxWidth = 10;
Chart.defaults.plugins.legend.labels.padding  = 8;

/* ── TRUST SCORES ── */
function initTrust() {
  const el = document.getElementById('trustChart');
  if (!el) return;
  new Chart(el, {
    type: 'bar',
    data: {
      labels: ['Karim', 'Rahim', 'Tasnim', 'Mehedi', 'Nadia'],
      datasets: [{
        data: [94, 84, 71, 68, 42],
        backgroundColor: ['#16a34a','#16a34a','#b45309','#b45309','#b91c1c'],
        borderColor:     ['#22c55e','#22c55e','#f59e0b','#f59e0b','#ef4444'],
        borderWidth: 1.5,
        borderRadius: 5,
        borderSkipped: false,
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: c => ` ${c.raw}/100` } }
      },
      scales: {
        x: { min:0, max:100, grid:{ color:'rgba(21,48,96,0.4)' }, ticks:{ color:C.muted, font:{size:9} } },
        y: { grid:{ display:false }, ticks:{ color:C.text, font:{size:10,weight:'600'} } }
      }
    }
  });
}

/* ── AGENT DOUGHNUT ── */
function initAgent() {
  const el = document.getElementById('agentChart');
  if (!el) return;
  new Chart(el, {
    type: 'doughnut',
    data: {
      labels: ['Rejected (60%)', 'Under Review (33%)', 'Shortlisted (7%)'],
      datasets: [{
        data: [9, 5, 1],
        backgroundColor: ['rgba(239,68,68,0.8)', 'rgba(245,158,11,0.8)', 'rgba(34,197,94,0.8)'],
        borderColor: ['#ef4444','#f59e0b','#22c55e'],
        borderWidth: 2, hoverOffset: 8,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      cutout: '58%',
      plugins: {
        legend: { position:'bottom', labels:{ color:C.text, font:{size:9.5} } },
        tooltip: { callbacks: { label: c => ` ${c.label}: ${c.raw} of 15 runs` } }
      }
    }
  });
}

/* ── RL WEIGHTS GROUPED BAR ── */
function initRL() {
  const el = document.getElementById('rlChart');
  if (!el) return;
  new Chart(el, {
    type: 'bar',
    data: {
      labels: ['CGPA','Skills','Experience','Projects','Activity','Trust'],
      datasets: [
        {
          label: 'Uniform (Before)',
          data: [0.200, 0.200, 0.200, 0.150, 0.100, 0.150],
          backgroundColor: 'rgba(56,189,248,0.20)',
          borderColor: C.accent, borderWidth: 1.5, borderRadius: 3,
        },
        {
          label: '▲ After Hire Signal',
          data: [0.260, 0.170, 0.210, 0.160, 0.130, 0.180],
          backgroundColor: 'rgba(34,197,94,0.22)',
          borderColor: C.green, borderWidth: 1.5, borderRadius: 3,
        },
        {
          label: '▼ After Reject Signal',
          data: [0.180, 0.230, 0.190, 0.140, 0.090, 0.130],
          backgroundColor: 'rgba(239,68,68,0.20)',
          borderColor: C.red, borderWidth: 1.5, borderRadius: 3,
        }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position:'bottom', labels:{ color:C.text, font:{size:9} } } },
      scales: {
        x: { grid:{ color:'rgba(21,48,96,0.3)' }, ticks:{ color:C.muted, font:{size:9} } },
        y: {
          min:0, max:0.34,
          grid:{ color:'rgba(21,48,96,0.3)' },
          ticks:{ color:C.muted, font:{size:9}, callback: v=>(v*100).toFixed(0)+'%' }
        }
      }
    }
  });
}

/* ── PIPELINE TIMING ── */
function initPipeline() {
  const el = document.getElementById('pipelineChart');
  if (!el) return;
  new Chart(el, {
    type: 'bar',
    data: {
      labels: ['Profile Load','AI Match (1 job)','Score All 8 Jobs','Recruit Agent','Interview Gen','Score Answer','Full Analysis'],
      datasets: [{
        data: [5, 17, 94, 70, 1400, 700, 2100],
        backgroundColor: [C.green, C.green, C.accent, C.accent, C.yellow, C.yellow, C.red],
        borderRadius: 4, borderSkipped: false,
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: c => c.raw>=1000 ? ` ${(c.raw/1000).toFixed(1)}s` : ` ${c.raw}ms` }
        }
      },
      scales: {
        x: {
          type: 'logarithmic',
          grid:{ color:'rgba(21,48,96,0.4)' },
          ticks:{ color:C.muted, font:{size:8.5}, callback: v=> v>=1000?`${v/1000}s`:`${v}ms` }
        },
        y: { grid:{ display:false }, ticks:{ color:C.muted, font:{size:8.5} } }
      }
    }
  });
}

/* ── SKILL GAP ── */
function initSkillGap() {
  const el = document.getElementById('skillGapChart');
  if (!el) return;
  new Chart(el, {
    type: 'bar',
    data: {
      labels: ['Python','SQL','Docker','Excel','REST API','Git'],
      datasets: [
        {
          label: 'Market Demand',
          data: [2, 2, 2, 2, 2, 2],
          backgroundColor: 'rgba(239,68,68,0.25)',
          borderColor: C.red, borderWidth: 1.5, borderRadius: 4,
        },
        {
          label: 'Student Supply',
          data: [1, 1, 1, 0, 1, 1],
          backgroundColor: 'rgba(56,189,248,0.22)',
          borderColor: C.accent, borderWidth: 1.5, borderRadius: 4,
        }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position:'bottom', labels:{ color:C.text, font:{size:9} } } },
      scales: {
        x: { grid:{ color:'rgba(21,48,96,0.3)' }, ticks:{ color:C.muted, font:{size:9} } },
        y: { min:0, max:3, grid:{ color:'rgba(21,48,96,0.3)' }, ticks:{ color:C.muted, font:{size:9}, stepSize:1 } }
      }
    }
  });
}

/* ── HEATMAP TABLE ── */
function buildHeatmap() {
  const students = ['Karim','Rahim','Tasnim','Mehedi','Nadia'];
  const jobs     = ['Django Dev','ML Eng.','Data Analyst','Frontend','Full Stack','Embedded','Marketing','Biz Analyst'];
  const scores   = [
    [49,70,68,38,52,43,67,70],
    [63,58,47,55,68,41,62,65],
    [30,30,38,30,30,36,72,65],
    [34,34,34,29,33,63,48,48],
    [14,19,19,39,22, 7,15,18],
  ];

  function cell(v) {
    if (v>=65) return { bg:'rgba(34,197,94,0.30)',  fg:'#bbf7d0' };
    if (v>=50) return { bg:'rgba(56,189,248,0.25)', fg:'#bae6fd' };
    if (v>=35) return { bg:'rgba(245,158,11,0.22)', fg:'#fde68a' };
    return            { bg:'rgba(239,68,68,0.18)',  fg:'#fca5a5' };
  }

  const thead = document.getElementById('hmHead');
  const tbody = document.getElementById('hmBody');
  if (!thead || !tbody) return;

  // header row
  const hr = document.createElement('tr');
  hr.innerHTML = '<th></th>';
  jobs.forEach(j => {
    const th = document.createElement('th');
    th.innerHTML = `<div class="col-lbl">${j}</div>`;
    hr.appendChild(th);
  });
  thead.appendChild(hr);

  // data rows
  students.forEach((s, i) => {
    const tr = document.createElement('tr');
    const th = document.createElement('th');
    th.className = 'rn'; th.textContent = s;
    tr.appendChild(th);
    scores[i].forEach(v => {
      const c = cell(v);
      const td = document.createElement('td');
      td.textContent = v;
      td.style.cssText = `background:${c.bg};color:${c.fg};`;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

/* ── PDF DOWNLOAD ── */
async function downloadPDF() {
  const btn = document.getElementById('dlBtn');
  const prog = document.getElementById('dlProg');
  const hint = document.getElementById('dlHint');

  btn.disabled = true;
  btn.textContent = '⏳ Generating…';
  if (prog) { prog.classList.add('show'); hint && hint.classList.remove('show'); }

  try {
    // Load libraries dynamically
    await Promise.all([
      loadScript('https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js'),
      loadScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js')
    ]);

    const poster = document.querySelector('.poster');

    // Temporarily expand to full design width for capture
    poster.style.transform = 'none';

    const canvas = await html2canvas(poster, {
      scale: 2,
      useCORS: true,
      allowTaint: true,
      backgroundColor: '#030c1a',
      logging: false,
      windowWidth: poster.scrollWidth,
      windowHeight: poster.scrollHeight,
    });

    const { jsPDF } = window.jspdf;
    // 3ft × 4ft in mm = 914.4 × 1219.2
    const pdf = new jsPDF({ unit:'mm', format:[914.4, 1219.2], orientation:'portrait' });
    const imgData = canvas.toDataURL('image/jpeg', 0.95);
    pdf.addImage(imgData, 'JPEG', 0, 0, 914.4, 1219.2);
    pdf.save('AI_Talent_Match_Poster_3x4ft.pdf');

  } catch(e) {
    alert('PDF generation failed: ' + e.message + '\n\nUse Print → Save as PDF instead.');
    console.error(e);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '⬇️ Download PDF (3×4 ft)';
    if (prog) prog.classList.remove('show');
  }
}

function printPoster() {
  window.print();
}

function loadScript(src) {
  return new Promise((res, rej) => {
    if (document.querySelector(`script[src="${src}"]`)) return res();
    const s = document.createElement('script');
    s.src = src; s.onload = res; s.onerror = rej;
    document.head.appendChild(s);
  });
}

function toggleHint() {
  document.getElementById('dlHint').classList.toggle('show');
}

/* ── INIT ── */
window.addEventListener('DOMContentLoaded', () => {
  buildHeatmap();
  initTrust();
  initAgent();
  initRL();
  initPipeline();
  initSkillGap();
});
