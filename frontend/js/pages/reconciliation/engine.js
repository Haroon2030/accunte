'use strict';

/* =====================================================================
   Statement reconciliation engine (pure functions, no DOM).
   Everything is normalised to one sign convention: amount > 0 means
   "the company owes the supplier more", amount < 0 means "owed less"
   (payment, return, discount). Both statements are converted to it,
   so the two sides can be compared directly whatever their perspective.
   ===================================================================== */
function rcLatin(s) {
  return String(s)
    .replace(/[٠-٩]/g, function (d) { return String(d.charCodeAt(0) - 0x0660); })
    .replace(/[۰-۹]/g, function (d) { return String(d.charCodeAt(0) - 0x06F0); })
    .replace(/٫/g, '.').replace(/٬/g, ',').replace(/−/g, '-');
}
function rcNorm(s) {
  return rcLatin(String(s).normalize('NFKC')).toLowerCase().replace(/[\u064B-\u065F\u0670\u0640]/g, '')
    .replace(/[أإآ]/g, 'ا').replace(/ى/g, 'ي').replace(/ة/g, 'ه').replace(/\s+/g, ' ').trim();
}
function rcNum(v) {
  if (v == null || v === '') return null;
  if (typeof v === 'number') return isFinite(v) ? v : null;
  if (v instanceof Date) return null;
  let s = rcLatin(v).trim();
  if (!s) return null;
  let neg = false;
  if (/^\(.*\)$/.test(s)) { neg = true; s = s.slice(1, -1); }
  if (/-\s*$/.test(s)) { neg = true; s = s.replace(/-\s*$/, ''); }
  if (/^\s*-/.test(s)) { neg = !neg; s = s.replace(/^\s*-/, ''); }
  s = s.replace(/[^\d.,]/g, '');
  if (!/\d/.test(s)) return null;
  if (s.indexOf(',') !== -1 && s.indexOf('.') !== -1) {
    if (s.lastIndexOf(',') > s.lastIndexOf('.')) s = s.replace(/\./g, '').replace(',', '.'); else s = s.replace(/,/g, '');
  } else if (s.indexOf(',') !== -1) {
    const parts = s.split(',');
    if (parts.length > 1 && parts[parts.length - 1].length === 3) s = s.replace(/,/g, ''); else s = s.replace(',', '.');
  }
  const n = parseFloat(s);
  /* more than 15 digits is never an amount: it is a glued document number or a mis-read column */
  if (isNaN(n) || s.replace(/[.,]/g, '').length > 15) return null;
  return neg ? -n : n;
}
function rcDate(v) {
  if (v instanceof Date) return isNaN(v) ? null : new Date(Date.UTC(v.getFullYear(), v.getMonth(), v.getDate(), 12));
  if (v == null || v === '') return null;
  if (typeof v === 'number') return v > 20000 && v < 80000 ? new Date(Date.UTC(1899, 11, 30) + Math.round(v) * 864e5 + 12 * 36e5) : null;
  const s = rcLatin(v).trim();
  let m = s.match(/(\d{4})[\/\-.](\d{1,2})[\/\-.](\d{1,2})/);
  if (m) return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], 12));
  m = s.match(/(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})/);
  if (m) { let y = +m[3]; if (y < 100) y += 2000; return new Date(Date.UTC(y, +m[2] - 1, +m[1], 12)); }
  return null;
}
const RC_FIELDS = [
  ['balance', ['الرصيد', 'رصيد', 'المستحق', 'المديونيه', 'balance', 'receivable', 'payable', 'outstanding', 'running', 'bal']],
  ['debit', ['مدين', 'debit', 'dr', 'منه']],
  ['credit', ['دائن', 'credit', 'cr', 'له']],
  ['date', ['التاريخ', 'تاريخ', 'date']],
  ['type', ['نوع المستند', 'نوع الحركه', 'نوع القيد', 'نوع', 'type']],
  ['ref', ['رقم المرجع', 'المرجع', 'مرجع', 'reference', 'ref']],
  ['doc', ['رقم المستند', 'رقم الفاتوره', 'رقم القيد', 'رقم السند', 'المستند', 'الفاتوره', 'السند', 'القيد', 'document', 'doc', 'invoice', 'inv', 'voucher', 'no', 'no.', '#']],
  ['desc', ['البيان', 'الوصف', 'التفاصيل', 'شرح', 'description', 'details', 'narration', 'particulars', 'memo']],
  ['amount', ['مبلغ', 'قيمه', 'amount', 'value', 'الاجمالي', 'صافي']]
];
const RC_SHORT = { dr: 1, cr: 1, no: 1, 'no.': 1, bal: 1, inv: 1, doc: 1, ref: 1, '#': 1 };
function rcFieldOf(cell) {
  const t = rcNorm(cell).replace(/[().:_\-\/*\[\]]/g, ' ').replace(/\s+/g, ' ').trim();
  if (!t || t.length > 40) return null;
  for (let i = 0; i < RC_FIELDS.length; i++) {
    const ks = RC_FIELDS[i][1];
    for (let j = 0; j < ks.length; j++) {
      const k = ks[j];
      if (RC_SHORT[k] ? t === k : (t === k || t.indexOf(k) !== -1)) return RC_FIELDS[i][0];
    }
  }
  return null;
}
function rcRowFields(cells) {
  const map = {};
  let hits = 0;
  (cells || []).forEach(function (c, ci) {
    const f = rcFieldOf(c);
    if (f && map[f] == null) { map[f] = ci; hits++; }
  });
  return { map: map, hits: hits };
}
function rcHasMoney(m) { return m.debit != null || m.credit != null || m.amount != null; }
/* a header only counts if numbers actually follow it in its money column(s) */
function rcHasData(rows, idx, map) {
  const cols = [map.debit, map.credit, map.amount].filter(function (c) { return c != null; });
  for (let i = idx + 1; i < Math.min(rows.length, idx + 40); i++) {
    const r = rows[i] || [];
    for (let k = 0; k < cols.length; k++) if (rcNum(r[cols[k]]) != null) return true;
  }
  return false;
}
/* find the header row anywhere in the first 300 rows (blank rows, titles, company name lines are skipped);
   also copes with a header split over two rows */
function rcFindHeader(rows) {
  let best = null;
  const lim = Math.min(rows.length, 300);
  const consider = function (idx, f) {
    if (f.hits >= 2 && rcHasMoney(f.map) && rcHasData(rows, idx, f.map) && (!best || f.hits > best.hits)) best = { idx: idx, map: f.map, hits: f.hits };
  };
  for (let i = 0; i < lim; i++) {
    const a = rcRowFields(rows[i]);
    consider(i, a);
    const nxt = rows[i + 1];
    if (nxt && (!best || best.idx < i)) {
      const w = Math.max((rows[i] || []).length, nxt.length);
      const merged = [];
      for (let c = 0; c < w; c++) {
        const x = rows[i][c], y = nxt[c];
        const tx = x == null ? '' : String(x).trim(), ty = y == null ? '' : String(y).trim();
        merged.push((tx + ' ' + ty).trim());
      }
      const b = rcRowFields(merged);
      if (b.hits > a.hits) consider(i + 1, b);
    }
  }
  return best;
}
function rcLooksDate(v) {
  if (v instanceof Date) return true;
  return typeof v === 'string' && /^\s*\d{1,4}[\/\-.]\d{1,2}[\/\-.]\d{1,4}\s*$/.test(rcLatin(v)) && rcDate(v) != null;
}
/* no recognisable header: infer the columns from what the rows look like */
function rcGuessLayout(rows) {
  const isData = function (r) {
    let d = false, n = false;
    (r || []).forEach(function (c) { if (rcLooksDate(c)) d = true; else if (rcNum(c) != null) n = true; });
    return d && n;
  };
  let first = -1;
  for (let i = 0; i < Math.min(rows.length, 400); i++) if (isData(rows[i])) { first = i; break; }
  if (first < 0) return null;
  const data = [];
  for (let i = first; i < Math.min(rows.length, first + 400); i++) if (isData(rows[i])) data.push(rows[i]);
  let w = 0;
  data.forEach(function (r) { w = Math.max(w, r.length); });
  const col = function (c) { return data.map(function (r) { return r[c]; }); };
  const stat = [];
  for (let c = 0; c < w; c++) {
    const vs = col(c);
    const nonEmpty = vs.filter(function (v) { return v !== '' && v != null && String(v).trim() !== ''; });
    const dates = nonEmpty.filter(rcLooksDate).length;
    const nums = nonEmpty.filter(function (v) { return !rcLooksDate(v) && rcNum(v) != null; });
    const txt = nonEmpty.length - dates - nums.length;
    const ints = nums.length && nums.every(function (v) { const n = rcNum(v); return n === Math.floor(n) && n >= 0; });
    const uniq = new Set(nonEmpty.map(String)).size;
    const avgLen = nonEmpty.length ? nonEmpty.reduce(function (s, v) { return s + String(v).length; }, 0) / nonEmpty.length : 0;
    stat.push({ c: c, n: nonEmpty.length, dates: dates, nums: nums.length, txt: txt, ints: ints, uniq: uniq, avgLen: avgLen });
  }
  const T = data.length;
  const dateCol = stat.slice().sort(function (a, b) { return b.dates - a.dates; })[0];
  const map = {};
  if (dateCol && dateCol.dates >= T * 0.5) map.date = dateCol.c;
  let numCols = stat.filter(function (s) { return s.c !== map.date && s.nums >= T * 0.25 && s.nums >= s.txt; });
  /* a fully populated, all-integer, unique column is a document number, not money */
  const docNum = numCols.filter(function (s) { return s.ints && s.n >= T * 0.9 && s.uniq >= s.n * 0.9 && s.c !== numCols[numCols.length - 1].c; })[0];
  if (docNum && numCols.length >= 3) { map.doc = docNum.c; numCols = numCols.filter(function (s) { return s !== docNum; }); }
  if (numCols.length > 3) numCols = numCols.slice(numCols.length - 3);
  const rest = stat.filter(function (s) { return s.c !== map.date && s.c !== map.doc && numCols.indexOf(s) === -1 && s.txt > 0; });
  if (map.doc == null && rest.length) {
    const shortest = rest.slice().sort(function (a, b) { return a.avgLen - b.avgLen; })[0];
    if (rest.length >= 2 && shortest.avgLen <= 24) map.doc = shortest.c;
  }
  const desc = rest.filter(function (s) { return s.c !== map.doc; }).sort(function (a, b) { return b.avgLen - a.avgLen; })[0];
  if (desc) map.desc = desc.c;
  const money = numCols.map(function (s) { return s.c; });
  let bal = null, a = null, b = null;
  const num = function (v) { const n = rcNum(v); return n == null ? 0 : n; };
  if (money.length >= 3) { a = money[0]; b = money[1]; bal = money[2]; }
  else if (money.length === 2) { a = money[0]; bal = money[1]; }
  else if (money.length === 1) { a = money[0]; }
  if (!money.length) return null;
  let incFirst = true;
  if (bal != null) {
    map.balance = bal;
    let s1 = 0, s2 = 0;
    for (let i = 1; i < data.length; i++) {
      const d = num(data[i][bal]) - num(data[i - 1][bal]);
      const mv = b != null ? num(data[i][a]) - num(data[i][b]) : num(data[i][a]);
      s1 += Math.abs(d - mv); s2 += Math.abs(d + mv);
    }
    incFirst = s1 <= s2;
  }
  const headerIdx = first - 1;
  return { idx: headerIdx, map: map, a: a, b: b, single: b == null, incFirst: incFirst, guessed: true };
}
/* share of rows whose balance movement equals the chosen debit/credit columns (either sign) */
function rcBalanceFit(rows, idx, cols, bal) {
  let ok = 0, tot = 0, prev = null;
  for (let i = idx + 1; i < Math.min(rows.length, idx + 600); i++) {
    const b = rcNum((rows[i] || [])[bal]);
    if (b == null) continue;
    if (prev != null) {
      const d = b - prev;
      const mv = (cols[0] == null ? 0 : (rcNum(rows[i][cols[0]]) || 0)) - (cols[1] == null ? 0 : (rcNum(rows[i][cols[1]]) || 0));
      tot++;
      if (Math.abs(d - mv) < 0.51 || Math.abs(d + mv) < 0.51) ok++;
    }
    prev = b;
  }
  return tot >= 3 ? ok / tot : null;
}
function rcRepairColumns(rows, idx, map) {
  if (map.balance == null || (map.debit == null && map.credit == null)) return map;
  const fit = rcBalanceFit(rows, idx, [map.debit, map.credit], map.balance);
  if (fit == null || fit >= 0.7) return map;
  let w = 0;
  rows.slice(idx + 1, idx + 200).forEach(function (r) { w = Math.max(w, (r || []).length); });
  const cand = [];
  for (let c = 0; c < w; c++) if (c !== map.balance && c !== map.date && c !== map.doc) cand.push(c);
  let best = null;
  cand.forEach(function (a) {
    cand.forEach(function (b) {
      if (b === a) return;
      const f = rcBalanceFit(rows, idx, [a, b], map.balance);
      if (f != null && f >= 0.7 && (!best || f > best.f)) best = { a: a, b: b, f: f };
    });
  });
  if (!best) return map;
  return Object.assign({}, map, { debit: best.a, credit: best.b, repaired: true });
}
/* which side of the ledger holds the invoices? vote by invoice wording and by where payments sit */
function rcDetectPersp(rows, idx, map) {
  let sup = 0, com = 0, sumDr = 0, sumCr = 0;
  const inv = /(فاتوره|invoice|مبيعات|مشتريات)/i, not = /(مردود|مرتجع|return|credit note|اشعار|خصم|تسويه|adjust)/i;
  for (let i = idx + 1; i < Math.min(rows.length, idx + 800); i++) {
    const r = rows[i] || [];
    const dr = rcNum(r[map.debit]) || 0, cr = rcNum(r[map.credit]) || 0;
    sumDr += dr; sumCr += cr;
    const t = rcNorm(r.filter(function (c) { return typeof c === 'string'; }).join(' '));
    if (RC_SUM.test(t) || RC_OPENING.test(t)) continue;
    if (RC_PAY.test(t) && !inv.test(t)) { if (cr > dr) sup++; else if (dr > cr) com++; }
    else if (inv.test(t) && !not.test(t)) { if (dr > cr) sup++; else if (cr > dr) com++; }
  }
  if (sup + com >= 3 && sup !== com) return sup > com ? 'supplier' : 'company';
  return sumDr >= sumCr ? 'supplier' : 'company';
}
function rcAutoLayout(rows, persp) {
  const hd = rcFindHeader(rows);
  if (hd) {
    const map = rcRepairColumns(rows, hd.idx, hd.map);
    const L = rcBuildLedger(rows, hd.idx, map, persp);
    const allZero = L.lines.length > 0 && L.lines.every(function (l) { return Math.abs(l.amount) < 1e-9; });
    if (!allZero) return { idx: hd.idx, map: map, guess: null, repaired: !!map.repaired };
    if (map.balance != null) {
      const bs = [];
      for (let i = hd.idx + 1; i < rows.length; i++) { const b = rcNum((rows[i] || [])[map.balance]); if (b != null) bs.push(b); }
      const moves = bs.some(function (b, i) { return i > 0 && Math.abs(b - bs[i - 1]) > 0.005; });
      if (moves) {
        const neg = bs.filter(function (b) { return b < 0; }).length > bs.length / 2;
        return { idx: hd.idx, map: Object.assign({}, map, { byBalance: neg ? -1 : 1 }), guess: null, derived: true };
      }
    }
    const g0 = rcGuessLayout(rows);
    if (g0) return { idx: g0.idx, map: rcGuessMap(g0, persp), guess: g0, repaired: false };
    return { idx: hd.idx, map: map, guess: null, repaired: false };
  }
  const g = rcGuessLayout(rows);
  return g ? { idx: g.idx, map: rcGuessMap(g, persp), guess: g } : null;
}
/* turn a guessed layout into a column map for the chosen perspective */
function rcGuessMap(g, persp) {
  const m = Object.assign({}, g.map);
  if (g.single) { m.amount = g.a; return m; }
  const inc = g.incFirst ? g.a : g.b, dec = g.incFirst ? g.b : g.a;
  if (persp === 'supplier') { m.debit = inc; m.credit = dec; } else { m.credit = inc; m.debit = dec; }
  return m;
}
const RC_OPENING = /(رصيد\s*(افتتاح|سابق|مرحل|اول|أول|بداي)|افتتاحي|opening|brought\s*forward|b\/f)/i;
const RC_TOTAL = /^\s*(الاجمالي|الإجمالي|المجموع|اجمالي|إجمالي|total|الرصيد\s*(الختامي|النهائي)|closing|رصيد\s*ختامي)/i;
/* wording that marks a summary line anywhere in a row (totals, net balance, balance in words ...) */
const RC_SUM = /(اجمالي|الاجمالي|المجموع|مجموع|grand total|sub ?total|\btotal\b|net receivable|net payable|net balance|صافي|الرصيد (لكم|علينا|المستحق|الختامي|النهائي)|balance due|closing balance)/i;
const RC_PAY = /(سداد|دفعه|دفعة|تحويل|شيك|سند\s*صرف|payment|paid|receipt|remit|bank|حواله|حوالة)/i;
const RC_CN = /(خصم|اشعار\s*دائن|إشعار\s*دائن|مرتجع|مردود|ارجاع|إرجاع|credit\s*note|return|rebate|discount)/i;
const RC_ADJ = /(تسويه|تسوية|adjust)/i;
function rcKind(text, amount, isOpening) {
  if (isOpening) return 'opening';
  const t = rcNorm(text);
  if (RC_PAY.test(t) && amount < 0) return 'payment';
  if (RC_CN.test(t) && amount < 0) return 'credit_note';
  if (RC_ADJ.test(t)) return 'adjustment';
  if (RC_CN.test(t) && amount > 0) return 'other';
  if (amount > 0) return 'invoice';
  return amount < 0 ? 'credit' : 'other';
}
const RC_KIND = { invoice: 'فاتورة', payment: 'دفعة', credit_note: 'خصم / إشعار دائن', adjustment: 'تسوية', opening: 'رصيد افتتاحي', other: 'حركة أخرى', credit: 'دفعة / إشعار دائن' };
function rcDocKey(doc, desc) {
  let src = doc != null && String(doc).trim() ? String(doc) : '';
  if (!src && desc) {
    const m = rcLatin(desc).match(/[A-Za-z]{1,5}[-\s]?\d{3,}|\b\d{4,}\b/);
    if (m) src = m[0];
  }
  src = rcLatin(src).toUpperCase().trim();
  if (!src) return '';
  const runs = src.match(/\d+/g);
  if (runs) {
    const longest = runs.sort(function (a, b) { return b.length - a.length; })[0].replace(/^0+/, '');
    if (longest.length >= 3) return longest;
  }
  return src.replace(/[^A-Z0-9؀-ۿ]/g, '');
}
/* every long number (6+ digits) in the document, reference and wording: supplier invoice numbers hide there */
function rcKeysOf(doc, ref, desc) {
  const out = [];
  [ref, doc, desc].forEach(function (src) {
    if (src == null || src === '' || src instanceof Date) return;
    (rcLatin(String(src)).match(/\d{6,}/g) || []).forEach(function (m) { const k = m.replace(/^0+/, ''); if (k && out.indexOf(k) === -1) out.push(k); });
  });
  /* Arabic PDFs sometimes hand over a long number back to front: try it both ways */
  out.slice().forEach(function (k) { if (k.length >= 10) { const r = k.split('').reverse().join(''); if (out.indexOf(r) === -1) out.push(r); } });
  /* a supplier often prints the invoice number with a suffix our side lacks (or the reverse): its first 10 digits stand in for it */
  out.slice().forEach(function (k) { const h = k.slice(0, 10); if (k.length >= 12 && out.indexOf(h) === -1) out.push(h); });
  return out;
}
function rcCell(v) { return v instanceof Date ? v : (v == null ? '' : String(v).trim()); }
/* rows -> normalised ledger lines. persp: 'supplier' (debit = invoice) | 'company' (credit = invoice) */
function rcBuildLedger(rows, headerIdx, map, persp) {
  const out = [];
  let sumDr = 0, sumCr = 0, prevBal = 0, lastStated = null;
  let statedBalance = null;
  for (let i = headerIdx + 1; i < rows.length; i++) {
    const r = rows[i] || [];
    const get = function (f) { return map[f] != null ? r[map[f]] : undefined; };
    if (r.every(function (c) { return c === '' || c == null || (typeof c === 'string' && !c.trim()); })) continue;
    const desc = rcCell(get('desc'));
    const doc = rcCell(get('doc'));
    const ref = rcCell(get('ref'));
    const type = rcCell(get('type'));
    const texts = r.filter(function (c) { return typeof c === 'string' && c.trim() && (rcNum(c) == null || /[A-Za-z\u0600-\u06FF]{3,}/.test(c)) && !rcLooksDate(c); }).map(function (c) { return c.trim(); });
    const anyText = texts[0] || '';
    const hasDate = rcDate(get('date')) != null;
    const label = desc || type || anyText || (doc && doc !== '-' ? doc : '');
    const dr = rcNum(get('debit')), cr = rcNum(get('credit')), am = rcNum(get('amount'));
    const opening = RC_OPENING.test(rcNorm(texts.join(' ') + ' ' + doc));
    if (!opening) {
      const hasDoc = (doc && doc !== '-' && /\d/.test(doc)) || (ref && /\d/.test(ref));
      if (RC_TOTAL.test(rcNorm(label))) continue;
      /* summary lines: "Total ...", "Net receivable ...", the balance written in words ... */
      if (RC_SUM.test(rcNorm(texts.join(' '))) && (!hasDate || !hasDoc)) continue;
      /* a row of bare numbers (no date, no document, no wording) is a total line */
      if (!hasDate && !label && (dr != null || cr != null || am != null || (map.byBalance && rcNum(get('balance')) != null))) continue;
      /* a line with no document that repeats the balance printed just above is the closing balance */
      if (!hasDoc && lastStated != null && rcNum(get('balance')) == null && [dr, cr, am].some(function (x) { return x != null && Math.abs(Math.abs(x) - Math.abs(lastStated)) <= 0.5; })) continue;
      /* a row equal to everything above it is a running total */
      if (out.length >= 3 && sumDr + sumCr > 0 && dr != null && cr != null && Math.abs(dr - sumDr) <= 0.5 && Math.abs(cr - sumCr) <= 0.5 && !hasDate) continue;
    }
    let amount = null;
    if (map.byBalance) {
      const bnow = rcNum(get('balance'));
      if (bnow != null) { amount = (bnow - prevBal) * map.byBalance; prevBal = bnow; }
    } else if (dr != null || cr != null) amount = persp === 'supplier' ? (dr || 0) - (cr || 0) : (cr || 0) - (dr || 0);
    else if (am != null) amount = am;
    if (amount == null || (amount === 0 && dr == null && cr == null && am == null)) continue;
    const bal = rcNum(get('balance'));
    if (bal != null) { statedBalance = bal; lastStated = bal; }
    const kind = rcKind(type + ' ' + desc + ' ' + doc + ' ' + (opening ? texts.join(' ') : ''), amount, opening);
    sumDr += dr || 0; sumCr += cr || 0;
    const keys = opening ? [] : rcKeysOf(doc, ref, desc);
    out.push({
      n: out.length + 1, date: rcDate(get('date')), doc: doc && doc !== '-' ? doc : (ref || ''), desc: desc || type || (opening || !doc ? anyText : ''), amount: amount, kind: kind,
      keys: keys, key: opening ? '' : (keys[0] || rcDocKey(doc, desc)), debit: dr, credit: cr
    });
  }
  return { lines: out, statedBalance: statedBalance, sum: out.reduce(function (s0, l) { return s0 + l.amount; }, 0) };
}

const RC_STATUS = {
  matched: { label: 'مطابق', tone: 'ok' },
  matched_amount: { label: 'مطابق بالمبلغ فقط', tone: 'work' },
  amount_diff: { label: 'فرق في المبلغ', tone: 'warn' },
  only_supplier: { label: 'عند المورد فقط', tone: 'bad' },
  only_company: { label: 'عندنا فقط', tone: 'bad' }
};
function rcReason(status, kind, diff) {
  if (status === 'matched') return '';
  if (status === 'matched_amount') return 'نفس المبلغ ولكن رقم المستند مختلف أو غائب. أكّد أنهما بند واحد.';
  if (status === 'amount_diff') return diff > 0 ? 'مبلغ المورد أعلى من مبلغنا. تحقق من خصم تجاري أو ضريبة أو فرق تسعير.' : 'مبلغنا أعلى من مبلغ المورد. تحقق من تسجيل المورد للفاتورة.';
  if (status === 'only_supplier') {
    if (kind === 'invoice') return 'فاتورة عند المورد غير مسجّلة عندنا. تحقق من الاستلام والإدخال.';
    if (kind === 'payment') return 'دفعة مسجّلة عند المورد غير مسجّلة عندنا. تحقق من السداد.';
    if (kind === 'credit_note') return 'خصم أو إشعار عند المورد غير مسجّل عندنا. اطلب المستند وسجّله.';
    if (kind === 'adjustment') return 'تسوية عند المورد غير مسجّلة عندنا. اطلب تفاصيلها.';
    return 'حركة عند المورد غير مسجّلة عندنا. اطلب التفاصيل.';
  }
  if (kind === 'invoice') return 'فاتورة مسجّلة عندنا وغير ظاهرة في كشف المورد (تأخر ترحيل أو لم تصله).';
  if (kind === 'payment') return 'دفعة سددناها وغير مسجّلة عند المورد. أرسل له إثبات التحويل.';
  if (kind === 'credit_note') return 'خصم أو إشعار مسجّل عندنا وغير مسجّل عند المورد. أرسل له المستند.';
  if (kind === 'adjustment') return 'تسوية داخلية عندنا (تكاليف أو مخزون) لا تظهر في كشف المورد. قيد داخلي يُراجع ولا يُرسل للمورد.';
  return 'حركة عندنا غير موجودة في كشف المورد.';
}
/* A = supplier statement ledger, B = company ledger (both already normalised). */
function rcReconcile(A, B, opts) {
  const tol = opts && opts.tol != null ? opts.tol : 0.25;
  const winDays = opts && opts.days != null ? opts.days : 15;
  const aLeft = A.lines.map(function (l, i) { return Object.assign({ i: i }, l); });
  const bLeft = B.lines.map(function (l, i) { return Object.assign({ i: i }, l); });
  const pairs = [];
  const usedA = {}, usedB = {};
  const dd = function (x, y) { return x && y ? Math.abs(x - y) / 864e5 : 9999; };
  const take = function (a, b, how) { usedA[a.i] = true; usedB[b.i] = true; pairs.push({ a: a, b: b, how: how }); };

  /* 1. opening balances against each other */
  const oa = aLeft.filter(function (l) { return l.kind === 'opening'; }), ob = bLeft.filter(function (l) { return l.kind === 'opening'; });
  for (let i = 0; i < Math.min(oa.length, ob.length); i++) take(oa[i], ob[i], 'doc');

  /* 2. a shared document number (any of the numbers found in the line): equal amounts first, then same-sign differences */
  const keysOf = function (l) { return l.keys && l.keys.length ? l.keys : (l.key ? [l.key] : []); };
  const idx = {};
  bLeft.forEach(function (b) { if (!usedB[b.i]) keysOf(b).forEach(function (k) { (idx[k] = idx[k] || []).push(b); }); });
  const search = function (a, accept) {
    let best = null, bd = 1e12;
    keysOf(a).forEach(function (k) {
      (idx[k] || []).forEach(function (b) {
        if (usedB[b.i]) return;
        const score = accept(a, b);
        if (score != null && score < bd) { bd = score; best = b; }
      });
    });
    return best;
  };
  aLeft.forEach(function (a) {
    if (usedA[a.i]) return;
    const b = search(a, function (x, y) { return Math.abs(x.amount - y.amount) <= tol ? dd(x.date, y.date) : null; });
    if (b) take(a, b, 'doc');
  });
  aLeft.forEach(function (a) {
    if (usedA[a.i]) return;
    const b = search(a, function (x, y) { return x.amount * y.amount > 0 ? Math.abs(x.amount - y.amount) : null; });
    if (b) take(a, b, 'doc');
  });

  /* 3. no document match: same sign, amount within tolerance, date within window; two tiers */
  [tol, null].forEach(function (tier) {
    aLeft.forEach(function (a) {
      if (usedA[a.i] || Math.abs(a.amount) <= tol) return;
      const lim = tier == null ? Math.min(5, Math.max(tol, Math.abs(a.amount) * 0.0003)) : tier;
      let best = null, bd = 1e12;
      bLeft.forEach(function (b) {
        if (usedB[b.i] || a.amount * b.amount <= 0) return;
        const af = Math.abs(a.amount - b.amount);
        if (af > lim) return;
        const d = dd(a.date, b.date);
        if (a.date && b.date && d > winDays) return;
        const sc = (d > 9000 ? 0 : d) + af;
        if (sc < bd) { bd = sc; best = b; }
      });
      if (best) take(a, best, 'amount');
    });
  });

  const items = [];
  let id = 0;
  const mkItem = function (status, a, b, how) {
    const amtA = a ? a.amount : 0, amtB = b ? b.amount : 0;
    const kind = (a || b).kind;
    id += 1;
    const diff = amtA - amtB;
    return {
      id: 'R' + String(id).padStart(3, '0'), status: status, kind: kind,
      doc: (a && a.doc) || (b && b.doc) || '', docA: a ? a.doc : '', docB: b ? b.doc : '',
      date: (a && a.date) || (b && b.date) || null, dateA: a ? a.date : null, dateB: b ? b.date : null,
      descA: a ? a.desc : '', descB: b ? b.desc : '', amtA: a ? amtA : null, amtB: b ? amtB : null, diff: diff,
      reason: rcReason(status, kind, diff)
    };
  };
  pairs.forEach(function (pr) {
    const same = Math.abs(pr.a.amount - pr.b.amount) <= tol;
    const status = pr.how === 'amount' ? 'matched_amount' : (same ? 'matched' : 'amount_diff');
    items.push(mkItem(status, pr.a, pr.b, pr.how));
  });
  aLeft.forEach(function (a) { if (!usedA[a.i]) items.push(mkItem('only_supplier', a, null)); });
  bLeft.forEach(function (b) { if (!usedB[b.i]) items.push(mkItem('only_company', null, b)); });
  items.sort(function (x, y) { return (x.date ? x.date.getTime() : 0) - (y.date ? y.date.getTime() : 0) || (x.id < y.id ? -1 : 1); });

  /* statement: supplier balance - explained items = company balance (exact by construction) */
  const sumA = A.sum, sumB = B.sum;
  const cat = function (it) {
    if (it.status === 'matched') return 'matched';
    if (it.kind === 'opening') return 'opening';
    if (it.status === 'amount_diff') return 'amount_diff';
    if (it.status === 'matched_amount') return 'matched_amount';
    if (it.kind === 'payment') return it.status === 'only_supplier' ? 'pay_supplier' : 'pay_company';
    if (it.kind === 'credit_note' || it.kind === 'credit') return it.status === 'only_supplier' ? 'cn_supplier' : 'cn_company';
    if (it.kind === 'adjustment') return it.status === 'only_supplier' ? 'adj_supplier' : 'adj_company';
    return it.status === 'only_supplier' ? 'inv_supplier' : 'inv_company';
  };
  const CATS = [
    ['inv_supplier', 'فواتير في كشف المورد غير مسجّلة عندنا'],
    ['inv_company', 'فواتير عندنا غير ظاهرة في كشف المورد'],
    ['pay_company', 'دفعات سددناها وغير مسجّلة عند المورد'],
    ['pay_supplier', 'دفعات عند المورد غير مسجّلة عندنا'],
    ['cn_company', 'خصومات وإشعارات عندنا غير مسجّلة عند المورد'],
    ['cn_supplier', 'خصومات وإشعارات عند المورد غير مسجّلة عندنا'],
    ['adj_company', 'تسويات تكاليف داخلية عندنا لا تظهر عند المورد'],
    ['adj_supplier', 'تسويات عند المورد غير مسجّلة عندنا'],
    ['amount_diff', 'فروق في مبالغ مستندات متطابقة الرقم'],
    ['matched_amount', 'فروق في بنود مطابقة بالمبلغ'],
    ['opening', 'فرق في الرصيد الافتتاحي'],
    ['matched', 'فروق تقريب في بنود متطابقة']
  ];
  const totals = {};
  items.forEach(function (it) { const c = cat(it); totals[c] = (totals[c] || 0) + (it.amtA || 0) - (it.amtB || 0); });
  const lines = CATS.filter(function (c) { return Math.abs(totals[c[0]] || 0) > tol || items.some(function (it) { return cat(it) === c[0]; }); })
    .map(function (c) { return { key: c[0], label: c[1], effect: -(totals[c[0]] || 0), count: items.filter(function (it) { return cat(it) === c[0]; }).length }; })
    .filter(function (l) { return l.count > 0 && Math.abs(l.effect) > 0.005; });
  const adjusted = sumA + lines.reduce(function (s, l) { return s + l.effect; }, 0);
  const counts = {};
  items.forEach(function (it) { counts[it.status] = (counts[it.status] || 0) + 1; });
  return {
    items: items, sumA: sumA, sumB: sumB, diff: sumA - sumB, lines: lines, adjusted: adjusted, unexplained: adjusted - sumB, counts: counts,
    open: items.filter(function (it) { return it.status !== 'matched'; }).length
  };
}
/* sample statements (same shape a parsed Excel sheet would have), used by the demo button */
function rcSampleRows() {
  const head = ['التاريخ', 'رقم المستند', 'البيان', 'مدين', 'دائن', 'الرصيد'];
  const sup = [
    ['01/09/2026', '', 'رصيد افتتاحي مرحل', 120000, ''],
    ['03/09/2026', 'INV-88101', 'فاتورة مبيعات', 45200, ''],
    ['07/09/2026', 'INV-88135', 'فاتورة مبيعات', 38750, ''],
    ['10/09/2026', 'INV-88213', 'فاتورة مبيعات', 22300, ''],
    ['14/09/2026', 'PAY-5521', 'سداد دفعة', '', 60000],
    ['18/09/2026', 'INV-88277', 'فاتورة مبيعات', 31400, ''],
    ['22/09/2026', 'INV-88290', 'فاتورة مبيعات', 12950, ''],
    ['25/09/2026', 'SR-0412', 'مرتجع بضاعة', '', 3100]
  ];
  const our = [
    ['01/09/2026', '', 'رصيد افتتاحي', '', 120000],
    ['03/09/2026', '88101', 'فاتورة مشتريات', '', 45200],
    ['08/09/2026', '88135', 'فاتورة مشتريات', '', 38750],
    ['11/09/2026', '88213', 'فاتورة مشتريات', '', 17980],
    ['15/09/2026', 'PAY-5521', 'سند صرف / تحويل بنكي', 60000, ''],
    ['23/09/2026', '88290', 'فاتورة مشتريات', '', 12950],
    ['26/09/2026', 'CN-7731', 'إشعار دائن مرتجع', 3100, ''],
    ['28/09/2026', 'INV-88301', 'فاتورة مشتريات', '', 9800],
    ['29/09/2026', 'PAY-5560', 'سند صرف / تحويل بنكي', 40000, ''],
    ['30/09/2026', 'DISC-77', 'خصم تجاري متفق عليه', 1500, '']
  ];
  const withBal = function (rows, sign) {
    let b = 0;
    return rows.map(function (r) { b += sign * ((Number(r[3]) || 0) - (Number(r[4]) || 0)); return r.concat([b]); });
  };
  return { supplier: [head].concat(withBal(sup, 1)), company: [head].concat(withBal(our, -1)) };
}
