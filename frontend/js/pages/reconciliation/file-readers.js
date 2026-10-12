'use strict';

/* =====================================================================
   File readers: Excel/CSV, Word, PDF (text or scanned) and photos (OCR).
   Heavy libraries load only when a file of that type is chosen.
   ===================================================================== */
const RC_LIBS = {
  xlsx: 'https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js',
  mammoth: 'https://cdnjs.cloudflare.com/ajax/libs/mammoth/1.6.0/mammoth.browser.min.js',
  pdf: 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js',
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
  const items = [];
  for (let p = 1; p <= pdf.numPages; p++) {
    const page = await pdf.getPage(p);
    const vp = page.getViewport({ scale: 1 });
    const tc = await page.getTextContent();
    tc.items.forEach(function (it) {
      if (!it.str || !it.str.trim()) return;
      items.push({ str: it.str.trim(), x0: it.transform[4], x1: it.transform[4] + it.width, y: vp.height - it.transform[5] + p * 10000, h: Math.abs(it.transform[3]) || 10 });
    });
  }
  if (items.length >= 15) return { rows: rcItemsToRows(items), source: 'pdf', note: pdf.numPages + ' صفحة' };
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
