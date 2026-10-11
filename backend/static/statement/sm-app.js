/* مطابق كشوفات الحساب — الواجهة: الملفات ← المراجعة ← النتائج. كل شيء يعمل في المتصفح ولا يُرسَل أي ملف لأي خادم. */
(function () {
    'use strict';
    var SM = window.SM, esc = SM.escapeHtml;
    var $C = function (c) { return SM.fmt(c / 100); };

    var DEFAULTS = { company: 'شركة محمد رشيد الرشيد للتجارة', tolerance: 0.01, rounding: 1, windowDays: 7, vat: 15, dayFirst: true };
    var KEY = 'sm.settings.v1';
    function loadSettings() {
        try { return Object.assign({}, DEFAULTS, JSON.parse(localStorage.getItem(KEY) || '{}')); } catch (e) { return Object.assign({}, DEFAULTS); }
    }
    function saveSettings(s) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) { /* التخزين غير متاح */ } }

    var SIDES = { ours: { title: 'دفاترنا', sub: 'حساب المورد في سجلات الشركة (دفتر الأستاذ / كشف الحساب الداخلي)', short: 'دفاترنا' },
        supplier: { title: 'كشف حساب المورد', sub: 'الكشف الذي أرسله المورد (Excel أو PDF أو صورة ممسوحة)', short: 'المورد' } };

    var S = { step: 1, settings: loadSettings(), sides: { ours: newSide(), supplier: newSide() }, result: null, tab: 'actions', modal: null, busy: false, progress: '', notice: null };
    var root, modalRoot;

    function newSide() { return { files: [], tables: [], side: null, opts: {} }; }
    var uid = 0;

    function tolCents() { return Math.max(1, Math.round(S.settings.tolerance * 100)); }
    function sideOpts(k) {
        return Object.assign({ sideDefault: k === 'supplier', tolerance: tolCents(), dayFirst: S.settings.dayFirst }, S.sides[k].opts);
    }
    function reparse(k) {
        var st = S.sides[k];
        st.side = st.tables.length ? SM.parseSide(st.tables, sideOpts(k)) : null;
    }
    function recompute(k) {
        var st = S.sides[k], o = sideOpts(k);
        st.side = SM.recomputeSide(st.side, { sideDefault: o.sideDefault, tolerance: o.tolerance, orientation: st.opts.orientation || st.side.orient, openingOverride: o.openingOverride });
    }

    // ── مساعدات ─────────────────────────────────────────────────────────────────
    function icons() { if (window.lucide) window.lucide.createIcons(); }
    function toast(msg, tone) { S.notice = { msg: msg, tone: tone || 'warn' }; renderNotice(); clearTimeout(toast.t); toast.t = setTimeout(function () { S.notice = null; renderNotice(); }, 6000); }
    function renderNotice() {
        var el = root.querySelector('#sm-notice');
        if (el) el.innerHTML = S.notice ? '<div class="sm-note ' + S.notice.tone + '" role="alert">' + esc(S.notice.msg) + '</div>' : '';
    }
    function download(bytes, name, mime) {
        var blob = new Blob([bytes], { type: mime }), a = document.createElement('a');
        a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click();
        setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
    }
    function ctx() { return { company: S.settings.company, supplierName: (S.sides.supplier.party || (S.sides.supplier.side && S.sides.supplier.side.party) || (S.sides.ours.side && S.sides.ours.side.party) || '') }; }
    function safeName(s) { return String(s || 'مورد').replace(/[\\/:*?"<>|]+/g, ' ').trim().slice(0, 60); }

    // ── الخطوة ١: الملفات ───────────────────────────────────────────────────────
    function filesPanel(k) {
        var st = S.sides[k], meta = SIDES[k];
        return '<section class="sm-panel" aria-labelledby="sm-t-' + k + '"><h3 id="sm-t-' + k + '">' + meta.title + '</h3><p class="sub">' + meta.sub + '</p>' +
            '<label class="sm-drop" data-drop="' + k + '" tabindex="0"><i data-lucide="upload-cloud"></i><b>اسحب الملفات هنا أو اضغط للاختيار</b>' +
            '<small>Excel · CSV · PDF · صور ممسوحة (JPG, PNG, WebP, TIFF)</small><input type="file" multiple hidden accept="' + SM.ACCEPT + '" data-pick="' + k + '"></label>' +
            (st.files.length ? '<ul class="sm-files">' + st.files.map(function (f) {
                var chip = f.status === 'ready' ? '<span class="sm-chip ok">جاهز</span>' : f.status === 'reading' ? '<span class="sm-chip busy">قراءة...</span>' : f.status === 'error' ? '<span class="sm-chip bad">تعذّرت القراءة</span>' : '<span class="sm-chip">بانتظار القراءة</span>';
                return '<li class="sm-file"><i data-lucide="file-text"></i><span class="name" title="' + esc(f.file.name) + '">' + esc(f.file.name) + '</span>' + chip +
                    '<button class="sm-btn quiet sm" data-act="remove" data-side="' + k + '" data-id="' + f.id + '" aria-label="حذف ' + esc(f.file.name) + '"><i data-lucide="x"></i></button></li>' +
                    (f.msg ? '<li class="sm-note ' + (f.status === 'error' ? 'bad' : '') + '">' + esc(f.msg) + '</li>' : '');
            }).join('') + '</ul>' : '') + '</section>';
    }

    function viewFiles() {
        var ready = S.sides.ours.files.length && S.sides.supplier.files.length;
        return '<div class="sm-grid2">' + filesPanel('ours') + filesPanel('supplier') + '</div>' +
            '<div class="sm-actions" style="margin-top:1rem"><button class="sm-btn primary" data-act="read"' + (ready && !S.busy ? '' : ' disabled') + '><i data-lucide="scan-search"></i> قراءة الملفات</button>' +
            '<button class="sm-btn" data-act="sample"' + (S.busy ? ' disabled' : '') + '><i data-lucide="flask-conical"></i> تجربة ببيانات نموذجية</button>' +
            '<span class="sm-progress" id="sm-progress" role="status">' + esc(S.progress) + '</span></div>' +
            '<p class="sm-note">الملفات تُقرأ داخل متصفحك فقط ولا تغادر جهازك. الملفات الممسوحة (PDF/صور) تُقرأ بالتعرّف الضوئي وتحتاج اتصالًا بالإنترنت لتحميل محرك القراءة أول مرة.</p>';
    }

    function addFiles(k, fileList) {
        var bad = [];
        Array.prototype.forEach.call(fileList, function (file) {
            if (!SM.fileKind(file.name) && !/^image\//.test(file.type || '')) { bad.push(file.name); return; }
            S.sides[k].files.push({ id: ++uid, file: file, status: 'pending', msg: '' });
        });
        if (bad.length) toast('ملفات بنوع غير مدعوم: ' + bad.join('، '), 'bad');
        render();
    }

    function readAll() {
        S.busy = true; S.progress = 'جارٍ القراءة...';
        ['ours', 'supplier'].forEach(function (k) { S.sides[k].tables = []; S.sides[k].files.forEach(function (f) { f.status = 'pending'; f.msg = ''; }); });
        render();
        var chain = Promise.resolve();
        ['ours', 'supplier'].forEach(function (k) {
            S.sides[k].files.forEach(function (f) {
                chain = chain.then(function () {
                    f.status = 'reading'; render();
                    return SM.readFile(f.file, { onProgress: function (t) { S.progress = SIDES[k].short + ' — ' + f.file.name + ': ' + t; var p = root.querySelector('#sm-progress'); if (p) p.textContent = S.progress; } })
                        .then(function (res) {
                            f.status = 'ready'; f.msg = res.note || '';
                            S.sides[k].tables.push(res.tables[0]);
                        }, function (err) { f.status = 'error'; f.msg = err.message || String(err); });
                });
            });
        });
        return chain.then(function () {
            S.busy = false; S.progress = '';
            ['ours', 'supplier'].forEach(reparse);
            var ok = S.sides.ours.side && S.sides.supplier.side;
            if (ok) { S.step = 2; S.result = null; } else toast('تعذّرت قراءة أحد الجانبين. راجع رسائل الأخطاء بجانب الملفات.', 'bad');
            render();
        });
    }

    // ── الخطوة ٢: المراجعة ──────────────────────────────────────────────────────
    var FIELDS = [['date', 'التاريخ'], ['ref', 'المرجع'], ['desc', 'البيان'], ['debit', 'مدين'], ['credit', 'دائن'], ['amount', 'المبلغ'], ['balance', 'الرصيد']];
    var KINDS = [['txn', 'حركة'], ['opening', 'رصيد افتتاحي'], ['total', 'إجمالي'], ['carry', 'مرحَّل'], ['blank', 'تجاهل']];

    function colOptions(side, selected) {
        var rows = side.rawRows || [], n = 0, header = rows[side.startRow - 1] || [];
        rows.forEach(function (r) { n = Math.max(n, r.length); });
        var opts = '<option value="">— بلا —</option>';
        for (var c = 0; c < n; c++) {
            var label = header[c] !== undefined && header[c] !== '' && typeof header[c] === 'string' ? header[c] : 'عمود ' + (c + 1);
            opts += '<option value="' + c + '"' + (selected === c ? ' selected' : '') + '>' + esc(String(label).slice(0, 28)) + '</option>';
        }
        return opts;
    }

    function factsHtml(side) {
        var close = side.closingPrinted === null || side.closingPrinted === undefined ? '—' : $C(side.closingPrinted);
        return '<div class="sm-facts">' +
            '<div class="sm-fact"><small>عدد الحركات</small><b>' + side.count + '</b></div>' +
            '<div class="sm-fact"><small>الفترة</small><b>' + (side.period.from ? SM.isoToDisplay(side.period.from) + ' – ' + SM.isoToDisplay(side.period.to) : '—') + '</b></div>' +
            '<div class="sm-fact"><small>الرصيد الافتتاحي</small><b>' + $C(side.opening) + '</b><em>' + esc(side.openingSource) + '</em></div>' +
            '<div class="sm-fact"><small>إجمالي مدين / دائن</small><b>' + $C(side.totals.debit) + ' / ' + $C(side.totals.credit) + '</b></div>' +
            '<div class="sm-fact"><small>الختامي المحسوب</small><b>' + $C(side.closingComputed) + '</b><em>مطبوع: ' + close + '</em></div>' +
            '<div class="sm-fact"><small>فحص الرصيد الجاري</small><b>' + (side.balanceCheck.ok ? '✓ متسق' : side.balanceCheck.mismatches + ' سطر غير متسق') + '</b></div></div>';
    }

    function warningsHtml(side) {
        var out = '';
        if (side.diagnosis) out += '<div class="sm-note bad">' + esc(side.diagnosis) + '</div>';
        side.warnings.forEach(function (w) {
            if (w.code === 'empty') return;
            out += '<div class="sm-note warn">' + esc(w.text) + (w.suggest !== undefined ? ' <button class="sm-btn sm" data-act="apply-opening" data-val="' + w.suggest + '">اعتماد القيمة المتسقة</button>' : '') + '</div>';
        });
        return out;
    }

    function editTable(k, side) {
        var single = side.map && side.map.amount !== undefined && side.map.debit === undefined && side.map.credit === undefined, cap = 1500;
        var head = '<tr><th>#</th><th>النوع</th><th>التاريخ</th><th>المرجع</th><th>البيان</th>' + (single ? '<th>المبلغ</th>' : '<th>مدين</th><th>دائن</th>') + '<th>الرصيد المطبوع</th><th>المحسوب</th><th></th></tr>';
        var rows = side.entries.slice(0, cap).map(function (e, i) {
            var cls = 'k-' + e.kind + (e.flags && e.flags.indexOf('balance') >= 0 ? ' f-balance' : '') + (e.conf !== undefined && e.conf < 60 ? ' f-low' : '');
            function inp(f, v, extra) { return '<input data-side="' + k + '" data-i="' + i + '" data-f="' + f + '" value="' + esc(v) + '" ' + (extra || '') + '>'; }
            var kindSel = '<select data-side="' + k + '" data-i="' + i + '" data-f="kind" aria-label="نوع السطر">' + KINDS.map(function (p) { return '<option value="' + p[0] + '"' + (e.kind === p[0] ? ' selected' : '') + '>' + p[1] + '</option>'; }).join('') + '</select>';
            var money = single ? '<td>' + inp('amount', e.amount ? SM.fmt(e.amount / 100) : '', 'class="num"') + '</td>' :
                '<td>' + inp('debit', e.debit ? SM.fmt(e.debit / 100) : '', 'class="num"') + '</td><td>' + inp('credit', e.credit ? SM.fmt(e.credit / 100) : '', 'class="num"') + '</td>';
            var calc = e.kind === 'txn' && e.balCalc !== undefined ? '<span class="calc num' + (e.flags && e.flags.indexOf('balance') >= 0 ? ' bad' : '') + '" dir="ltr">' + $C(e.balCalc * side.balSign) + '</span>' : '';
            return '<tr class="' + cls + '" title="' + esc(e.why || '') + '"><td class="calc">' + (e.row + 1) + '</td><td>' + kindSel + '</td><td>' + inp('date', e.date ? SM.isoToDisplay(e.date) : '') + '</td><td>' + inp('ref', e.ref) + '</td><td>' +
                inp('desc', e.desc, 'class="desc"') + '</td>' + money + '<td>' + inp('bal', e.bal === null ? '' : SM.fmt(e.bal / 100), 'class="num"') + '</td><td>' + calc + '</td>' +
                '<td><button class="sm-btn quiet sm danger" data-act="del-row" data-side="' + k + '" data-i="' + i + '" aria-label="حذف السطر"><i data-lucide="trash-2"></i></button></td></tr>';
        }).join('');
        return '<div class="sm-scroll tall"><table class="sm-table sm-edit"><thead>' + head + '</thead><tbody>' + rows + '</tbody></table></div>' +
            (side.entries.length > cap ? '<p class="sm-note warn">عُرض أول ' + cap + ' سطر للتحرير؛ باقي الأسطر محسوبة في المطابقة.</p>' : '');
    }

    function reviewPanel(k) {
        var st = S.sides[k], side = st.side, meta = SIDES[k];
        var orient = st.opts.orientation ? (st.opts.orientation.debitIncreases ? 'debit' : 'credit') : 'auto';
        var autoNote = side.orient.auto ? 'مكتشف من كلمات البيان (فاتورة / سداد...)' : 'افتراضي لهذا الجانب';
        return '<section class="sm-panel" data-review="' + k + '"><h3>' + meta.title + '</h3><p class="sub">' + esc(side.fileName) + (side.parts > 1 ? ' — ' + side.parts + ' ملفات مدمجة' : '') + '</p>' +
            '<div class="sm-row"><div><label for="sm-party-' + k + '">اسم الطرف (كما يظهر في الكشف)</label><input id="sm-party-' + k + '" class="sm-field" data-party="' + k + '" value="' + esc(st.party !== undefined ? st.party : (side.party || '')) + '"></div>' +
            '<div><label for="sm-orient-' + k + '">اتجاه الحركة (المستحق للمورد)</label><select id="sm-orient-' + k + '" class="sm-field" data-orient="' + k + '"><option value="auto"' + (orient === 'auto' ? ' selected' : '') + '>تلقائي — ' + (side.orient.debitIncreases ? 'المدين يزيد' : 'الدائن يزيد') + '</option><option value="debit"' + (orient === 'debit' ? ' selected' : '') + '>المدين يزيد المستحق للمورد</option><option value="credit"' + (orient === 'credit' ? ' selected' : '') + '>الدائن يزيد المستحق للمورد</option></select><small style="color:#8a98ab;font-size:.72rem">' + autoNote + '</small></div>' +
            '<div><label for="sm-open-' + k + '">الرصيد الافتتاحي (تعديل يدوي)</label><input id="sm-open-' + k + '" class="sm-field" dir="ltr" data-opening="' + k + '" placeholder="' + $C(side.opening) + '" value="' + (st.opts.openingOverride !== undefined ? SM.fmt(st.opts.openingOverride / 100) : '') + '"></div></div>' +
            '<details style="margin:.6rem 0"><summary style="cursor:pointer;font-weight:700;font-size:.86rem;color:var(--steel-dark)">ربط الأعمدة (' + (side.mapHow === 'header' ? 'من الترويسة' : side.mapHow === 'inferred' ? 'مستنتجة من المحتوى' : 'يدوي') + ')</summary>' +
            '<div class="sm-maps">' + FIELDS.map(function (f) { return '<div><label>' + f[1] + '</label><select data-map="' + k + '" data-field="' + f[0] + '">' + colOptions(side, side.map[f[0]]) + '</select></div>'; }).join('') + '</div>' +
            '<button class="sm-btn sm" data-act="infer" data-side="' + k + '"><i data-lucide="wand"></i> استنتاج الأعمدة من المحتوى</button></details>' +
            '<div data-live="' + k + '">' + factsHtml(side) + warningsHtml(side) + '</div>' + editTable(k, side) +
            '<div class="sm-actions" style="margin-top:.6rem"><button class="sm-btn sm" data-act="add-row" data-side="' + k + '"><i data-lucide="plus"></i> إضافة سطر</button></div></section>';
    }

    function viewReview() {
        return '<div class="sm-grid2">' + reviewPanel('ours') + reviewPanel('supplier') + '</div>' +
            '<div class="sm-actions" style="margin-top:1rem"><button class="sm-btn" data-act="go" data-step="1"><i data-lucide="arrow-right"></i> رجوع للملفات</button>' +
            '<button class="sm-btn primary" data-act="reconcile"><i data-lucide="git-compare"></i> مطابقة الكشفين</button></div>';
    }

    function refreshReview(k) {
        var st = S.sides[k], panel = root.querySelector('[data-review="' + k + '"]');
        if (!panel) return render();
        var sc = panel.querySelector('.sm-scroll'), top = sc ? sc.scrollTop : 0;
        var tmp = document.createElement('div'); tmp.innerHTML = reviewPanel(k);
        panel.replaceWith(tmp.firstChild);
        var nsc = root.querySelector('[data-review="' + k + '"] .sm-scroll'); if (nsc) nsc.scrollTop = top;
        icons();
    }

    // ── الخطوة ٣: النتائج ───────────────────────────────────────────────────────
    function tabsDef(res) {
        return [['actions', 'تحتاج إجراء', res.actions.length], ['diffs', 'فروق المبالغ', res.diffs.length + res.flips.length], ['sup', 'عند المورد فقط', res.supplierOnly.length],
            ['our', 'عندنا فقط', res.oursOnly.length], ['groups', 'مجمّعة', res.groups.length], ['matched', 'متطابقة', res.matches.length], ['rev', 'انعكاسات', res.reversals.ours.length + res.reversals.supplier.length], ['integrity', 'سلامة الكشف', '']];
    }
    function tr(cells, text, cls) { return '<tr' + (cls ? ' class="' + cls + '"' : '') + ' data-t="' + esc(String(text).toLowerCase()) + '">' + cells + '</tr>'; }
    function td(v) { return '<td>' + esc(v === undefined || v === null ? '' : v) + '</td>'; }
    function tdn(c) { return '<td class="num">' + (c === 0 ? '<span class="zero">0.00</span>' : $C(c)) + '</td>'; }
    function wrapTable(head, rows, empty) {
        return rows.length ? '<div class="sm-scroll tall"><table class="sm-table"><thead><tr>' + head.map(function (h) { return '<th>' + h + '</th>'; }).join('') + '</tr></thead><tbody>' + rows.join('') + '</tbody></table></div>' : '<p class="empty">' + empty + '</p>';
    }

    function tabContent(res) {
        var D = SM.isoToDisplay, cat = SM.categoryLabel;
        switch (S.tab) {
            case 'actions': return wrapTable(['الأولوية', 'الجهة', 'التصنيف', 'المرجع', 'التاريخ', 'المبلغ', 'التشخيص', 'الإجراء المقترح'], res.actions.map(function (a) {
                return tr(td(SM.severityLabel(a.sev)) + td(a.side === 'ours' ? 'دفاترنا' : a.side === 'supplier' ? 'المورد' : 'الطرفان') + td(cat(a.cat)) + '<td dir="ltr">' + esc(a.ref || '') + '</td>' + td(D(a.date)) + tdn(a.amount) + td(a.text) + td(a.action), [a.ref, a.text, a.action, cat(a.cat)].join(' '), 'sev' + a.sev);
            }), 'لا توجد إجراءات مطلوبة');
            case 'diffs': return wrapTable(['المرجع', 'التاريخ', 'مبلغنا', 'مبلغ المورد', 'الفرق', 'السبب المحتمل', 'الإجراء'], res.diffs.map(function (d) {
                return tr('<td dir="ltr">' + esc(d.a.ref || d.b.ref) + '</td>' + td(D(d.a.date || d.b.date)) + tdn(d.a.m) + tdn(d.b.m) + tdn(d.diff) + td(d.reasonText + (d.lowConfidence ? ' (ثقة منخفضة: بلا مرجع)' : '')) + td(d.action), [d.a.ref, d.b.ref, d.reasonText].join(' '));
            }).concat(res.flips.map(function (f) {
                return tr('<td dir="ltr">' + esc(f.a.ref || f.b.ref) + '</td>' + td(D(f.a.date)) + tdn(f.a.m) + tdn(f.b.m) + tdn(f.diff) + td('انعكاس اتجاه: القيد نفسه بعكس الإشارة') + td('راجع طبيعة المستند وصحّح عند الطرف الخاطئ'), [f.a.ref, f.b.ref, 'انعكاس'].join(' '), 'sev3');
            })), 'لا توجد فروق مبالغ');
            case 'sup':
            case 'our': {
                var list = S.tab === 'sup' ? res.supplierOnly : res.oursOnly;
                return wrapTable(['التاريخ', 'المرجع', 'البيان', 'المبلغ', 'التصنيف', 'التشخيص', 'الإجراء المقترح'], list.map(function (x) {
                    return tr(td(D(x.e.date)) + '<td dir="ltr">' + esc(x.e.ref) + '</td>' + td(x.e.desc) + tdn(x.e.m) + td(cat(x.cat)) + td(x.text) + td(x.action), [x.e.ref, x.e.desc, x.text].join(' '), 'sev' + x.sev);
                }), S.tab === 'sup' ? 'لا توجد حركات عند المورد فقط' : 'لا توجد حركات عندنا فقط');
            }
            case 'groups': return wrapTable(['الجهة', 'المفرد', 'المبلغ', 'الأجزاء المقابلة', 'مجموع الأجزاء', 'الطريقة'], res.groups.map(function (gr) {
                var many = gr.many.reduce(function (s, x) { return s + x.m; }, 0);
                return tr(td(gr.side === 'ours' ? 'دفاترنا' : 'المورد') + td((gr.single.ref || gr.single.id) + ' — ' + D(gr.single.date)) + tdn(gr.single.m) + td(gr.many.map(function (x) { return (x.ref || x.id) + ' (' + $C(x.m) + ')'; }).join('، ')) + tdn(many) + td(gr.pass === 'ref-group' ? 'بالمرجع نفسه' : 'بمجموع الجزئيات'), gr.single.ref);
            }), 'لا توجد مطابقات مجمّعة');
            case 'matched': return wrapTable(['التاريخ (دفاترنا)', 'المرجع (دفاترنا)', 'التاريخ (المورد)', 'المرجع (المورد)', 'المبلغ', 'الطريقة', 'الثقة'], res.matches.map(function (m) {
                return tr(td(D(m.a.date)) + '<td dir="ltr">' + esc(m.a.ref) + '</td>' + td(D(m.b.date)) + '<td dir="ltr">' + esc(m.b.ref) + '</td>' + tdn(m.a.m) + td(m.pass === 'ref' ? 'مرجع + مبلغ' : m.pass === 'timing' ? 'مبلغ (تأخير توقيت)' : 'مبلغ + تاريخ') + td(m.confidence), [m.a.ref, m.b.ref].join(' '));
            }), 'لا توجد مطابقات');
            case 'rev': {
                var rows = [];
                ['ours', 'supplier'].forEach(function (s) { res.reversals[s].forEach(function (r) { rows.push(tr(td(s === 'ours' ? 'دفاترنا' : 'المورد') + td(r.a.ref) + tdn(r.a.m) + td(D(r.a.date)) + td(r.b.ref) + tdn(r.b.m) + td(D(r.b.date)), [r.a.ref, r.b.ref].join(' '))); }); });
                return wrapTable(['الجهة', 'القيد', 'المبلغ', 'التاريخ', 'قيد العكس', 'المبلغ', 'التاريخ'], rows, 'لا توجد انعكاسات داخلية');
            }
            case 'integrity': return integrityHtml(res);
        }
        return '';
    }

    function integrityHtml(res) {
        function one(title, s) {
            var bad = s.txns.filter(function (t) { return t.flags && t.flags.indexOf('balance') >= 0; });
            return '<div class="sm-panel" style="margin-bottom:.8rem"><h3>' + title + '</h3><div class="sm-facts"><div class="sm-fact"><small>الافتتاحي</small><b>' + $C(s.opening) + '</b><em>' + esc(s.openingSource) + '</em></div>' +
                '<div class="sm-fact"><small>الختامي المحسوب</small><b>' + $C(s.closingComputed) + '</b></div><div class="sm-fact"><small>الختامي المطبوع</small><b>' + (s.closingPrinted === null || s.closingPrinted === undefined ? '—' : $C(s.closingPrinted)) + '</b></div>' +
                '<div class="sm-fact"><small>أسطر غير متسقة</small><b>' + s.balanceCheck.mismatches + '</b></div></div>' +
                s.warnings.map(function (w) { return '<div class="sm-note warn">' + esc(w.text) + '</div>'; }).join('') +
                (bad.length ? wrapTable(['المرجع', 'التاريخ', 'الرصيد المطبوع', 'الرصيد الصحيح'], bad.map(function (t) { return tr(td(t.ref) + td(SM.isoToDisplay(t.date)) + tdn(t.bal) + tdn(t.balExpected), t.ref); }), '') : '<p class="sm-note ok">الرصيد الجاري متسق في كل الأسطر.</p>') + '</div>';
        }
        return one('دفاترنا', res.ours) + one('كشف المورد', res.supplier);
    }

    function sealIcon(tone) { return tone === 'ok' ? 'badge-check' : tone === 'warn' ? 'alert-triangle' : 'x-octagon'; }

    function viewResults() {
        var res = S.result, st = SM.statusInfo(res.status), sp = SM.summaryParts(res, ctx()), b = res.bridge, c = ctx();
        var kp = res.kpis;
        var bridgeBad = Math.abs(b.unexplained) > res.options.tolCents;
        var html = '<section class="sm-panel"><div class="sm-verdict"><div class="sm-seal ' + st.tone + '"><div><i data-lucide="' + sealIcon(st.tone) + '"></i><br>' + esc(st.label) + '</div></div><div>' +
            '<h3 style="font-size:1.2rem">' + esc(c.supplierName || 'المورد') + '</h3><p class="sub" style="margin:0">' + esc(c.company) + '</p>' +
            '<div class="sm-parties"><div><small>رصيد دفاترنا</small><b>' + $C(b.oursClosing) + '</b></div><div><small>رصيد كشف المورد</small><b>' + $C(b.supplierClosing) + '</b></div><div class="diff"><small>الفرق الإجمالي</small><b>' + $C(b.gross) + '</b></div><div><small>حركات متطابقة</small><b>' + kp.matched + '</b></div></div>' +
            '<p style="margin:.2rem 0">' + esc(sp.breakdown ? 'يتكوّن الفرق من: ' + sp.breakdown + '.' : st.line) + '</p>' +
            (sp.top.length ? '<ol class="sm-top5">' + sp.top.map(function (a) { return '<li><b>' + esc(SM.categoryLabel(a.cat)) + '</b>' + (a.ref ? ' [' + esc(a.ref) + ']' : '') + ' — ' + $C(a.amount) + ' — ' + esc(a.action) + '</li>'; }).join('') + '</ol>' : '') +
            '<div class="sm-actions" style="margin-top:.8rem"><button class="sm-btn" data-act="copy"><i data-lucide="copy"></i> نسخ الملخص</button><button class="sm-btn" data-act="report"><i data-lucide="file-text"></i> تقرير المطابقة</button>' +
            '<button class="sm-btn" data-act="letter"><i data-lucide="mail"></i> خطاب المورد</button><button class="sm-btn primary" data-act="excel"><i data-lucide="file-spreadsheet"></i> تصدير Excel</button><button class="sm-btn" data-act="print"><i data-lucide="printer"></i> طباعة / PDF</button></div></div></div></section>';
        html += '<section class="sm-panel" style="margin-top:1rem"><h3>جسر المطابقة</h3><p class="sub">من رصيد دفاترنا إلى رصيد كشف المورد، بند بند</p>' + SM.bridgeHtml(res).replace('class="result"', 'class="result' + (bridgeBad ? ' bad' : '') + '"') + '</section>';
        html += '<div class="sm-kpis" style="margin-top:1rem">' +
            kpi('حركات دفاترنا', kp.ours, '') + kpi('حركات المورد', kp.supplier, '') + kpi('متطابقة', kp.matched, 'ok') + kpi('فروق مبالغ', kp.diffs, kp.diffs ? 'warn' : 'ok') +
            kpi('عند المورد فقط', kp.supplierOnly, kp.supplierOnly ? 'warn' : 'ok') + kpi('عندنا فقط', kp.oursOnly, kp.oursOnly ? 'warn' : 'ok') + kpi('تأخير توقيت', kp.timing, '') + '</div>';
        html += '<section class="sm-panel" style="margin-top:1rem"><div class="sm-tabs" role="tablist">' + tabsDef(res).map(function (t) {
            return '<button class="sm-tab' + (S.tab === t[0] ? ' is-active' : '') + '" role="tab" aria-selected="' + (S.tab === t[0]) + '" data-act="tab" data-tab="' + t[0] + '">' + t[1] + (t[2] !== '' ? ' <span class="cnt">' + t[2] + '</span>' : '') + '</button>';
        }).join('') + '<input class="sm-field sm-search" style="max-width:14rem" type="search" placeholder="بحث في الجدول" aria-label="بحث" data-search></div><div id="sm-tabbody">' + tabContent(res) + '</div></section>';
        html += '<div class="sm-actions" style="margin-top:1rem"><button class="sm-btn" data-act="go" data-step="2"><i data-lucide="arrow-right"></i> رجوع للمراجعة</button><button class="sm-btn quiet" data-act="restart">مطابقة جديدة</button></div>';
        return html;
    }
    function kpi(label, n, tone) { return '<div class="sm-kpi ' + tone + '"><small>' + label + '</small><b>' + n + '</b></div>'; }

    function runReconcile() {
        var o = { tolCents: tolCents(), roundingCents: Math.round(S.settings.rounding * 100), windowDays: S.settings.windowDays, vatPct: S.settings.vat };
        ['ours', 'supplier'].forEach(function (k) {
            var side = S.sides[k].side;
            if (!side.txns.length) throw new Error('لا توجد حركات في ' + SIDES[k].title + '. ' + (side.diagnosis || 'راجع ربط الأعمدة وتصنيف الأسطر.'));
        });
        S.result = SM.reconcile(S.sides.ours.side, S.sides.supplier.side, o);
        S.step = 3; S.tab = 'actions';
    }

    // ── نوافذ: التقرير والخطاب والإعدادات ──────────────────────────────────────
    function printDoc(html, title) {
        var w = window.open('', '_blank');
        if (!w) { toast('المتصفح منع النافذة المنبثقة. اسمح بها ثم أعد المحاولة.', 'bad'); return; }
        var base = window.__SM_STATIC__ || '/static/statement/';
        w.document.write('<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>' + esc(title) + '</title><meta name="viewport" content="width=device-width, initial-scale=1">' +
            '<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&family=Noto+Naskh+Arabic:wght@400;600;700&display=swap" rel="stylesheet">' +
            '<link href="' + base + 'statement.css" rel="stylesheet"></head><body class="print-body sm">' + html + '</body></html>');
        w.document.close();
        w.onload = function () { setTimeout(function () { w.focus(); w.print(); }, 400); };
    }

    function settingsHtml() {
        var s = S.settings;
        function num(id, label, val, step, hint) { return '<div><label for="' + id + '">' + label + '</label><input id="' + id + '" class="sm-field" dir="ltr" type="number" step="' + step + '" min="0" value="' + val + '">' + (hint ? '<small>' + hint + '</small>' : '') + '</div>'; }
        return '<div class="sm-settings"><div style="grid-column:1/-1"><label for="st-company">اسم الشركة (يظهر في الخطاب والتقرير)</label><input id="st-company" class="sm-field" value="' + esc(s.company) + '"></div>' +
            num('st-tol', 'حد التسامح في المبلغ (ريال)', s.tolerance, '0.01', 'فرق يساويه أو يقل عنه يُعد تطابقًا') + num('st-round', 'حد فروق التقريب (ريال)', s.rounding, '0.01', 'الفرق الأقل منه يُصنَّف تقريبًا') +
            num('st-win', 'نافذة التاريخ (أيام)', s.windowDays, '1', 'للمطابقة بالمبلغ والتاريخ') + num('st-vat', 'ضريبة القيمة المضافة %', s.vat, '0.5', 'لكشف فروق الضريبة') +
            '<div><label for="st-date">ترتيب التاريخ</label><select id="st-date" class="sm-field"><option value="day"' + (s.dayFirst ? ' selected' : '') + '>اليوم/الشهر/السنة</option><option value="month"' + (!s.dayFirst ? ' selected' : '') + '>الشهر/اليوم/السنة</option></select></div></div>' +
            '<div class="sm-actions" style="margin-top:1rem"><button class="sm-btn primary" data-act="save-settings">حفظ الإعدادات</button><button class="sm-btn" data-act="reset-settings">استعادة الافتراضي</button></div>';
    }

    function modalHtml() {
        if (!S.modal) return '';
        var m = S.modal, tools = m.type === 'settings' ? '' : '<button class="sm-btn primary sm" data-act="print-modal"><i data-lucide="printer"></i> طباعة / حفظ PDF</button><button class="sm-btn sm" data-act="copy-modal"><i data-lucide="copy"></i> نسخ النص</button>';
        return '<div class="sm-modal" data-modal-bg role="dialog" aria-modal="true" aria-label="' + esc(m.title) + '"><div class="sm-sheet"><div class="sm-sheet-bar"><h3>' + esc(m.title) + '</h3><div class="sm-actions">' + tools + '<button class="sm-btn sm" data-act="close-modal"><i data-lucide="x"></i> إغلاق</button></div></div><div class="sm-sheet-body">' +
            (m.type === 'settings' ? settingsHtml() : m.html) + '</div></div></div>';
    }

    // ── الجذر والتصيير ─────────────────────────────────────────────────────────
    function stepper() {
        var names = ['الملفات', 'المراجعة', 'النتائج'];
        return '<ol class="sm-steps">' + names.map(function (n, i) {
            var cls = S.step === i + 1 ? 'is-current' : (S.step > i + 1 ? 'is-done' : ''), go = (S.step > i + 1) ? ' data-act="go" data-step="' + (i + 1) + '"' : '';
            return '<li class="' + cls + '"' + (go ? ' data-go' + go : '') + '><span class="n">' + (S.step > i + 1 ? '✓' : i + 1) + '</span>' + n + '</li>';
        }).join('') + '</ol>';
    }

    function render() {
        var scroll = root.scrollTop;
        root.innerHTML = '<div class="sm-head"><div><h2>مطابق كشوفات الحساب</h2><p>طابق كشف حساب المورد مع سجلاتنا: يقرأ Excel وPDF والصور الممسوحة، ويفسّر كل فرق ويوصي بالإجراء المناسب.</p></div>' +
            '<div class="sm-actions"><span class="sm-privacy"><i data-lucide="shield-check"></i> المعالجة داخل متصفحك فقط</span><button class="sm-btn" data-act="settings"><i data-lucide="settings"></i> الإعدادات</button></div></div>' +
            '<div id="sm-notice"></div>' + stepper() + (S.step === 1 ? viewFiles() : S.step === 2 ? viewReview() : viewResults());
        modalRoot.innerHTML = modalHtml();                       // النافذة خارج الصفحة كي لا تتقيّد بحاوية التحريك
        document.body.style.overflow = S.modal ? 'hidden' : '';
        renderNotice(); icons(); root.scrollTop = scroll;
    }

    // ── الأحداث ─────────────────────────────────────────────────────────────────
    function parseMoneyInput(v) { var n = SM.parseNumber(String(v).replace(/\s/g, '')); return n === null ? null : SM.cents(n); }

    function onChangeField(t) {
        var k = t.dataset.side, i = +t.dataset.i, f = t.dataset.f, side = S.sides[k].side, e = side.entries[i], v = t.value.trim();
        if (f === 'kind') e.kind = v;
        else if (f === 'ref' || f === 'desc') e[f] = v;
        else if (f === 'date') {
            if (v === '') e.date = null;
            else { var d = SM.parseDate(v, S.settings.dayFirst); if (!d) { toast('تاريخ غير صالح: ' + v, 'bad'); t.value = e.date ? SM.isoToDisplay(e.date) : ''; return; } e.date = d; }
        } else {
            var c = v === '' ? 0 : parseMoneyInput(v);
            if (c === null) { toast('مبلغ غير صالح: ' + v, 'bad'); return; }
            if (f === 'bal') e.bal = v === '' ? null : c;
            else { e[f] = c; e['has' + f.charAt(0).toUpperCase() + f.slice(1)] = v !== ''; }
        }
        recompute(k); refreshReview(k);
    }

    function handleClick(ev) {
        var el = ev.target.closest('[data-act]');
        if (!el || el.disabled) return;
        var act = el.dataset.act, k = el.dataset.side;
        switch (act) {
            case 'remove': S.sides[k].files = S.sides[k].files.filter(function (f) { return f.id !== +el.dataset.id; }); render(); break;
            case 'read': readAll(); break;
            case 'sample': loadSample(); break;
            case 'go': S.step = +el.dataset.step; render(); break;
            case 'restart': S.sides = { ours: newSide(), supplier: newSide() }; S.result = null; S.step = 1; render(); break;
            case 'reconcile': try { runReconcile(); render(); window.scrollTo && root.scrollIntoView(); } catch (e) { toast(e.message, 'bad'); } break;
            case 'tab': S.tab = el.dataset.tab; var body = root.querySelector('#sm-tabbody'); S.search = ''; if (body) { body.innerHTML = tabContent(S.result); root.querySelectorAll('.sm-tab').forEach(function (b) { b.classList.toggle('is-active', b === el); }); root.querySelector('[data-search]').value = ''; icons(); } break;
            case 'apply-opening': var ov = +el.dataset.val; var panel = el.closest('[data-live]'); k = panel.dataset.live; S.sides[k].opts.openingOverride = ov; recompute(k); refreshReview(k); break;
            case 'infer': var st = S.sides[k]; st.opts.map = SM.inferColumns(st.side.rawRows, st.side.startRow); reparse(k); refreshReview(k); break;
            case 'del-row': S.sides[k].side.entries.splice(+el.dataset.i, 1); recompute(k); refreshReview(k); break;
            case 'add-row': S.sides[k].side.entries.push({ row: S.sides[k].side.entries.length, date: null, ref: '', desc: '', debit: 0, credit: 0, amount: 0, bal: null, hasDebit: false, hasCredit: false, hasAmount: false, kind: 'txn', why: 'سطر مضاف يدويًا', raw: '' }); recompute(k); refreshReview(k); break;
            case 'copy': copyText(SM.summaryText(S.result, ctx())); break;
            case 'report': S.modal = { type: 'report', title: 'تقرير المطابقة', html: SM.buildReportHtml(S.result, ctx()) }; render(); break;
            case 'letter': S.modal = { type: 'letter', title: 'خطاب المورد', html: SM.buildLetterHtml(S.result, ctx()) }; render(); break;
            case 'excel': exportExcel(); break;
            case 'print': printDoc(SM.buildReportHtml(S.result, ctx()), 'تقرير مطابقة — ' + (ctx().supplierName || '')); break;
            case 'print-modal': printDoc(S.modal.html, S.modal.title); break;
            case 'copy-modal': var tmp = document.createElement('div'); tmp.innerHTML = S.modal.html; copyText(tmp.innerText); break;
            case 'settings': S.modal = { type: 'settings', title: 'الإعدادات' }; render(); break;
            case 'close-modal': S.modal = null; render(); break;
            case 'save-settings': saveFromModal(); break;
            case 'reset-settings': S.settings = Object.assign({}, DEFAULTS); saveSettings(S.settings); S.modal = { type: 'settings', title: 'الإعدادات' }; render(); toast('استُعيدت الإعدادات الافتراضية', 'ok'); break;
        }
    }

    function saveFromModal() {
        var g = function (id) { return document.getElementById(id); };
        var n = function (id, def) { var v = parseFloat(g(id).value); return isFinite(v) && v >= 0 ? v : def; };
        S.settings = { company: g('st-company').value.trim() || DEFAULTS.company, tolerance: n('st-tol', DEFAULTS.tolerance), rounding: n('st-round', DEFAULTS.rounding),
            windowDays: Math.round(n('st-win', DEFAULTS.windowDays)), vat: n('st-vat', DEFAULTS.vat), dayFirst: g('st-date').value === 'day' };
        saveSettings(S.settings); S.modal = null;
        if (S.step === 2) ['ours', 'supplier'].forEach(reparse);
        if (S.step === 3) { try { runReconcile(); } catch (e) { toast(e.message, 'bad'); } }
        render(); toast('حُفظت الإعدادات', 'ok');
    }

    function copyText(text) {
        function fallback() { var ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); toast('نُسخ الملخص', 'ok'); } catch (e) { toast('تعذّر النسخ', 'bad'); } ta.remove(); }
        if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(function () { toast('نُسخ الملخص', 'ok'); }, fallback); else fallback();
    }

    function exportExcel() {
        try {
            var bytes = SM.buildXlsx(SM.buildWorkbook(S.result, ctx()));
            download(bytes, 'مطابقة-' + safeName(ctx().supplierName) + '-' + new Date().toISOString().slice(0, 10) + '.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
        } catch (e) { toast('تعذّر إنشاء ملف Excel: ' + e.message, 'bad'); }
    }

    function handleChange(ev) {
        var t = ev.target;
        if (t.dataset.pick) { addFiles(t.dataset.pick, t.files); t.value = ''; return; }
        if (t.dataset.f) { onChangeField(t); return; }
        if (t.dataset.party) { S.sides[t.dataset.party].party = t.value.trim(); return; }
        if (t.dataset.orient) {
            var k = t.dataset.orient;
            if (t.value === 'auto') delete S.sides[k].opts.orientation; else S.sides[k].opts.orientation = { debitIncreases: t.value === 'debit', auto: false, evidence: 0 };
            reparse(k); refreshReview(k); return;
        }
        if (t.dataset.opening) {
            var kk = t.dataset.opening, c = t.value.trim() === '' ? undefined : parseMoneyInput(t.value);
            if (c === null) { toast('مبلغ غير صالح', 'bad'); return; }
            if (c === undefined) delete S.sides[kk].opts.openingOverride; else S.sides[kk].opts.openingOverride = c;
            reparse(kk); refreshReview(kk); return;
        }
        if (t.dataset.map) {
            var side = S.sides[t.dataset.map], map = Object.assign({}, side.side.map);
            if (t.value === '') delete map[t.dataset.field]; else map[t.dataset.field] = +t.value;
            side.opts.map = map; reparse(t.dataset.map); refreshReview(t.dataset.map);
        }
    }

    function handleInput(ev) {
        var t = ev.target;
        if (t.hasAttribute && t.hasAttribute('data-search')) {
            var q = t.value.trim().toLowerCase();
            root.querySelectorAll('#sm-tabbody tr[data-t]').forEach(function (r) { r.hidden = q && r.dataset.t.indexOf(q) < 0; });
        }
    }

    function handleDrag(ev) {
        var drop = ev.target.closest('[data-drop]');
        if (!drop) return;
        if (ev.type === 'dragover' || ev.type === 'dragenter') { ev.preventDefault(); drop.classList.add('is-over'); }
        else if (ev.type === 'dragleave') drop.classList.remove('is-over');
        else if (ev.type === 'drop') { ev.preventDefault(); drop.classList.remove('is-over'); addFiles(drop.dataset.drop, ev.dataTransfer.files); }
    }

    // ── بيانات نموذجية للتجربة ─────────────────────────────────────────────────
    function loadSample() {
        var H = ['التاريخ', 'رقم المستند', 'البيان', 'مدين', 'دائن', 'الرصيد'];
        function ours(open, items) { var bal = open, rows = [['اسم المورد: شركة الأفق للتوريدات'], H, ['', '', 'رصيد افتتاحي', '', open, open]]; items.forEach(function (it) { bal += (it[3] || 0) - (it[4] || 0); rows.push([it[0], it[1], it[2], it[4] || '', it[3] || '', bal]); }); return { name: 'دفاترنا-نموذج.xlsx', rows: rows, preface: [] }; }
        function supp(open, items) { var bal = open, rows = [['كشف حساب العميل', 'شركة الأفق للتوريدات'], H, ['', '', 'رصيد افتتاحي', open, '', open]]; items.forEach(function (it) { bal += (it[3] || 0) - (it[4] || 0); rows.push([it[0], it[1], it[2], it[3] || '', it[4] || '', bal]); }); return { name: 'كشف-المورد-نموذج.xlsx', rows: rows, preface: [] }; }
        var common = [['2026-01-05', 'INV-1001', 'فاتورة مشتريات', 10000, 0], ['2026-01-12', 'PAY-77', 'سداد دفعة بنكية', 0, 4000], ['2026-01-20', 'INV-1002', 'فاتورة مشتريات', 2500.5, 0]];
        S.sides.ours.tables = [ours(5000, common.concat([['2026-01-06', 'A1', 'فاتورة مشتريات', 1000, 0], ['2026-01-26', 'CN-5', 'إشعار دائن مرتجع', 0, 700], ['2026-01-28', 'PAY-80', 'سداد دفعة بنكية', 0, 3000]]))];
        S.sides.supplier.tables = [supp(5000, common.concat([['2026-01-06', 'A1', 'فاتورة مشتريات', 1150, 0], ['2026-01-27', 'INV-1003', 'فاتورة مشتريات', 1500, 0]]))];
        S.sides.ours.files = [{ id: ++uid, file: { name: 'دفاترنا-نموذج.xlsx' }, status: 'ready', msg: '' }];
        S.sides.supplier.files = [{ id: ++uid, file: { name: 'كشف-المورد-نموذج.xlsx' }, status: 'ready', msg: '' }];
        ['ours', 'supplier'].forEach(function (k) { S.sides[k].opts = {}; reparse(k); });
        S.step = 2; S.result = null; render();
    }

    SM.app = {
        mount: function (el) {
            root = el; root.classList.add('sm');
            modalRoot = document.createElement('div'); modalRoot.className = 'sm'; document.body.appendChild(modalRoot);
            [root, modalRoot].forEach(function (r) { r.addEventListener('click', handleClick); r.addEventListener('change', handleChange); r.addEventListener('input', handleInput); });
            ['dragover', 'dragenter', 'dragleave', 'drop'].forEach(function (t) { root.addEventListener(t, handleDrag); });
            root.addEventListener('keydown', function (e) { if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches('[data-drop]')) { e.preventDefault(); e.target.querySelector('input').click(); } if (e.key === 'Escape' && S.modal) { S.modal = null; render(); } });
            render();
        },
        state: S, loadSample: loadSample, render: render
    };
})();
