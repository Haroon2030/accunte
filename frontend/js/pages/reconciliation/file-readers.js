'use strict';

/* =====================================================================
   File readers: Excel/CSV, Word, PDF (text or scanned) and photos (OCR).
   Heavy libraries load only when a file of that type is chosen.
   ===================================================================== */
const RC_LIBS = {
  xlsx: 'vendor/xlsx.full.min.js',
  mammoth: 'vendor/mammoth.browser.min.js',
  pdf: 'vendor/pdf.min.js',
  ocr: 'https://cdnjs.cloudflare.com/ajax/libs/tesseract.js/5.0.5/tesseract.min.js'
};
const rcLoaded = {};
function rcLoad(name) {
  if (rcLoaded[name]) return rcLoaded[name];
  rcLoaded[name] = new Promise(function (res, rej) {
    const s = document.createElement('script');
    s.src = RC_LIBS[name];
    s.onload = function () { res(); };
    s.onerror = function () { delete rcLoaded[name]; rej(new Error('تعذّر تحميل مكتبة القراءة (' + name + '). تأكد من الاتصال بالإنترنت.')); };
    document.head.appendChild(s);
  });
  return rcLoaded[name];
}
function rcExt(f) { const m = /\.([a-z0-9]+)$/i.exec(f.name); return m ? m[1].toLowerCase() : ''; }
function rcSplitText(lines) {
  const rows = lines.map(function (l) { return String(l).replace(/\r/g, ''); }).filter(function (l) { return l.trim(); });
  const hasGap = rows.some(function (l) { return /\t|\s{2,}|\||;/.test(l); });
  return rows.map(function (l) {
    return (hasGap ? l.trim().split(/\t|\s{2,}|\s*[|;]\s*/) : l.trim().split(',')).map(function (c) { return c.trim(); });
  });
}
function rcWithTimeout(promise, ms, msg) {
  return Promise.race([promise, new Promise(function (_, rej) { setTimeout(function () { rej(new Error(msg)); }, ms); })]);
}

/* text items from pdf.js often come one glyph at a time (Arabic presentation forms, split runs). Join the pieces that touch
   on the same line into words, normalise the forms (NFKC) and split a side label off an amount ("58,650.00 مدين") */
const RC_SIDE_RE = /^(مدين|دائن)$/;
function rcMergeRuns(items) {
  /* some fonts put NUL or other control characters between the glyphs: they carry no text */
  const sorted = items.map(function (it) { return Object.assign({}, it, { str: it.str.normalize('NFKC').replace(/[\u0000-\u001F\u007F\uFEFF]/g, '') }); })
    .filter(function (it) { return it.str.trim(); })
    .sort(function (a, b) { return a.y - b.y || a.x0 - b.x0; });
  const runs = [];
  sorted.forEach(function (it) {
    const run = runs[runs.length - 1];
    if (run && Math.abs(it.y - run.y) <= Math.max(it.h, 6) * 0.5) run.items.push(it);
    else runs.push({ y: it.y, items: [it] });
  });
  const arabic = /[؀-ۿ]/;
  const out = [];
  runs.forEach(function (run) {
    /* a run is only ever one word: pieces that touch are glued, and a gap wider than a space starts a new word */
    const groups = [];
    /* only pieces of one word glue: same script, no digits, touching (a column edge or a number always starts a new cell) */
    const scriptOf = function (t) { return /\d/.test(t) ? 'dg' : arabic.test(t) ? 'ar' : /[A-Za-z]/.test(t) ? 'la' : 'ot'; };
    run.items.forEach(function (it) {
      const g = groups[groups.length - 1];
      const sc = scriptOf(it.str);
      if (g && (sc === 'ar' || sc === 'la') && g.sc === sc && it.x0 - g.x1 <= Math.max(it.h, 6) * 0.12) g.items.push(it), g.x1 = Math.max(g.x1, it.x1);
      else groups.push({ items: [it], x0: it.x0, x1: it.x1, sc: sc });
    });
    groups.forEach(function (g) {
      const parts = g.items.slice().sort(function (a, b) { return g.sc === 'ar' ? b.x1 - a.x1 : a.x0 - b.x0; });
      let str = parts.map(function (i) { return i.str; }).join('').replace(/[\uE000-\uF8FF]/g, '').replace(/\s+/g, ' ').trim();
      str = str.replace(/^(-?[\d,]+\.\d{2})\s*(مدين|دائن)$/, '$1');
      if (!str) return;
      out.push({ str: str, x0: g.x0, x1: g.x1, y: run.y, h: Math.max.apply(null, g.items.map(function (i) { return i.h; })) });
    });
  });
  return out;
}

