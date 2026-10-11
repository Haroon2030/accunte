/* مطابق كشوفات الحساب — المخرجات: ملخص نصي، تقرير المطابقة، خطاب المورد، وتصدير Excel بعشر أوراق.
   لا ذكاء اصطناعي هنا: كله من نتائج المحرك. المبالغ تُعرض #,##0.00 والسالب = المورد مدين لنا. */
(function (g) {
    'use strict';
    var SM = g.SM = g.SM || {};
    var E = SM.escapeHtml, F = function (c) { return SM.fmt(c / 100); };
    var D = SM.isoToDisplay;

    var CAT = {
        'invoice-not-in-ours': 'فاتورة لدى المورد غير مسجَّلة عندنا', 'goods-in-transit': 'فاتورة بضاعة/خدمة في الطريق', 'credit-note-not-recorded': 'إشعار دائن/خصم/مرتجع لدى المورد وليس عندنا',
        'unexpected-payment': 'دفعة يذكرها المورد ولا نجدها', 'debit-note': 'إشعار مدين من المورد', 'credit-not-in-ours': 'قيد دائن لدى المورد',
        'payment-in-transit': 'دفعة/شيك في الطريق', 'payment-not-posted': 'دفعة لم يسجّلها المورد', 'unaccepted-note': 'إشعار/مرتجع لم يقبله المورد',
        'invoice-not-in-supplier': 'فاتورة عندنا وليست في كشف المورد', 'ours-credit-only': 'قيد عندنا بلا مقابل', duplicate: 'قيد مكرر', cutoff: 'فصل فترات',
        'amount-diff': 'فرق مبلغ', 'sign-flip': 'انعكاس اتجاه'
    };
    SM.categoryLabel = function (k) { return CAT[k] || k; };
    var SEV = { 3: 'عاجل', 2: 'متوسط', 1: 'منخفض' };
    SM.severityLabel = function (n) { return SEV[n] || ''; };

    var STATUS = {
        matched: { label: 'متطابق', tone: 'ok', line: 'الرصيدان متطابقان ولا يوجد فرق.' },
        explained: { label: 'الفرق مفسَّر — يحتاج متابعة', tone: 'warn', line: 'الفرق بين الرصيدين مفسَّر ببنود محددة تحتاج متابعة.' },
        unexplained: { label: 'يوجد فرق غير مفسَّر', tone: 'bad', line: 'بقي فرق لم تُفسّره حركات الكشفين؛ راجع سلامة الكشف والرصيد الافتتاحي.' }
    };
    SM.statusInfo = function (s) { return STATUS[s]; };

    function party(ctx, res) { return ctx.supplierName || res.supplier.party || res.ours.party || 'المورد'; }
    function period(res) {
        var from = [res.ours.period.from, res.supplier.period.from].filter(Boolean).sort()[0], to = [res.ours.period.to, res.supplier.period.to].filter(Boolean).sort().reverse()[0];
        return from && to ? D(from) + ' – ' + D(to) : '';
    }
    function sum(arr, f) { return arr.reduce(function (s, x) { return s + f(x); }, 0); }

    /** سطور الجسر بالترتيب: [{label, amount(سنتات), note}] */
    SM.bridgeLines = function (res) {
        var b = res.bridge, lines = [];
        lines.push({ key: 'ours', label: 'رصيد دفاترنا', amount: b.oursClosing, kind: 'start' });
        lines.push({ key: 'open', label: 'فرق الرصيد الافتتاحي', amount: b.openingDiff, note: 'مرحَّل من فترات سابقة' });
        lines.push({ key: 'sup', label: 'حركات عند المورد وليست عندنا (+)', amount: b.supplierOnly, note: res.supplierOnly.length + ' حركة' });
        lines.push({ key: 'our', label: 'حركات عندنا وليست عند المورد (−)', amount: b.oursOnly, note: res.oursOnly.length + ' حركة' });
        lines.push({ key: 'diff', label: 'فروق مبالغ في مستندات مشتركة', amount: b.amountDiffs, note: res.diffs.length + ' مستند' });
        lines.push({ key: 'flip', label: 'قيود بعكس الاتجاه', amount: b.signFlips, note: res.flips.length + ' قيد' });
        lines.push({ key: 'exp', label: 'الرصيد المتوقع عند المورد', amount: b.expected, kind: 'subtotal' });
        lines.push({ key: 'sclose', label: 'رصيد كشف المورد', amount: b.supplierClosing, kind: 'subtotal' });
        lines.push({ key: 'unx', label: 'فرق غير مفسَّر', amount: b.unexplained, kind: 'result', note: 'تقريب أو خطأ حسابي داخل أحد الكشفين' });
        return lines;
    };

    SM.summaryParts = function (res, ctx) {
        var b = res.bridge, st = STATUS[res.status];
        var parts = [];
        if (b.openingDiff) parts.push('فرق الرصيد الافتتاحي ' + F(b.openingDiff));
        if (res.supplierOnly.length) parts.push(res.supplierOnly.length + ' حركة عند المورد فقط (' + F(b.supplierOnly) + ')');
        if (res.oursOnly.length) parts.push(res.oursOnly.length + ' حركة عندنا فقط (' + F(b.oursOnly) + ')');
        if (res.diffs.length) parts.push(res.diffs.length + ' فرق مبلغ (' + F(b.amountDiffs) + ')');
        if (res.flips.length) parts.push(res.flips.length + ' قيد معكوس الاتجاه (' + F(b.signFlips) + ')');
        if (Math.abs(b.unexplained) > res.options.tolCents) parts.push('فرق غير مفسَّر ' + F(b.unexplained));
        return { status: st, breakdown: parts.join('، '), top: res.actions.slice(0, 5) };
    };

    SM.summaryText = function (res, ctx) {
        ctx = ctx || {};
        var sp = SM.summaryParts(res, ctx), b = res.bridge, L = [];
        L.push('ملخص مطابقة كشف حساب — ' + (ctx.company || ''));
        L.push('المورد: ' + party(ctx, res) + (period(res) ? ' | الفترة: ' + period(res) : ''));
        L.push('الحالة: ' + sp.status.label);
        L.push('رصيد دفاترنا: ' + F(b.oursClosing) + ' | رصيد كشف المورد: ' + F(b.supplierClosing) + ' | الفرق: ' + F(b.gross));
        L.push('حركات متطابقة: ' + res.kpis.matched + ' من ' + res.kpis.ours + ' (دفاترنا) و' + res.kpis.supplier + ' (المورد)');
        if (sp.breakdown) L.push('تفصيل الفرق: ' + sp.breakdown + '.');
        if (sp.top.length) {
            L.push('أهم الإجراءات:');
            sp.top.forEach(function (a, i) { L.push((i + 1) + '. ' + CAT[a.cat] + (a.ref ? ' [' + a.ref + ']' : '') + ' — ' + F(a.amount) + ' — ' + a.action); });
        }
        return L.join('\n');
    };

    // ── جداول HTML مشتركة ───────────────────────────────────────────────────────
    function money(c, cls) { return '<td class="num ' + (cls || '') + '" dir="ltr">' + (c === 0 ? '<span class="zero">0.00</span>' : F(c)) + '</td>'; }
    function table(headers, rows, opts) {
        opts = opts || {};
        if (!rows.length) return '<p class="empty">' + (opts.empty || 'لا توجد بنود') + '</p>';
        return '<table class="sm-table"><thead><tr>' + headers.map(function (h) { return '<th>' + E(h) + '</th>'; }).join('') + '</tr></thead><tbody>' + rows.join('') + '</tbody>' +
            (opts.foot ? '<tfoot>' + opts.foot + '</tfoot>' : '') + '</table>';
    }
    function bridgeHtml(res) {
        return '<table class="sm-bridge"><tbody>' + SM.bridgeLines(res).map(function (l) {
            var sign = (!l.kind && l.amount > 0) ? '+' : '';
            return '<tr class="' + (l.kind || 'line') + '"><td class="lbl">' + E(l.label) + (l.note ? '<small>' + E(l.note) + '</small>' : '') + '</td><td class="num" dir="ltr">' + sign + F(l.amount) + '</td></tr>';
        }).join('') + '</tbody></table>';
    }
    SM.bridgeHtml = bridgeHtml;

    function entryRows(list, cols) {
        return list.map(function (x) {
            var e = x.e;
            return '<tr><td>' + E(D(e.date)) + '</td><td dir="ltr">' + E(e.ref) + '</td><td>' + E(e.desc) + '</td>' + money(e.m) + '<td>' + E(CAT[x.cat] || '') + '</td><td>' + E(x.action) + '</td></tr>';
        });
    }

    // ── التقرير المضمَّن ────────────────────────────────────────────────────────
    SM.buildReportHtml = function (res, ctx) {
        ctx = ctx || {};
        var sp = SM.summaryParts(res, ctx), b = res.bridge, h = [];
        h.push('<header class="doc-head"><div><h1>تقرير مطابقة كشف حساب مورد</h1><p>' + E(ctx.company || '') + '</p></div><div class="doc-meta"><div>المورد: <b>' + E(party(ctx, res)) + '</b></div><div>الفترة: ' + E(period(res)) + '</div><div>تاريخ الإعداد: ' + E(D(new Date().toISOString().slice(0, 10))) + '</div></div></header>');
        h.push('<section><h2>١. الخلاصة</h2><p class="verdict ' + sp.status.tone + '"><b>' + E(sp.status.label) + '</b> — ' + E(sp.status.line) + '</p>');
        h.push('<table class="sm-kv"><tr><th>رصيد دفاترنا</th><td dir="ltr">' + F(b.oursClosing) + '</td><th>رصيد كشف المورد</th><td dir="ltr">' + F(b.supplierClosing) + '</td><th>الفرق الإجمالي</th><td dir="ltr"><b>' + F(b.gross) + '</b></td></tr></table>');
        h.push('<p>' + E(sp.breakdown ? 'يتكوّن الفرق من: ' + sp.breakdown + '.' : 'لا توجد بنود فرق.') + '</p></section>');
        h.push('<section><h2>٢. جسر المطابقة</h2>' + bridgeHtml(res) + '</section>');

        var timing = res.supplierOnly.concat(res.oursOnly).filter(function (x) { return x.kind === 'timing'; }), errors = res.supplierOnly.concat(res.oursOnly).filter(function (x) { return x.kind !== 'timing'; });
        h.push('<section><h2>٣. تحليل الفرق حسب النوع</h2>');
        var byCat = {};
        res.supplierOnly.concat(res.oursOnly).forEach(function (x) { var k = x.cat; byCat[k] = byCat[k] || { n: 0, sum: 0, kind: x.kind }; byCat[k].n++; byCat[k].sum += x.e.m * (x.e.side === 'ours' ? -1 : 1); });
        res.diffs.forEach(function (d) { var k = 'amount-diff'; byCat[k] = byCat[k] || { n: 0, sum: 0, kind: 'error' }; byCat[k].n++; byCat[k].sum += d.diff; });
        if (res.flips.length) byCat['sign-flip'] = { n: res.flips.length, sum: b.signFlips, kind: 'error' };
        var catRows = Object.keys(byCat).map(function (k) { return '<tr><td>' + E(CAT[k]) + '</td><td>' + (byCat[k].kind === 'timing' ? 'توقيت (يزول وحده)' : 'يحتاج تصحيحًا/متابعة') + '</td><td class="num">' + byCat[k].n + '</td>' + money(byCat[k].sum) + '</tr>'; });
        h.push(table(['النوع', 'الطبيعة', 'العدد', 'الأثر على الفرق'], catRows, { empty: 'لا توجد فروق' }));
        h.push('<p class="note">فروق التوقيت: ' + F(sum(timing, function (x) { return x.e.m * (x.e.side === 'ours' ? -1 : 1); })) + ' — فروق تحتاج تصحيحًا: ' + F(sum(errors, function (x) { return x.e.m * (x.e.side === 'ours' ? -1 : 1); }) + b.amountDiffs + b.signFlips) + '.</p></section>');

        h.push('<section><h2>٤. الإجراءات حسب الأولوية</h2>');
        h.push(table(['الأولوية', 'البند', 'المرجع', 'التاريخ', 'المبلغ', 'الإجراء المقترح'], res.actions.map(function (a) {
            return '<tr class="sev' + a.sev + '"><td>' + SEV[a.sev] + '</td><td>' + E(CAT[a.cat] + (a.text && a.cat === 'amount-diff' ? ': ' + a.text : '')) + '</td><td dir="ltr">' + E(a.ref || '') + '</td><td>' + E(D(a.date)) + '</td>' + money(a.amount) + '<td>' + E(a.action) + '</td></tr>';
        }), { empty: 'لا توجد إجراءات مطلوبة' }));
        if (b.openingDiff) h.push('<p class="note"><b>الرصيد الافتتاحي:</b> يختلف بين الطرفين بمقدار ' + F(b.openingDiff) + '؛ طابق كشف الفترة السابقة أولًا لأن أصل الفرق فيها.</p>');
        h.push('</section>');

        var je = SM.proposedEntries(res);
        h.push('<section><h2>٥. قيود تسوية مقترحة (أخطاء مثبتة من جانبنا فقط)</h2>');
        h.push(je.length ? table(['القيد', 'المدين', 'الدائن', 'المبلغ', 'ملاحظة'], je.map(function (j) { return '<tr><td>' + E(j.title) + '</td><td>' + E(j.dr) + '</td><td>' + E(j.cr) + '</td>' + money(j.amount) + '<td>' + E(j.note) + '</td></tr>'; })) : '<p class="empty">لا توجد قيود مقترحة؛ لا يُقيَّد شيء قبل وصول المستند المؤيِّد.</p>');
        h.push('<p class="note">لا يُرحَّل أي قيد قبل الحصول على المستند الأصلي (الفاتورة أو الإشعار) والتحقق منه.</p></section>');

        var risks = SM.riskFlags(res);
        h.push('<section><h2>٦. مؤشرات المخاطر</h2>' + (risks.length ? '<ul>' + risks.map(function (r) { return '<li>' + E(r) + '</li>'; }).join('') + '</ul>' : '<p class="empty">لا توجد مؤشرات مخاطر.</p>') + '</section>');
        if (Math.abs(b.unexplained) > res.options.tolCents) {
            h.push('<section><h2>٧. أين نبحث عن الفرق غير المفسَّر (' + F(b.unexplained) + ')</h2><ul><li>تحقق من الرصيد الافتتاحي لدى الطرفين ومن أي فترة سابقة غير مطابقة.</li><li>راجع «سلامة الكشف»: أسطر لا يتسق رصيدها الجاري، أو رصيد ختامي مطبوع يخالف المحسوب.</li><li>راجع قراءة الأرقام في الملفات الممسوحة (OCR): الخطأ في رقم واحد يُنتج فرقًا كاملًا.</li><li>ابحث عن مستند مفقود بمبلغ ' + F(Math.abs(b.unexplained)) + ' أو بمبلغ مقارب في أحد الكشفين.</li></ul></section>');
        }
        return '<article class="doc">' + h.join('') + '</article>';
    };

    SM.proposedEntries = function (res) {
        var out = [];
        res.diffs.forEach(function (d) {
            var amt = Math.abs(d.diff);
            if (d.reason === 'vat-excl' && d.diff > 0) out.push({ title: 'تحميل ضريبة القيمة المضافة غير المقيَّدة — ' + (d.a.ref || d.b.ref), dr: 'ضريبة مدخلات / مصروف', cr: 'حساب المورد', amount: amt, note: 'يُقيَّد فقط إن ثبت أن فاتورة المورد شاملة الضريبة' });
            if (d.reason === 'rounding') out.push({ title: 'تسوية فرق تقريب — ' + (d.a.ref || d.b.ref), dr: d.diff > 0 ? 'فروق تقريب' : 'حساب المورد', cr: d.diff > 0 ? 'حساب المورد' : 'فروق تقريب', amount: amt, note: 'ضمن حد التسامح' });
        });
        res.oursOnly.concat(res.supplierOnly).forEach(function (x) {
            if (x.cat === 'duplicate' && x.e.side === 'ours') out.push({ title: 'عكس قيد مكرر — ' + (x.e.ref || ''), dr: 'حساب المورد', cr: 'المصروف/المشتريات', amount: Math.abs(x.e.m), note: 'بعد التأكد من أن التكرار عندنا' });
        });
        return out;
    };

    SM.riskFlags = function (res) {
        var out = [];
        var dups = res.supplierOnly.concat(res.oursOnly).filter(function (x) { return x.cat === 'duplicate'; });
        if (dups.length) out.push('قيود مكررة (' + dups.length + ') قد تعني دفعًا أو تسجيلًا مزدوجًا.');
        var big = res.actions.filter(function (a) { return a.amount >= 1000000; });
        if (big.length) out.push('بنود كبيرة (≥ 10,000.00) بين الإجراءات: ' + big.length + '.');
        if (res.flips.length) out.push('قيود معكوسة الاتجاه (' + res.flips.length + ') تضاعف أثرها على الرصيد.');
        if (!res.ours.balanceCheck.ok) out.push('رصيد دفاترنا الجاري غير متسق في ' + res.ours.balanceCheck.mismatches + ' سطر.');
        if (!res.supplier.balanceCheck.ok) out.push('رصيد كشف المورد الجاري غير متسق في ' + res.supplier.balanceCheck.mismatches + ' سطر.');
        var unp = res.oursOnly.filter(function (x) { return x.cat === 'payment-not-posted'; });
        if (unp.length) out.push('دفعات لم يسجّلها المورد (' + unp.length + '): خطر مطالبة مكررة بها.');
        if (res.bridge.openingDiff) out.push('اختلاف الرصيد الافتتاحي ' + F(res.bridge.openingDiff) + ' يدل على فترة سابقة غير مطابقة.');
        return out;
    };

    // ── خطاب المورد ─────────────────────────────────────────────────────────────
    SM.buildLetterHtml = function (res, ctx) {
        ctx = ctx || {};
        var name = party(ctx, res), b = res.bridge, h = [];
        var pay = res.oursOnly.filter(function (x) { return x.cat === 'payment-in-transit' || x.cat === 'payment-not-posted'; });
        var notes = res.oursOnly.filter(function (x) { return x.cat === 'unaccepted-note'; });
        var missing = res.supplierOnly.filter(function (x) { return x.cat === 'invoice-not-in-ours' || x.cat === 'goods-in-transit' || x.cat === 'debit-note'; });
        var ours = res.oursOnly.filter(function (x) { return x.cat === 'invoice-not-in-supplier'; });
        h.push('<article class="doc letter"><header class="doc-head"><div><h1>' + E(ctx.company || '') + '</h1></div><div class="doc-meta"><div>التاريخ: ' + E(D(new Date().toISOString().slice(0, 10))) + '</div></div></header>');
        h.push('<p>السادة / <b>' + E(name) + '</b> المحترمين</p><p>السلام عليكم ورحمة الله وبركاته،،</p>');
        h.push('<p><b>الموضوع: مطابقة كشف الحساب' + (period(res) ? ' عن الفترة ' + E(period(res)) : '') + '</b></p>');
        h.push('<p>بعد مطابقة كشف حسابكم مع سجلاتنا، تبيّن أن رصيد دفاترنا ' + F(b.oursClosing) + ' بينما رصيد كشفكم ' + F(b.supplierClosing) + '، بفرق قدره ' + F(b.gross) + '. نرجو مراجعة البنود التالية وإفادتنا:</p>');
        if (pay.length) h.push('<h3>١. دفعات سُدِّدت من طرفنا ولم تظهر في كشفكم</h3>' + table(['التاريخ', 'المرجع', 'البيان', 'المبلغ'], pay.map(function (x) { return '<tr><td>' + E(D(x.e.date)) + '</td><td dir="ltr">' + E(x.e.ref) + '</td><td>' + E(x.e.desc) + '</td>' + money(Math.abs(x.e.m)) + '</tr>'; })) + '<p>نرجو تأكيد استلامها وإقفالها على الفواتير المستحقة.</p>');
        if (notes.length) h.push('<h3>٢. إشعارات دائنة/مرتجعات/خصومات لدينا لم تظهر في كشفكم</h3>' + table(['التاريخ', 'المرجع', 'البيان', 'المبلغ'], notes.map(function (x) { return '<tr><td>' + E(D(x.e.date)) + '</td><td dir="ltr">' + E(x.e.ref) + '</td><td>' + E(x.e.desc) + '</td>' + money(Math.abs(x.e.m)) + '</tr>'; })) + '<p>نرجو قيدها في حسابنا لديكم، ونرفق المستندات عند الطلب.</p>');
        if (missing.length) h.push('<h3>٣. بنود في كشفكم لا نجدها في سجلاتنا</h3>' + table(['التاريخ', 'المرجع', 'البيان', 'المبلغ'], missing.map(function (x) { return '<tr><td>' + E(D(x.e.date)) + '</td><td dir="ltr">' + E(x.e.ref) + '</td><td>' + E(x.e.desc) + '</td>' + money(x.e.m) + '</tr>'; })) + '<p>نرجو تزويدنا بصور الفواتير وأوامر الشراء ومحاضر الاستلام المتعلقة بها.</p>');
        if (ours.length) h.push('<h3>٤. فواتير مسجَّلة لدينا وغير ظاهرة في كشفكم</h3>' + table(['التاريخ', 'المرجع', 'البيان', 'المبلغ'], ours.map(function (x) { return '<tr><td>' + E(D(x.e.date)) + '</td><td dir="ltr">' + E(x.e.ref) + '</td><td>' + E(x.e.desc) + '</td>' + money(x.e.m) + '</tr>'; })) + '<p>نرجو التحقق من قيدها لديكم.</p>');
        if (res.diffs.length) h.push('<h3>٥. فروق في مبالغ مستندات مشتركة</h3>' + table(['المرجع', 'مبلغنا', 'مبلغكم', 'الفرق', 'السبب المحتمل'], res.diffs.map(function (d) { return '<tr><td dir="ltr">' + E(d.a.ref || d.b.ref) + '</td>' + money(d.a.m) + money(d.b.m) + money(d.diff) + '<td>' + E(d.reasonText) + '</td></tr>'; })));
        var arith = [];
        if (!res.supplier.balanceCheck.ok) arith.push('رصيد كشفكم الجاري لا يتسق مع الحركة في ' + res.supplier.balanceCheck.mismatches + ' سطر');
        res.supplier.warnings.filter(function (w) { return w.code === 'closing-mismatch'; }).forEach(function (w) { arith.push(w.text); });
        if (arith.length) h.push('<h3>٦. ملاحظات حسابية على كشفكم</h3><ul>' + arith.map(function (a) { return '<li>' + E(a) + '</li>'; }).join('') + '</ul>');
        if (b.openingDiff) h.push('<p>كما نلفت إلى اختلاف الرصيد الافتتاحي بيننا بمقدار ' + F(b.openingDiff) + '، ونرجو مطابقة الفترة السابقة.</p>');
        h.push('<p>نأمل إفادتنا خلال أسبوع من تاريخه، وتقبلوا خالص التحية والتقدير.</p>');
        h.push('<div class="sign"><div>المحاسب المسؤول<br><span class="line"></span></div><div>المدير المالي<br><span class="line"></span></div><div>الختم<br><span class="line"></span></div></div></article>');
        return h.join('');
    };

    // ── تصدير Excel (عشر أوراق) ─────────────────────────────────────────────────
    SM.buildWorkbook = function (res, ctx) {
        ctx = ctx || {};
        var b = res.bridge, sp = SM.summaryParts(res, ctx), num = function (c) { return c / 100; };
        var sheets = [];
        sheets.push({ name: 'الملخص', header: false, widths: [34, 24, 60], bold: [0, 2], rows: [
            ['مطابقة كشف حساب مورد — ' + (ctx.company || '')], [], ['المورد', party(ctx, res)], ['الفترة', period(res)], ['الحالة', sp.status.label],
            ['رصيد دفاترنا', num(b.oursClosing)], ['رصيد كشف المورد', num(b.supplierClosing)], ['الفرق الإجمالي', num(b.gross)],
            ['حركات متطابقة', res.kpis.matched], ['فروق مبالغ', res.kpis.diffs], ['عند المورد فقط', res.kpis.supplierOnly], ['عندنا فقط', res.kpis.oursOnly], [],
            ['تفصيل الفرق', sp.breakdown || '—'], [], ['أهم الإجراءات']].concat(sp.top.map(function (a, i) { return [(i + 1) + '. ' + CAT[a.cat], num(a.amount), a.action]; })) });
        sheets.push({ name: 'الجسر', widths: [44, 18, 40], rows: [['البند', 'المبلغ', 'ملاحظة']].concat(SM.bridgeLines(res).map(function (l) { return [l.label, num(l.amount), l.note || '']; })), total: [SM.bridgeLines(res).length] });
        sheets.push({ name: 'تحتاج إجراء', widths: [10, 34, 16, 14, 16, 60], rows: [['الأولوية', 'البند', 'المرجع', 'التاريخ', 'المبلغ', 'الإجراء المقترح']].concat(res.actions.map(function (a) { return [SEV[a.sev], CAT[a.cat], a.ref || '', D(a.date), num(a.amount), a.action]; })) });
        sheets.push({ name: 'فروق المبالغ', widths: [16, 14, 40, 16, 16, 16, 40], rows: [['المرجع', 'التاريخ', 'البيان', 'مبلغنا', 'مبلغ المورد', 'الفرق', 'السبب']].concat(res.diffs.map(function (d) { return [d.a.ref || d.b.ref, D(d.a.date || d.b.date), d.a.desc || d.b.desc, num(d.a.m), num(d.b.m), num(d.diff), d.reasonText]; })) });
        function only(list, label) {
            return { name: label, widths: [14, 16, 44, 16, 34, 60], rows: [['التاريخ', 'المرجع', 'البيان', 'المبلغ', 'التصنيف', 'التشخيص والإجراء']].concat(list.map(function (x) { return [D(x.e.date), x.e.ref, x.e.desc, num(x.e.m), CAT[x.cat], x.text + ' — ' + x.action]; })) };
        }
        sheets.push(only(res.supplierOnly, 'عند المورد فقط'));
        sheets.push(only(res.oursOnly, 'عندنا فقط'));
        var grp = [['الجهة', 'مفرد', 'المرجع', 'المبلغ المفرد', 'الأجزاء', 'مجموع الأجزاء']];
        res.groups.forEach(function (gr) { grp.push([gr.side === 'ours' ? 'دفاترنا' : 'المورد', gr.single.id, gr.single.ref, num(gr.single.m), gr.many.map(function (x) { return x.ref || x.id; }).join('، '), num(sum(gr.many, function (x) { return x.m; }))]); });
        sheets.push({ name: 'مجمّعة', widths: [12, 10, 18, 16, 50, 16], rows: grp });
        var mt = [['دفاترنا: التاريخ', 'دفاترنا: المرجع', 'المورد: التاريخ', 'المورد: المرجع', 'المبلغ', 'الطريقة', 'الثقة']];
        res.matches.forEach(function (m) { mt.push([D(m.a.date), m.a.ref, D(m.b.date), m.b.ref, num(m.a.m), m.pass === 'ref' ? 'مرجع + مبلغ' : (m.pass === 'timing' ? 'مبلغ (تأخير توقيت)' : 'مبلغ + تاريخ'), m.confidence]); });
        sheets.push({ name: 'متطابقة', widths: [14, 16, 14, 16, 16, 22, 16], rows: mt });
        var rv = [['الجهة', 'القيد', 'مرجع', 'مبلغ', 'عكسه', 'مرجع', 'مبلغ']];
        ['ours', 'supplier'].forEach(function (s) { res.reversals[s].forEach(function (r) { rv.push([s === 'ours' ? 'دفاترنا' : 'المورد', r.a.id, r.a.ref, num(r.a.m), r.b.id, r.b.ref, num(r.b.m)]); }); });
        sheets.push({ name: 'انعكاسات', widths: [12, 10, 16, 16, 10, 16, 16], rows: rv });
        var integ = [['الجهة', 'البند', 'القيمة']];
        [['دفاترنا', res.ours], ['كشف المورد', res.supplier]].forEach(function (p) {
            var s = p[1];
            integ.push([p[0], 'الرصيد الافتتاحي', num(s.opening)], [p[0], 'مصدر الافتتاحي', s.openingSource], [p[0], 'الختامي المحسوب', num(s.closingComputed)],
                [p[0], 'الختامي المطبوع', s.closingPrinted === null || s.closingPrinted === undefined ? '' : num(s.closingPrinted)], [p[0], 'أسطر غير متسقة الرصيد', s.balanceCheck.mismatches]);
            s.warnings.forEach(function (w) { integ.push([p[0], 'تحذير', w.text]); });
            s.txns.filter(function (t) { return t.flags && t.flags.indexOf('balance') >= 0; }).forEach(function (t) { integ.push([p[0], 'سطر غير متسق: ' + (t.ref || t.id || ''), 'المطبوع ' + F(t.bal) + ' / الصحيح ' + F(t.balExpected)]); });
        });
        sheets.push({ name: 'سلامة الكشف', widths: [16, 40, 60], rows: integ });
        return sheets;
    };

    if (typeof module !== 'undefined' && module.exports) module.exports = SM;
})(typeof window !== 'undefined' ? window : globalThis);
