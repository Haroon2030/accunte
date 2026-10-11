/* مطابق كشوفات الحساب — بناء دفتر جانب واحد (دفاترنا أو كشف المورد) من جدول خام:
   كشف الترويسة، استنتاج الأعمدة، الرصيد الافتتاحي بكل صوره، حذف الإجماليات والمرحَّل، اتجاه الحركة،
   ترتيب التواريخ، وفحص تكامل الرصيد الجاري.
   اصطلاح المبالغ: كلها بالهللات (أعداد صحيحة)، والإشارة «المستحق للمورد»: الموجب = نحن مدينون للمورد. */
(function (g) {
    'use strict';
    var SM = g.SM = g.SM || {};
    var N = function (s) { return SM.normAr(s); };

    // ── مفردات الأعمدة (مُطبَّعة: ة→ه، أ/إ→ا، ى→ي) ──────────────────────────────
    var FIELD_WORDS = {
        balance: ['رصيد', 'balance', 'bal'],
        debit: ['مدين', 'debit', 'منه', 'عليه', 'dr', 'مدينه'],
        credit: ['دائن', 'credit', 'له', 'cr', 'دائنه'],
        amount: ['المبلغ', 'مبلغ', 'amount', 'القيمه', 'قيمه', 'value'],
        due: ['استحقاق', 'due'],
        date: ['تاريخ', 'date', 'التاريخ'],
        ref: ['رقم المستند', 'رقم الفاتوره', 'رقم السند', 'رقم القيد', 'المرجع', 'مرجع', 'مستند', 'سند', 'document', 'doc no', 'doc', 'reference', 'ref', 'voucher',
            'invoice no', 'inv no', 'رقم', 'no', 'رقم الحواله', 'الفاتوره'],
        desc: ['بيان', 'البيان', 'وصف', 'الوصف', 'تفاصيل', 'description', 'details', 'narration', 'ملاحظات', 'text', 'نوع الحركه', 'الحركه']
    };
    Object.keys(FIELD_WORDS).forEach(function (k) { FIELD_WORDS[k] = FIELD_WORDS[k].map(N); });
    var PRIORITY = ['balance', 'due', 'debit', 'credit', 'amount', 'date', 'desc', 'ref'];

    function labelField(text) {
        var n = N(text);
        if (!n) return null;
        for (var p = 0; p < PRIORITY.length; p++) {
            var f = PRIORITY[p], words = FIELD_WORDS[f];
            for (var i = 0; i < words.length; i++) {
                var w = words[i];
                if (n === w) return f;
                if (w.length <= 3 && /^[a-z]+$/.test(w)) { if (new RegExp('(^|[^a-z])' + w + '([^a-z]|$)').test(n)) return f; }
                else if (n.indexOf(w) >= 0) return f;
            }
        }
        return null;
    }
    SM.labelField = labelField;

    /** يبحث عن نطاق الترويسة (قد يمتد 1–3 أسطر). يُرجع {start,end,map,score} أو null. */
    SM.findHeader = function (rows) {
        var best = null, limit = Math.min(rows.length, 60);
        for (var i = 0; i < limit; i++) {
            for (var span = 1; span <= 3 && i + span <= rows.length; span++) {
                var width = 0, r;
                for (r = i; r < i + span; r++) width = Math.max(width, (rows[r] || []).length);
                var map = {}, distinct = 0;
                for (var c = 0; c < width; c++) {
                    var parts = [];
                    for (r = i; r < i + span; r++) { var cell = (rows[r] || [])[c]; if (cell !== '' && cell != null && typeof cell !== 'number') parts.push(String(cell)); }
                    if (!parts.length) continue;
                    var f = labelField(parts.join(' '));
                    if (!f || f === 'due') continue;
                    if (map[f] === undefined) { map[f] = c; distinct++; }
                    else if (f === 'balance') { (map.balanceAlt = map.balanceAlt || []).push(c); }
                }
                var hasMoney = map.debit !== undefined || map.credit !== undefined || map.amount !== undefined || map.balance !== undefined;
                var hasId = map.date !== undefined || map.ref !== undefined || map.desc !== undefined;
                if (distinct >= 3 && hasMoney && hasId) {
                    var score = distinct * 10 - span;
                    if (!best || score > best.score) best = { start: i, end: i + span - 1, map: map, score: score };
                }
            }
            if (best && i > best.end + 2) break;
        }
        return best;
    };

    function colStats(rows, start, ncols) {
        var stats = [], c;
        for (c = 0; c < ncols; c++) stats.push({ n: 0, date: 0, num: 0, textLen: 0, refish: 0, ints: [], vals: [] });
        var take = rows.slice(start, start + 400);
        take.forEach(function (row) {
            for (var c = 0; c < ncols; c++) {
                var v = row[c];
                if (v === '' || v == null) continue;
                var s = stats[c]; s.n++;
                var isNum = typeof v === 'number' || SM.parseNumber(v) !== null;
                if (SM.parseDate(v) && (typeof v !== 'number' || v > 20000)) { s.date++; }
                else if (isNum) { s.num++; s.vals.push(typeof v === 'number' ? v : SM.parseNumber(v)); }
                else { s.textLen += String(v).length; if (/\d/.test(String(v)) && String(v).length <= 24) s.refish++; }
            }
        });
        return stats;
    }

    /** استنتاج الأعمدة من المحتوى حين لا توجد ترويسة معروفة. */
    SM.inferColumns = function (rows, start) {
        start = start || 0;
        var ncols = 0;
        rows.forEach(function (r) { ncols = Math.max(ncols, r.length); });
        var st = colStats(rows, start, ncols), total = Math.max(1, Math.min(rows.length - start, 400)), map = {}, c;
        var bestDate = -1, bd = 0;
        for (c = 0; c < ncols; c++) if (st[c].date > bd && st[c].date >= total * 0.3) { bd = st[c].date; bestDate = c; }
        if (bestDate >= 0) map.date = bestDate;
        var numCols = [];
        for (c = 0; c < ncols; c++) {
            if (c === bestDate || st[c].num < total * 0.25) continue;
            var seq = st[c].vals.length > 3 && st[c].vals.every(function (v, i) { return Number.isInteger(v) && (i === 0 || v === st[c].vals[i - 1] + 1); });
            if (!seq) numCols.push(c);
        }
        // عمود الرصيد: الذي يساوي تغيّره بين صفين متتاليين حركةَ عمود آخر (أو فرقَ عمودين)
        function rowVal(row, col) { var v = row[col]; var n = typeof v === 'number' ? v : SM.parseNumber(v); return n === null ? 0 : n; }
        var data = rows.slice(start).filter(function (r) { return r.some(function (x) { return x !== '' && x != null; }); });
        var bestBal = -1, bestScore = 0;
        numCols.forEach(function (bc) {
            var others = numCols.filter(function (x) { return x !== bc; }), hit = 0, tried = 0;
            for (var i = 1; i < data.length; i++) {
                var cur = data[i][bc], prev = data[i - 1][bc];
                if (cur === '' || prev === '' || cur == null || prev == null) continue;
                var d = Math.abs(rowVal(data[i], bc) - rowVal(data[i - 1], bc));
                tried++;
                var cand = [];
                others.forEach(function (o) { cand.push(Math.abs(rowVal(data[i], o))); others.forEach(function (o2) { if (o2 !== o) cand.push(Math.abs(rowVal(data[i], o) - rowVal(data[i], o2))); }); });
                if (cand.some(function (x) { return Math.abs(x - d) < 0.011; })) hit++;
            }
            var score = tried >= 2 ? hit / tried : 0;
            if (score > bestScore && score >= 0.6) { bestScore = score; bestBal = bc; }
        });
        if (bestBal >= 0) map.balance = bestBal;
        var money = numCols.filter(function (x) { return x !== bestBal; });
        if (money.length >= 2) { map.debit = money[0]; map.credit = money[1]; }
        else if (money.length === 1) map.amount = money[0];
        var used = {};
        Object.keys(map).forEach(function (k) { used[map[k]] = 1; });
        var textCols = [];
        for (c = 0; c < ncols; c++) if (!used[c] && st[c].n) textCols.push(c);
        var refCol = -1, refScore = 0, descCol = -1, descLen = 0;
        textCols.forEach(function (tc) {
            var avg = st[tc].textLen / Math.max(1, st[tc].n - st[tc].num);
            var rs = st[tc].refish / Math.max(1, st[tc].n);
            if (avg <= 24 && rs > refScore && rs >= 0.4) { refScore = rs; refCol = tc; }
        });
        textCols.forEach(function (tc) {
            if (tc === refCol) return;
            var avg = st[tc].textLen / Math.max(1, st[tc].n);
            if (avg > descLen) { descLen = avg; descCol = tc; }
        });
        if (refCol >= 0) map.ref = refCol;
        if (descCol >= 0) map.desc = descCol;
        return map;
    };

    // ── كلمات التصنيف ───────────────────────────────────────────────────────────
    var OPENING_RE = new RegExp(N('(رصيد\\s*(ال)?(افتتاحي|سابق|مدور|منقول|مرحل|اول المده|بدايه|اول الفتره)|المنقول|منقول من|مرحل من|ما قبله|اول المده|بدايه الفتره|رصيد اول|opening|brought forward|balance b\\/?f|b\\/f|b\\/d|previous balance|balance brought|بدايه المده|رصيد بدايه)'));
    var CARRY_OUT_RE = new RegExp(N('(مرحل ل|منقول ل|ما بعده|ينقل|الي الصفحه|carried forward|c\\/f|c\\/d|carry forward|to next page|مجموع الصفحه)'));
    var TOTAL_RE = new RegExp(N('(^|\\s)(الاجمالي|اجمالي|المجموع|مجموع|الجمله|جمله|total|sub ?total|grand total|اجمالي الحركه|مجموع الحركات|الرصيد الختامي|رصيد ختامي|الرصيد النهائي|رصيد نهايه|الرصيد الحالي|closing balance|ending balance|balance c\\/d|الرصيد المستحق|صافي الرصيد)(\\s|$)'));
    var INVOICE_RE = new RegExp(N('(فاتوره|فواتير|invoice|\\binv\\b|مشتريات|purchase|bill|قيد فاتوره|اشعار مدين|debit note)'));
    var PAYMENT_RE = new RegExp(N('(دفعه|دفعات|سداد|payment|\\bpmt\\b|سند صرف|سند قبض|تحويل|حواله|شيك|cheque|\\bcheck\\b|receipt|transfer|نقدي|مدفوع|bank|بنك)'));
    var DECREASE_RE = new RegExp(N('(اشعار دائن|credit note|مرتجع|مردودات|return|خصم|discount|تسويه|حسم|اشعار تخفيض|cn\\b)'));
    SM.words = { OPENING_RE: OPENING_RE, TOTAL_RE: TOTAL_RE, INVOICE_RE: INVOICE_RE, PAYMENT_RE: PAYMENT_RE, DECREASE_RE: DECREASE_RE };

    function cellStr(v) { return v == null ? '' : String(v).trim(); }
    function numCell(row, col) {
        if (col === undefined || col === null) return null;
        var v = row[col];
        if (v === '' || v == null) return null;
        if (typeof v === 'number') return { v: v, drcr: null };
        return SM.parseNumberEx(v) || (function () { var m = SM.extractMoney(v); return m === null ? null : { v: m, drcr: null }; })();
    }

    /** يحوّل الصفوف بعد الترويسة إلى مدخلات خام (date/ref/desc/debit/credit/amount/balance بالهللات) بلا تصنيف. */
    SM.parseEntries = function (rows, map, startRow, opts) {
        opts = opts || {};
        var out = [];
        for (var i = startRow; i < rows.length; i++) {
            var row = rows[i] || [];
            if (!row.some(function (x) { return x !== '' && x != null; })) continue;
            var d = numCell(row, map.debit), cr = numCell(row, map.credit), a = numCell(row, map.amount), b = numCell(row, map.balance);
            var dateRaw = map.date !== undefined ? row[map.date] : '';
            var e = {
                row: i, date: SM.parseDate(dateRaw, opts.dayFirst !== false),
                ref: cellStr(map.ref !== undefined ? row[map.ref] : ''), desc: cellStr(map.desc !== undefined ? row[map.desc] : ''),
                debit: d ? SM.cents(d.v) : 0, credit: cr ? SM.cents(cr.v) : 0, amount: a ? SM.cents(a.v) : 0,
                bal: b ? SM.cents(b.v) : null, balDrcr: b ? b.drcr : null, hasDebit: !!d, hasCredit: !!cr, hasAmount: !!a,
                raw: row.map(cellStr).join(' | ')
            };
            if (map.desc === undefined) e.desc = row.filter(function (v, idx) { return typeof v === 'string' && v.trim() && idx !== map.ref && idx !== map.date && SM.parseNumber(v) === null; }).join(' ').trim();
            out.push(e);
        }
        return out;
    };

    function hasMoney(e) { return !!(e.debit || e.credit || e.amount); }

    /** يصنّف كل مدخل: opening | txn | total | carry | blank (ويحفظ السبب). */
    SM.classifyEntries = function (entries) {
        var firstTxnSeen = false;
        var dated = entries.filter(function (e) { return e.date && hasMoney(e); }), asc = 0, dsc = 0;
        for (var i = 1; i < dated.length; i++) { if (dated[i].date > dated[i - 1].date) asc++; else if (dated[i].date < dated[i - 1].date) dsc++; }
        var order = entries.map(function (e, idx) { return idx; });
        if (dsc > asc) order.reverse();                          // كشف تنازلي: الافتتاحي في آخر الملف، فنصنّف من الأقدم
        order.forEach(function (idx) {
            var e = entries[idx];
            var n = N(e.desc + ' ' + e.ref);
            e.kind = 'txn'; e.why = '';
            if (!hasMoney(e) && e.bal === null) { e.kind = 'blank'; return; }
            if (OPENING_RE.test(n) && !CARRY_OUT_RE.test(n)) {
                e.kind = firstTxnSeen ? 'carry' : 'opening';
                e.why = firstTxnSeen ? 'مرحَّل مكرر في أعلى صفحة' : 'سطر رصيد افتتاحي';
                return;
            }
            if (CARRY_OUT_RE.test(n)) { e.kind = 'carry'; e.why = 'مرحَّل لصفحة تالية'; return; }
            if (TOTAL_RE.test(n)) { e.kind = 'total'; e.why = 'سطر إجمالي'; return; }
            if (!hasMoney(e) && e.bal !== null) {
                if (!firstTxnSeen && !e.date && !e.ref) { e.kind = 'opening'; e.why = 'سطر برصيد فقط في أول الكشف'; }
                else { e.kind = 'total'; e.why = 'سطر برصيد فقط'; }
                return;
            }
            // أول سطر مالي بلا تاريخ ولا رقم مرجعي (ولا كلمات فاتورة/سداد): رصيد افتتاحي حتى لو كان وصفه ناقصًا (OCR)
            if (hasMoney(e) && !e.date && !/\d/.test(e.ref) && !INVOICE_RE.test(n) && !PAYMENT_RE.test(n) && !firstTxnSeen) { e.kind = 'opening'; e.why = 'أول سطر بلا تاريخ ولا مرجع'; return; }
            firstTxnSeen = true;
        });
        // إجماليات بلا عنوان: آخر سطر مجموع أعمدة ما قبله
        var txns = entries.filter(function (e) { return e.kind === 'txn'; });
        for (var k = entries.length - 1; k >= 0; k--) {
            var e = entries[k];
            if (e.kind === 'blank' || e.kind === 'total') continue;
            if (e.kind !== 'txn') break;
            if (e.date || e.ref) break;
            var before = txns.filter(function (t) { return t !== e && t.row < e.row; });
            var sd = before.reduce(function (s, t) { return s + t.debit; }, 0), sc = before.reduce(function (s, t) { return s + t.credit; }, 0);
            if (before.length >= 2 && ((e.debit && Math.abs(e.debit - sd) <= 1) || (e.credit && Math.abs(e.credit - sc) <= 1))) {
                e.kind = 'total'; e.why = 'مجموع أعمدة بلا عنوان';
            }
            break;
        }
        return entries;
    };

    // ── اتجاه الحركة ────────────────────────────────────────────────────────────
    /** يُرجع {debitIncreases, auto, evidence}. sideDefault: true للمورد (المدين يزيد المستحق)، false لدفاترنا. */
    SM.detectOrientation = function (entries, sideDefault) {
        var score = 0, ev = 0;
        entries.forEach(function (e) {
            if (e.kind !== 'txn') return;
            var n = N(e.desc + ' ' + e.ref);
            var inv = INVOICE_RE.test(n) && !DECREASE_RE.test(n), pay = PAYMENT_RE.test(n) || DECREASE_RE.test(n);
            var w = inv ? 1 : (pay ? -1 : 0);
            if (!w) return;
            if (e.debit && !e.credit) { score += w; ev++; }
            else if (e.credit && !e.debit) { score -= w; ev++; }
        });
        if (ev >= 2 && score !== 0) return { debitIncreases: score > 0, auto: true, evidence: ev };
        return { debitIncreases: !!sideDefault, auto: false, evidence: ev };
    };

    function movement(e, debitIncreases) {
        if (e.hasAmount && !e.hasDebit && !e.hasCredit) return debitIncreases ? e.amount : -e.amount;
        return debitIncreases ? e.debit - e.credit : e.credit - e.debit;
    }

    // ── البناء النهائي: فتح، إغلاق، ترتيب، تكامل ───────────────────────────────
    SM.finalizeSide = function (entries, o) {
        o = o || {};
        var tol = typeof o.tolerance === 'number' ? o.tolerance : 1;                // هللة
        var side = { entries: entries, warnings: [], tol: tol };
        var orient = o.orientation || SM.detectOrientation(entries, o.sideDefault);
        side.orient = orient;
        var txns = entries.filter(function (e) { return e.kind === 'txn'; });
        txns.forEach(function (e) { e.m = movement(e, orient.debitIncreases); });

        // أرصدة Dr/Cr: الأقلية تُقلب
        var withDr = entries.filter(function (e) { return e.bal !== null && e.balDrcr; });
        if (withDr.length) {
            var drN = withDr.filter(function (e) { return e.balDrcr === 'dr'; }).length, majority = drN >= withDr.length - drN ? 'dr' : 'cr';
            withDr.forEach(function (e) { if (e.balDrcr !== majority) e.bal = -e.bal; });
        }

        // ترتيب زمني: الكشف التنازلي يُعاد ترتيبه من الأقدم
        var dated = txns.filter(function (e) { return e.date; }), asc = 0, desc = 0;
        for (var i = 1; i < dated.length; i++) { if (dated[i].date > dated[i - 1].date) asc++; else if (dated[i].date < dated[i - 1].date) desc++; }
        side.reversed = desc > asc && o.autoReverse !== false;
        var ordered = side.reversed ? txns.slice().reverse() : txns.slice();

        // اتجاه عمود الرصيد (balSign): +1 إن كان الرصيد يزيد مع زيادة المستحق للمورد
        var chainRows = ordered.filter(function (e) { return e.bal !== null; }), fitPos = 0, fitNeg = 0, tried = 0;
        for (var j = 1; j < chainRows.length; j++) {
            if (chainRows[j - 1].bal === null) continue;
            var delta = chainRows[j].bal - chainRows[j - 1].bal;
            if (ordered.indexOf(chainRows[j]) - ordered.indexOf(chainRows[j - 1]) !== 1) continue;
            tried++;
            if (Math.abs(delta - chainRows[j].m) <= tol) fitPos++;
            if (Math.abs(delta + chainRows[j].m) <= tol) fitNeg++;
        }
        side.balSign = (tried && fitNeg > fitPos) ? -1 : 1;
        var norm = function (b) { return b === null ? null : side.balSign * b; };

        // الرصيد الافتتاحي: سطر مُسمّى ← ترويسة ← أول رصيد ← مشتق
        var openingEntry = entries.filter(function (e) { return e.kind === 'opening'; })[0], opening = null, src = '', derived = null;
        var firstIdx = -1;
        for (var q = 0; q < ordered.length; q++) { if (ordered[q].bal !== null) { firstIdx = q; break; } }
        if (firstIdx >= 0) {
            derived = norm(ordered[firstIdx].bal) - ordered.slice(0, firstIdx + 1).reduce(function (s2, e) { return s2 + e.m; }, 0);
        }
        if (typeof o.openingOverride === 'number') { opening = o.openingOverride; src = 'مُدخَل يدويًا'; }
        else if (openingEntry) {
            var ov = openingEntry.bal !== null ? norm(openingEntry.bal) : (hasMoney(openingEntry) ? movement(openingEntry, orient.debitIncreases) : null);
            if (ov !== null) { opening = ov; src = 'السطر ' + (openingEntry.row + 1) + ': ' + (openingEntry.desc || 'رصيد افتتاحي'); }
        }
        if (opening === null && typeof o.headerOpening === 'number') { opening = o.headerOpening; src = 'من رأس الكشف'; }
        if (opening === null && derived !== null) { opening = derived; src = 'محسوب من رصيد أول حركة'; }
        if (opening === null) { opening = 0; src = 'غير موجود (يُعتبر صفرًا)'; }
        side.opening = opening; side.openingSource = src; side.openingDerived = derived;
        if (derived !== null && Math.abs(derived - opening) > tol && src !== 'محسوب من رصيد أول حركة') {
            side.warnings.push({ code: 'opening-conflict', text: 'الرصيد الافتتاحي (' + SM.fmt(opening / 100) + ') لا يتسق مع رصيد أول حركة؛ القيمة المتسقة ' + SM.fmt(derived / 100), suggest: derived });
        }

        // سلسلة الرصيد الجاري
        var run = opening, mism = 0;
        ordered.forEach(function (e) {
            run += e.m; e.balCalc = run; e.flags = e.flags || [];
            e.flags = e.flags.filter(function (f) { return f !== 'balance'; });
            if (e.bal !== null && Math.abs(norm(e.bal) - run) > tol) { e.flags.push('balance'); e.balExpected = run; mism++; }
        });
        side.txns = ordered;
        side.closingComputed = run;
        var lastPrinted = ordered.slice().reverse().filter(function (e) { return e.bal !== null; })[0];
        var closingEntry = entries.filter(function (e) { return e.kind === 'total' && e.bal !== null; }).slice(-1)[0];
        side.closingPrinted = closingEntry ? norm(closingEntry.bal) : (lastPrinted ? norm(lastPrinted.bal) : null);
        side.balanceCheck = { mismatches: mism, ok: mism === 0 };
        if (side.closingPrinted !== null && Math.abs(side.closingPrinted - run) > tol) {
            side.warnings.push({ code: 'closing-mismatch', text: 'الرصيد الختامي المطبوع (' + SM.fmt(side.closingPrinted / 100) + ') يختلف عن المحسوب (' + SM.fmt(run / 100) + ')' });
        }
        if (mism) side.warnings.push({ code: 'balance-chain', text: mism + ' سطر لا يتسق رصيده الجاري مع الحركة (مظلَّلة بالبرتقالي)' });
        side.totals = { debit: txns.reduce(function (s, e) { return s + e.debit + (e.hasAmount && e.m > 0 && !e.hasDebit && !e.hasCredit && orient.debitIncreases ? e.amount : 0); }, 0),
            credit: txns.reduce(function (s, e) { return s + e.credit; }, 0) };
        var dts = ordered.filter(function (e) { return e.date; }).map(function (e) { return e.date; }).sort();
        side.period = { from: dts[0] || null, to: dts[dts.length - 1] || null };
        side.count = ordered.length;
        if (!ordered.length) side.warnings.push({ code: 'empty', text: 'لم تُستخرج أي حركة من هذا الجانب' });
        return side;
    };

    // ── تحليل ملف كامل: ترويسة + أعمدة + تصنيف + بناء ───────────────────────────
    SM.analyzeTable = function (table, o) {
        o = o || {};
        var rows = table.rows || [], mapInfo = SM.findHeader(rows), map, start, how;
        if (o.map) { map = o.map; start = typeof o.startRow === 'number' ? o.startRow : (mapInfo ? mapInfo.end + 1 : 0); how = 'manual'; }
        else if (mapInfo) { map = mapInfo.map; start = mapInfo.end + 1; how = 'header'; }
        else { start = 0; map = SM.inferColumns(rows, 0); how = 'inferred'; }
        var entries = SM.parseEntries(rows, map, start, o);
        entries.forEach(function (e, i) { e.conf = table.confs && table.confs[e.row] !== undefined ? table.confs[e.row] : 100; });
        var pre = (table.preface || []).concat(rows.slice(0, Math.max(0, start)).map(function (r) { return r.map(cellStr).join(' '); }));
        return { entries: entries, map: map, start: start, how: how, pre: pre, name: table.name || '', rows: rows };
    };

    function scanPreface(pre) {
        var headerOpening = null, party = '';
        pre.forEach(function (line) {
            var n = N(line);
            if (headerOpening === null && OPENING_RE.test(n)) {
                var m = SM.extractMoney(line.replace(/.*?[:：]/, ''));
                if (m !== null) headerOpening = SM.cents(m);
            }
            if (!party) {
                var pm = line.match(/(?:اسم\s*)?(?:المورد|العميل|الحساب|supplier|vendor|customer|account name)\s*[:：\-]\s*(.+)/i);
                if (pm) party = pm[1].replace(/\s{2,}.*/, '').trim();
            }
        });
        return { headerOpening: headerOpening, party: party };
    }

    function diagnose(side, entries, rows, map) {
        if (side.txns.length) return;
        var money = entries.filter(hasMoney).length;
        side.diagnosis = !rows.length ? 'لم تُقرأ أي بيانات من الملف' : (map.debit === undefined && map.credit === undefined && map.amount === undefined)
            ? 'لم يُحدَّد عمود للمبالغ (مدين/دائن/المبلغ). عيّنه من قائمة الأعمدة'
            : (money && entries.every(function (e) { return e.kind !== 'txn'; }) ? 'كل الأسطر صُنّفت كأرصدة أو إجماليات؛ راجع تصنيف الأسطر' : 'لم تُعثر على حركات بعد صف الترويسة');
    }

    /** tables: جدول واحد أو عدة جداول (ملفات متعددة لنفس الجانب). o: {sideDefault, tolerance, orientation, openingOverride, dayFirst, map} */
    SM.parseSide = function (tables, o) {
        o = o || {};
        var list = Array.isArray(tables) ? tables : [tables];
        var parts = list.map(function (t, idx) { var a = SM.analyzeTable(t, idx === 0 ? o : Object.assign({}, o, { map: undefined })); a.fileIdx = idx; return a; });
        var entries = [];
        if (parts.length > 1) {
            parts.forEach(function (p) { p.min = p.entries.filter(function (e) { return e.date; }).map(function (e) { return e.date; }).sort()[0] || '9999'; });
            parts.sort(function (a, b) { return a.min < b.min ? -1 : a.min > b.min ? 1 : a.fileIdx - b.fileIdx; });
        }
        parts.forEach(function (p) { p.entries.forEach(function (e) { e.file = p.name; }); entries = entries.concat(p.entries); });
        SM.classifyEntries(entries);
        var scan = scanPreface(parts.reduce(function (acc, p) { return acc.concat(p.pre); }, []));
        var side = SM.finalizeSide(entries, { sideDefault: o.sideDefault, tolerance: o.tolerance, headerOpening: scan.headerOpening === null ? undefined : scan.headerOpening,
            orientation: o.orientation, openingOverride: o.openingOverride, autoReverse: o.autoReverse });
        var first = parts[0];
        side.map = first.map; side.mapHow = first.how; side.startRow = first.start; side.party = scan.party; side.fileName = parts.map(function (p) { return p.name; }).filter(Boolean).join('، ');
        side.rawRows = first.rows; side.parts = parts.length;
        diagnose(side, entries, first.rows, first.map);
        return side;
    };

    /** يعيد حساب الجانب بعد تعديل المستخدم (نوع سطر، مبلغ، تاريخ...) دون إعادة قراءة الملف. */
    SM.recomputeSide = function (side, o) {
        o = o || {};
        side.entries.forEach(function (e) { delete e.flags; });
        var re = SM.finalizeSide(side.entries, { sideDefault: o.sideDefault, tolerance: o.tolerance, headerOpening: o.headerOpening, orientation: o.orientation || side.orient,
            openingOverride: o.openingOverride, autoReverse: o.autoReverse === undefined ? false : o.autoReverse });
        ['map', 'mapHow', 'startRow', 'party', 'fileName', 'rawRows', 'parts'].forEach(function (k) { re[k] = side[k]; });
        return re;
    };

    SM.parseCurrencyInput = function (s) { var n = SM.parseNumber(s); return n === null ? undefined : SM.cents(n); };

    if (typeof module !== 'undefined' && module.exports) module.exports = SM;
})(typeof window !== 'undefined' ? window : globalThis);