/* text items {str,x0,x1,y,h} (from a PDF page or OCR) -> table rows aligned to the header columns */
function rcItemsToRows(items) {
  if (!items.length) return [];
  const hs = items.map(function (i) { return i.h; }).sort(function (a, b) { return a - b; });
  const medH = Math.max(hs[Math.floor(hs.length / 2)] || 10, 6);
  const sorted = items.slice().sort(function (a, b) { return a.y - b.y || a.x0 - b.x0; });
  const lines = [];
  sorted.forEach(function (it) {
    const last = lines[lines.length - 1];
    if (last && Math.abs(it.y - last.y) <= medH * 0.6) { last.items.push(it); last.y = (last.y * (last.items.length - 1) + it.y) / last.items.length; }
    else lines.push({ y: it.y, items: [it] });
  });
  const arabic = /[؀-ۿ]/;
  const cellsOf = function (line) {
    const its = line.items.slice().sort(function (a, b) { return a.x0 - b.x0; });
    const groups = [];
    its.forEach(function (it) {
      const g = groups[groups.length - 1];
      if (g && it.x0 - g.x1 < medH * 0.9) { g.items.push(it); g.x1 = Math.max(g.x1, it.x1); }
      else groups.push({ items: [it], x0: it.x0, x1: it.x1 });
    });
    return groups.map(function (g) {
      const joined = g.items.map(function (i) { return i.str; }).join(' ');
      const text = arabic.test(joined) ? g.items.slice().sort(function (a, b) { return b.x1 - a.x1; }).map(function (i) { return i.str; }).join(' ') : joined;
      return { t: text, x0: g.x0, x1: g.x1 };
    });
  };
  const cellLines = lines.map(cellsOf);
  const plain = cellLines.map(function (cl) { return cl.map(function (c) { return c.t; }); });
  const hd = rcFindHeader(plain);
  if (!hd) return plain;
  const cols = cellLines[hd.idx].map(function (c) { return (c.x0 + c.x1) / 2; });
  return cellLines.map(function (cl, li) {
    if (li <= hd.idx) return plain[li];
    const row = cols.map(function () { return ''; });
    cl.forEach(function (c) {
      const mid = (c.x0 + c.x1) / 2;
      let bi = 0, bd = 1e12;
      cols.forEach(function (cx, ci) { const d = Math.abs(cx - mid); if (d < bd) { bd = d; bi = ci; } });
      row[bi] = row[bi] ? row[bi] + ' ' + c.t : c.t;
    });
    return row;
  });
}


/* ---------------------------------------------------------------------
   Account-statement PDFs (text layer): one entry = a "main" line carrying a date and money, followed by
   continuation lines (wrapped description, long reference numbers). Columns come from where the money
   sits on the page, named by the header words above it (Debit / Credit / Balance, مدين / دائن / الرصيد).
   Returns table rows (header first) or null when the page does not look like a statement.
   --------------------------------------------------------------------- */
const RC_DATE_TOK = /^(\d{1,2}[\/.\-]\d{1,2}[\/.\-]\d{4}|\d{4}[\/.\-]\d{1,2}[\/.\-]\d{1,2})$/;
/* amounts carry 2 decimals, or 3 where the ledger keeps fils-level precision (1,107,019.480) */
const RC_MONEY_TOK = /^\(?-?\d{1,3}(?:,\d{3})*\.\d{2,3}\)?-?$|^-?\d+\.\d{2,3}$/;
const RC_INT_TOK = /^\d{3,}$/;
const RC_OPEN_TOK = /فتتاحي|افتتاح|opening|الرصيد السابق|رصيد سابق|رصيد مدور|رصيد مرحل|previous balance|brought forward|b\/f/i;
/* the summary lines (net movement, closing balance) are words that may come out in either order (RTL) */
const RC_TOTAL_TOK = /(صافي\s*الحركة|الحركة\s*صافي|الرصيد\s*الختامي|الختامي\s*الرصيد|رصيد ختامي|الرصيد النهائي|closing balance|net movement)/i;
const RC_STOP_TOK = /صافي|الحركة|الختامي|الرصيد الختامي|إجمالي العمليات|اجمالي العمليات|إجمالي|اجمالي|total|طبع بواسطة|تاريخ التقرير|المدير العام|المحاسب|يعتبر هذا الكشف|الرصيد الحالي|الرصيد الختامي|prepared by|check by|ملاحظة|مﻼحظة/i;
function rcPdfStatement(items) {
  if (items.length < 15) return null;
  const hs = items.map(function (i) { return i.h; }).sort(function (a, b) { return a - b; });
  const medH = Math.max(hs[Math.floor(hs.length / 2)] || 10, 6);
  const sorted = items.slice().sort(function (a, b) { return a.y - b.y || a.x0 - b.x0; });
  const lines = [];
  sorted.forEach(function (it) {
    const last = lines[lines.length - 1];
    if (last && Math.abs(it.y - last.y) <= medH * 0.6) { last.items.push(it); last.y = (last.y * (last.items.length - 1) + it.y) / last.items.length; }
    else lines.push({ y: it.y, items: [it] });
  });
  const kind = function (it) {
    if (RC_DATE_TOK.test(it.str)) return 'date';
    if (RC_MONEY_TOK.test(it.str)) return 'money';
    if (RC_INT_TOK.test(it.str)) return 'int';
    if (RC_SIDE_RE.test(it.str)) return 'side';
    return 'text';
  };
  lines.forEach(function (ln) {
    ln.items.sort(function (a, b) { return a.x0 - b.x0; });
    ln.items.forEach(function (it) { it.k = kind(it); });
    ln.page = Math.floor(ln.y / 10000);
    ln.text = ln.items.map(function (i) { return i.str; }).join(' ');
    ln.main = ln.items.some(function (i) { return i.k === 'date'; }) && ln.items.some(function (i) { return i.k === 'money'; }) && !RC_TOTAL_TOK.test(ln.text);
    ln.open = !ln.main && RC_OPEN_TOK.test(ln.text) && ln.items.some(function (i) { return i.k === 'money'; });
  });
  const entries = lines.filter(function (l) { return l.main || l.open; });
  if (entries.filter(function (l) { return l.main; }).length < 5) return null;

  /* money columns: right edges that repeat down the page */
  const cl = [];
  entries.forEach(function (ln) {
    ln.items.forEach(function (it) {
      if (it.k !== 'money') return;
      let c = cl.filter(function (x) { return Math.abs(x.x1 - it.x1) <= 12; })[0];
      if (!c) { c = { x1: it.x1, cs: [], n: 0 }; cl.push(c); }
      c.x1 = (c.x1 * c.n + it.x1) / (c.n + 1); c.n++; c.cs.push((it.x0 + it.x1) / 2);
    });
  });
  /* a short statement can have a credit column with only two entries: a money column needs two values to count */
  const minN = Math.max(2, Math.round(entries.length * 0.05));
  const cols = cl.filter(function (c) { return c.n >= minN; }).sort(function (a, b) { return a.x1 - b.x1; });
  if (cols.length < 2 || cols.length > 4) return null;
  cols.forEach(function (c) { c.c = c.cs.reduce(function (t, v) { return t + v; }, 0) / c.cs.length; });

  /* header words above the first entry decide which column is debit / credit / balance */
  const firstIdx = lines.indexOf(entries[0]);
  const hdr = [];
  lines.slice(0, firstIdx).forEach(function (ln) {
    ln.items.forEach(function (it) {
      const w = it.str.split(/\s+/);
      w.forEach(function (t, wi) { hdr.push({ t: t.toLowerCase().replace(/[:.()]/g, ''), c: (it.x0 + it.x1) / 2 + (wi - (w.length - 1) / 2) * 6 }); });
    });
  });
  const DR = /^(debit|dr|مدين|منه)$/, CR = /^(credit|cr|دائن|له)$/, BAL = /^(balance|net|الرصيد|رصيد)$/;
  const rolled = cols.map(function (col) {
    const near = hdr.filter(function (h) { return Math.abs(h.c - col.c) <= 45; });
    const has = function (re) { return near.some(function (h) { return re.test(h.t); }); };
    const role = has(DR) ? 'debit' : has(CR) ? 'credit' : has(BAL) ? 'balance' : '';
    return { col: col, role: role };
  });
  /* a header word can be unreadable (some printers embed the font so the letters come out as symbols): when two of the three money columns are known, the third takes the remaining role */
  if (cols.length === 3) {
    const known = rolled.filter(function (q) { return q.role; }), blank = rolled.filter(function (q) { return !q.role; });
    if (known.length === 2 && blank.length === 1 && known[0].role !== known[1].role) {
      const left = ['debit', 'credit', 'balance'].filter(function (r) { return known.every(function (q) { return q.role !== r; }); })[0];
      blank[0].role = left;
    }
  }
  const roleOf = function (r) { const x = rolled.filter(function (q) { return q.role === r; }); return x.length === 1 ? x[0].col : null; };
  const colDr = roleOf('debit'), colCr = roleOf('credit'), colBal = roleOf('balance');
  if (!(colDr && colCr) && !colBal) return null;
  const colOf = function (it) {
    const c = (it.x0 + it.x1) / 2;
    let best = null, bd = 1e9;
    cols.forEach(function (q) { const d = Math.min(Math.abs(q.c - c), Math.abs(q.x1 - it.x1)); if (d < bd) { bd = d; best = q; } });
    return bd <= 40 ? best : null;
  };

  /* columns that repeat on every row (branch code, customer code, ...) are not document numbers */
  const seen = {};
  entries.forEach(function (ln) { const u = {}; ln.items.forEach(function (it) { if (it.k === 'int') u[it.str] = 1; }); Object.keys(u).forEach(function (k) { seen[k] = (seen[k] || 0) + 1; }); });
  const constant = function (v) { return seen[v] >= Math.max(6, Math.round(entries.length * 0.04)); };

  const rows = [['التاريخ', 'رقم المستند', 'البيان', 'مدين', 'دائن', 'الرصيد']];
  let cur = null, ended = false, pageSeen = -1;
  const arabic = /[؀-ۿ]/;
  /* debit and credit columns hold magnitudes: some systems print credits as negatives, which would flip the sign */
  const fmtMoney = function (t) { return t.replace(/[()\-]/g, ''); };
  const textOf = function (its) {
    const ar = its.some(function (i) { return arabic.test(i.str); });
    /* a page's total label (المجموع / الإجمالي) can sit on the same line as the last row: it is not part of the wording */
    return ((ar ? its.slice().sort(function (a, b) { return b.x1 - a.x1; }) : its).map(function (i) { return i.str; }).join(' ')).replace(/\s*(المجموع|الإجمالي|إجمالي|اجمالي)\s*$/, '');
  };
  const flush = function () {
    if (!cur) return;
    rows.push([cur.date, cur.docs.join(' '), cur.desc.join(' '), cur.dr, cur.cr, cur.bal]);
    cur = null;
  };
  lines.forEach(function (ln, li) {
    if (ln.main || ln.open) {
      flush(); ended = false; pageSeen = ln.page;
      cur = { date: '', docs: [], desc: [], dr: '', cr: '', bal: '' };
      const dates = ln.items.filter(function (i) { return i.k === 'date'; });
      if (dates.length) cur.date = dates[0].str;
      const text = [];
      ln.items.forEach(function (it) {
        if (it.k === 'money') {
          const c = colOf(it);
          if (!c) return;
          if (c === colDr) cur.dr = fmtMoney(it.str); else if (c === colCr) cur.cr = fmtMoney(it.str); else if (c === colBal) cur.bal = it.str;
        } else if (it.k === 'int') { if (!constant(it.str) && cur.docs.indexOf(it.str) === -1) cur.docs.push(it.str); }
        else if (it.k === 'text') text.push(it);
      });
      if (text.length) cur.desc.push(textOf(text));
      if (ln.open && !cur.dr && !cur.cr && cur.bal) {
        const v = parseFloat(cur.bal.replace(/[^\d.\-]/g, ''));
        if (v >= 0 && colDr) { cur.dr = cur.bal.replace('-', ''); } else if (colCr) cur.cr = cur.bal.replace('-', '');
      }
      if (ln.open && !/افتتاح/.test(cur.desc.join(' '))) cur.desc.unshift('رصيد افتتاحي');
      return;
    }
    if (!cur || ended || ln.page !== pageSeen) return;
    if (RC_STOP_TOK.test(ln.text)) { ended = true; return; }
    const text = [];
    ln.items.forEach(function (it) {
      if (it.k === 'int') { if (!constant(it.str) && cur.docs.indexOf(it.str) === -1) cur.docs.push(it.str); }
      else if (it.k === 'text') text.push(it);
    });
    if (text.length) cur.desc.push(textOf(text));
  });
  flush();
  return rows.length > 5 ? rows : null;
}

async function rcReadSheet(f, ext) {
  await rcLoad('xlsx');
  let wb;
  if (ext === 'csv' || ext === 'tsv' || ext === 'txt') {
    const buf = await f.arrayBuffer();
    let text;
    try { text = new TextDecoder('utf-8', { fatal: true }).decode(buf); } catch (e) { text = new TextDecoder('windows-1256').decode(buf); }
    wb = XLSX.read(text, { type: 'string', cellDates: true });
  } else wb = XLSX.read(await f.arrayBuffer(), { type: 'array', cellDates: true });
  let best = null;
  wb.SheetNames.forEach(function (n) {
    const rows = XLSX.utils.sheet_to_json(wb.Sheets[n], { header: 1, raw: true, defval: '', blankrows: true });
    const lay = rcAutoLayout(rows, 'company');
    const score = lay ? rcBuildLedger(rows, lay.idx, lay.map, 'company').lines.length : 0;
    if (!best || score > best.score || (score === best.score && rows.length > best.rows.length)) best = { rows: rows, name: n, score: score };
  });
  if (!best || !best.rows.length) throw new Error('الملف فارغ.');
  let formulas = 0, emptyF = 0;
  const wsb = wb.Sheets[best.name];
  Object.keys(wsb).forEach(function (a) {
    const c = wsb[a];
    if (a[0] !== '!' && c && c.f) { formulas++; if (c.v === undefined || c.v === 0 || c.v === '') emptyF++; }
  });
  const diag = { sheet: best.name, sheets: wb.SheetNames.length, formulas: formulas, emptyFormulas: emptyF };
  return { rows: best.rows, source: 'excel', note: wb.SheetNames.length > 1 ? 'قُرئت الورقة: ' + best.name : '', diag: diag };
}
async function rcReadDocx(f) {
  await rcLoad('mammoth');
  const res = await mammoth.convertToHtml({ arrayBuffer: await f.arrayBuffer() });
  const doc = new DOMParser().parseFromString(res.value, 'text/html');
  const rows = [];
  [].slice.call(doc.querySelectorAll('table')).forEach(function (t) {
    [].slice.call(t.querySelectorAll('tr')).forEach(function (r) {
      rows.push([].slice.call(r.children).map(function (c) { return c.textContent.trim(); }));
    });
  });
  if (rows.length) return { rows: rows, source: 'word', note: '' };
  const paras = [].slice.call(doc.querySelectorAll('p')).map(function (x) { return x.textContent; });
  if (!paras.length) throw new Error('لم أجد جدولاً أو نصاً في ملف Word.');
  return { rows: rcSplitText(paras), source: 'word', note: 'لا يوجد جدول في الملف، قُرئ النص سطراً سطراً.' };
}
async function rcOcr(src, onStatus) {
  await rcLoad('ocr');
  if (onStatus) onStatus('تجهيز محرك القراءة…');
  const worker = await rcWithTimeout(Tesseract.createWorker(['ara', 'eng'], 1, {
    logger: function (m) { if (onStatus && m.status === 'recognizing text') onStatus('قراءة الصورة ' + Math.round(m.progress * 100) + '%'); }
  }), 90000, 'تعذّر تجهيز محرك قراءة الصور (قد تكون الشبكة تحجب ملفات اللغة).');
  try {
    const out = await rcWithTimeout(worker.recognize(src), 180000, 'استغرقت قراءة الصورة وقتاً طويلاً.');
    return (out.data.words || []).filter(function (w) { return w.text && w.text.trim() && w.confidence > 20; }).map(function (w) {
      return { str: w.text.trim(), x0: w.bbox.x0, x1: w.bbox.x1, y: (w.bbox.y0 + w.bbox.y1) / 2, h: w.bbox.y1 - w.bbox.y0 };
    });
  } finally { try { await worker.terminate(); } catch (e) { /* ignore */ } }
}
async function rcReadImage(f, onStatus) {
  if (onStatus) onStatus('تجهيز الصورة…');
  const bmp = await createImageBitmap(f);
  const k = Math.min(1, 2400 / Math.max(bmp.width, bmp.height));
  const cv = document.createElement('canvas');
  cv.width = Math.round(bmp.width * k); cv.height = Math.round(bmp.height * k);
  const cx = cv.getContext('2d');
  try { cx.filter = 'grayscale(1) contrast(1.35)'; } catch (e) { /* not supported */ }
  cx.drawImage(bmp, 0, 0, cv.width, cv.height);
  const items = await rcOcr(cv, onStatus);
  if (!items.length) throw new Error('لم أستطع قراءة نص من الصورة. جرّب صورة أوضح أو الصق الجدول يدوياً.');
  return { rows: rcItemsToRows(items), source: 'ocr', note: 'قراءة آلية من صورة. راجع الأعمدة والبنود قبل المطابقة.' };
}
async function rcReadPdf(f, onStatus) {
  await rcLoad('pdf');
  const lib = window.pdfjsLib;
  lib.GlobalWorkerOptions.workerSrc = RC_LIBS.pdf.replace('pdf.min.js', 'pdf.worker.min.js');
  const pdf = await lib.getDocument({ data: new Uint8Array(await f.arrayBuffer()) }).promise;
  let items = [];
  for (let p = 1; p <= pdf.numPages; p++) {
    const page = await pdf.getPage(p);
    const vp = page.getViewport({ scale: 1 });
    const tc = await page.getTextContent();
    tc.items.forEach(function (it) {
      if (!it.str || !it.str.trim()) return;
      let str = it.str.trim();
      if (/^[٠-٩۰-۹]+$/.test(str)) str = rcLatin(str); /* digits only: keep the order pdf.js gives, matching also tries the reversed number */
      items.push({ str: str, x0: it.transform[4], x1: it.transform[4] + it.width, y: vp.height - it.transform[5] + p * 10000, h: Math.abs(it.transform[3]) || 10 });
    });
  }
  items = rcMergeRuns(items);
  if (items.length >= 15) {
    const st = rcPdfStatement(items);
    if (st) return { rows: st, source: 'pdf', note: pdf.numPages + ' صفحة · كشف حساب مُحلَّل: ' + (st.length - 1) + ' حركة' };
    return { rows: rcItemsToRows(items), source: 'pdf', note: pdf.numPages + ' صفحة' };
  }
  /* scanned PDF: render each page and read it as an image */
  const all = [];
  for (let p = 1; p <= pdf.numPages; p++) {
    if (onStatus) onStatus('صفحة ' + p + ' من ' + pdf.numPages + '…');
    const page = await pdf.getPage(p);
    const vp = page.getViewport({ scale: 2 });
    const cv = document.createElement('canvas');
    cv.width = vp.width; cv.height = vp.height;
    await page.render({ canvasContext: cv.getContext('2d'), viewport: vp }).promise;
    const its = await rcOcr(cv, onStatus);
    its.forEach(function (i) { i.y += p * 10000; all.push(i); });
  }
  if (!all.length) throw new Error('ملف PDF لا يحتوي نصاً قابلاً للقراءة.');
  return { rows: rcItemsToRows(all), source: 'ocr', note: 'ملف PDF مصوّر، قُرئ بالتعرف الضوئي. راجع البنود قبل المطابقة.' };
}
async function rcReadFile(f, onStatus) {
  const e = rcExt(f);
  if (['xlsx', 'xlsm', 'xls', 'csv', 'tsv', 'txt'].indexOf(e) !== -1) return rcReadSheet(f, e);
  if (e === 'docx') return rcReadDocx(f);
  if (e === 'pdf') return rcReadPdf(f, onStatus);
  if (/^(png|jpe?g|webp|bmp|gif|tiff?)$/.test(e) || /^image\//.test(f.type)) return rcReadImage(f, onStatus);
  if (e === 'doc') throw new Error('صيغة Word القديمة (doc) غير مدعومة. احفظ الملف بصيغة docx.');
  throw new Error('صيغة الملف غير مدعومة.');
}
