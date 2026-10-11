/* مطابق كشوفات الحساب — محرك المطابقة (دالّة نقية قابلة للاختبار).
   يطابق حركات دفاترنا مع كشف المورد على عدة جولات، كل جولة تستهلك غير المطابَق فقط، ويشرح كل فرق ويوصي بإجراء.
   المبالغ بالهللات، والإشارة «المستحق للمورد» (الموجب = نحن مدينون له). */
(function (g) {
    'use strict';
    var SM = g.SM = g.SM || {};
    var DAY = 86400000;

    function dayNum(iso) { return iso ? Math.round(Date.parse(iso + 'T00:00:00Z') / DAY) : null; }
    function dist(a, b) { return (a.d !== null && b.d !== null) ? Math.abs(a.d - b.d) : 9999; }

    function entity(side, t, i) {
        var text = (t.ref || '') + ' ' + (t.desc || '');
        return { id: (side === 'ours' ? 'O' : 'S') + (i + 1), side: side, i: i, t: t, date: t.date, d: dayNum(t.date), ref: t.ref || '', desc: t.desc || '',
            m: t.m, refN: SM.normRef(t.ref || ''), digits: SM.refDigits(text), used: false, norm: SM.normAr(text) };
    }

    function sameAmount(a, b, tol) { return Math.abs(a.m - b.m) <= tol; }
    /** تعارض مراجع حقيقي: للطرفين أرقام مرجعية صريحة (3 خانات فأكثر) ولا يتقاطع منها شيء. المراجع القصيرة مختلفة الترقيم بين النظامين لا تُعدّ تعارضًا. */
    function refsConflict(a, b) {
        if (!a.refN || !b.refN || a.refN === b.refN) return false;
        if (!a.digits.length || !b.digits.length) return false;
        return !a.digits.some(function (x) { return b.digits.indexOf(x) >= 0; });
    }
    function refLevel(a, b) {
        if (a.refN && a.refN === b.refN) return 1;
        if (a.digits.some(function (x) { return x.length >= 4 && b.digits.indexOf(x) >= 0; })) return 2;
        if (a.refN && b.refN && a.refN.length >= 4 && b.refN.length >= 4 && (a.refN.endsWith(b.refN) || b.refN.endsWith(a.refN))) return 3;
        return 0;
    }

    var REASONS = {
        rounding: ['تقريب هللات', 'اعتمد قيمة المستند الأصلي وسوِّ الفرق كتقريب إن كان ضمن حد التسامح'],
        'vat-excl': ['فرق ضريبة القيمة المضافة: المورد سجّل الفاتورة شاملة الضريبة وسُجّلت عندنا بدونها', 'راجع الفاتورة الأصلية؛ إن كانت شاملة الضريبة فصحّح قيدنا بالفرق'],
        'vat-incl': ['فرق ضريبة القيمة المضافة: سُجّلت عندنا شاملة الضريبة وسجّلها المورد بدونها', 'راجع الفاتورة الأصلية واطلب من المورد تصحيح قيده إن لزم'],
        transposition: ['احتمال خطأ في تبديل أرقام (قُيّد المبلغ بأرقام متبادلة)', 'قارن المبلغ بنسخة الفاتورة وصحّح عند الطرف الخاطئ'],
        decimal: ['احتمال خطأ في موضع الفاصلة العشرية', 'قارن المبلغ بنسخة المستند وصحّح عند الطرف الخاطئ'],
        'discount-or-price': ['فرق صغير: خصم أو فرق سعر غير متفق عليه', 'اطلب نسخة الفاتورة وأمر الشراء وتأكد من الخصم/السعر المتفق عليه'],
        'quantity-or-price': ['فرق مضاعف: كمية أو سعر وحدة مختلف', 'طابق الفاتورة مع أمر الشراء ومحضر الاستلام'],
        generic: ['اختلاف مبلغ في المستند نفسه', 'اطلب من المورد صورة المستند وراجع القيد عند الطرفين']
    };

    function classifyDiff(a, b, o) {
        var ca = Math.abs(a.m), cb = Math.abs(b.m), diff = cb - ca, abs = Math.abs(diff), hi = Math.max(ca, cb) || 1;
        if (abs <= o.roundingCents) return 'rounding';
        var v = 1 + o.vatPct / 100, near = function (x, y) { return Math.abs(x - y) <= Math.max(o.tolCents, hi * 0.005); };
        if (near(cb, ca * v)) return 'vat-excl';
        if (near(ca, cb * v)) return 'vat-incl';
        var sa = String(ca).split('').sort().join(''), sb = String(cb).split('').sort().join('');
        if (sa === sb && abs % 9 === 0) return 'transposition';
        if (ca && cb) {
            var r = cb / ca;
            if ([10, 100, 0.1, 0.01].some(function (k) { return Math.abs(r - k) / k < 0.005; })) return 'decimal';
        }
        if (abs / hi <= 0.1) return 'discount-or-price';
        if (ca && cb) {
            var q = cb > ca ? cb / ca : ca / cb;
            if (q >= 1.95 && q <= 10.05 && Math.abs(q - Math.round(q)) < 0.01) return 'quantity-or-price';
        }
        return 'generic';
    }

    function pairsGreedy(listA, listB, ok, score) {
        // كل الأزواج المقبولة مرتّبة بالأفضلية ثم تُسند جشعيًا (A وB غير مستهلكين)
        var cand = [];
        listA.forEach(function (a) { listB.forEach(function (b) { if (ok(a, b)) cand.push({ a: a, b: b, s: score(a, b) }); }); });
        cand.sort(function (x, y) { return x.s - y.s; });
        var out = [];
        cand.forEach(function (c) {
            if (c.a.used || c.b.used) return;
            c.a.used = c.b.used = true;
            out.push(c);
        });
        return out;
    }

    function bucketByAmount(list) {
        var map = {};
        list.forEach(function (e) { (map[e.m] = map[e.m] || []).push(e); });
        return map;
    }

    /** يجد مجموعة جزئية (حجم 2..maxK) من pool مجموعها يساوي target ضمن tol. */
    function subsetSum(pool, target, tol, maxK) {
        var best = null, deadline = Date.now() + 40;
        (function dfs(start, picked, sum) {
            if (best || Date.now() > deadline) return;
            if (picked.length >= 2 && Math.abs(sum - target) <= tol) { best = picked.slice(); return; }
            if (picked.length >= maxK) return;
            for (var i = start; i < pool.length; i++) {
                var next = sum + pool[i].m;
                if (target > 0 ? (next > target + tol && pool[i].m > 0) : (next < target - tol && pool[i].m < 0)) continue;
                picked.push(pool[i]);
                dfs(i + 1, picked, next);
                picked.pop();
                if (best) return;
            }
        })(0, [], 0);
        return best;
    }

    var PAY_WORDS = /(سداد|دفعه|دفعات|payment|تحويل|حواله|شيك|cheque|check|pmt|transfer|نقد)/;
    var NOTE_WORDS = /(اشعار دائن|credit note|مرتجع|مردودات|return|خصم|discount|تسويه|حسم|اشعار تخفيض)/;
    var DEBIT_NOTE = /(اشعار مدين|debit note)/;
    var CANCEL_WORDS = /(الغاء|الغي|تصحيح|عكس|عكسي|reversal|reverse|cancel|void|correction)/;

    SM.reconcile = function (ours, supplier, options) {
        var o = Object.assign({ tolCents: 1, roundingCents: 100, windowDays: 7, timingDays: 60, vatPct: 15 }, options || {});
        var O = ours.txns.map(function (t, i) { return entity('ours', t, i); }), S = supplier.txns.map(function (t, i) { return entity('supplier', t, i); });
        var res = { matches: [], groups: [], diffs: [], flips: [], reversals: { ours: [], supplier: [] }, supplierOnly: [], oursOnly: [], options: o, ours: ours, supplier: supplier, O: O, S: S };
        var free = function (list) { return list.filter(function (e) { return !e.used; }); };

        // 1) المرجع + المبلغ (ثلاث درجات قوة للمرجع)
        [1, 2, 3].forEach(function (level) {
            var pairs = pairsGreedy(free(O), free(S), function (a, b) { return refLevel(a, b) === level && sameAmount(a, b, o.tolCents); }, function (a, b) { return dist(a, b); });
            pairs.forEach(function (p) { res.matches.push({ a: p.a, b: p.b, pass: 'ref', level: level, confidence: level === 1 ? 'عالية' : (level === 2 ? 'جيدة' : 'متوسطة') }); });
        });

        // 2) المبلغ + نافذة التاريخ (بلا تعارض مراجع)
        var byAmt = pairsGreedy(free(O), free(S), function (a, b) {
            return sameAmount(a, b, o.tolCents) && dist(a, b) <= o.windowDays && !refsConflict(a, b);
        }, function (a, b) { return dist(a, b) + (refLevel(a, b) ? -0.5 : 0); });
        byAmt.forEach(function (p) { res.matches.push({ a: p.a, b: p.b, pass: 'amount-date', level: 0, confidence: dist(p.a, p.b) === 0 ? 'جيدة' : 'متوسطة' }); });

        // 3) انعكاسات داخلية (قيد ثم عكسه في الجانب نفسه)
        [[O, 'ours'], [S, 'supplier']].forEach(function (pair) {
            var list = free(pair[0]), side = pair[1];
            list.forEach(function (a) {
                if (a.used) return;
                for (var k = 0; k < list.length; k++) {
                    var b = list[k];
                    if (b === a || b.used || a.m === 0 || Math.abs(a.m + b.m) > o.tolCents) continue;
                    var linked = (a.refN && a.refN === b.refN) || CANCEL_WORDS.test(a.norm) || CANCEL_WORDS.test(b.norm);
                    if (!linked) continue;
                    a.used = b.used = true;
                    res.reversals[side].push({ a: a, b: b });
                    return;
                }
            });
        });

        // 4) تجميع: بالمرجع ثم بمجموع الجزئيات (واحد ↔ عدة)
        function groupPass() {
            var found = false;
            [[O, S, 'ours'], [S, O, 'supplier']].forEach(function (cfg) {
                var singles = free(cfg[0]), others = free(cfg[1]);
                singles.forEach(function (a) {
                    if (a.used || !a.m) return;
                    var sameRef = others.filter(function (b) { return !b.used && refLevel(a, b) === 1; });
                    var chosen = null;
                    if (sameRef.length >= 2) {
                        var sum = sameRef.reduce(function (s, b) { return s + b.m; }, 0);
                        if (Math.abs(sum - a.m) <= o.tolCents * sameRef.length) chosen = sameRef;
                    }
                    if (!chosen) {
                        var pool = others.filter(function (b) { return !b.used && b.m && (a.m > 0) === (b.m > 0) && Math.abs(b.m) < Math.abs(a.m) && dist(a, b) <= 45 && !refsConflict(a, b); })
                            .sort(function (x, y) { return dist(a, x) - dist(a, y); }).slice(0, 24);
                        chosen = pool.length >= 2 ? subsetSum(pool, a.m, o.tolCents, 4) : null;
                    }
                    if (chosen) {
                        a.used = true; chosen.forEach(function (b) { b.used = true; });
                        res.groups.push({ side: cfg[2], single: a, many: chosen, pass: sameRef.length >= 2 && chosen === sameRef ? 'ref-group' : 'subset-sum' });
                        found = true;
                    }
                });
            });
            return found;
        }
        groupPass();

        // 5) نفس المرجع بمبلغ مختلف ← فرق مبلغ مع تصنيف السبب
        var refPairs = pairsGreedy(free(O), free(S), function (a, b) { return refLevel(a, b) > 0 && (a.m > 0) === (b.m > 0); }, function (a, b) { return refLevel(a, b) * 100 + dist(a, b); });
        refPairs.forEach(function (p) {
            var reason = classifyDiff(p.a, p.b, o);
            res.diffs.push({ a: p.a, b: p.b, diff: p.b.m - p.a.m, reason: reason, reasonText: REASONS[reason][0], action: REASONS[reason][1], pass: 'ref' });
        });

        // 6) انعكاس الإشارة: نفس المرجع/المبلغ بعكس الاتجاه ← فرق بضعف القيمة
        var flipPairs = pairsGreedy(free(O), free(S), function (a, b) {
            return a.m !== 0 && Math.abs(a.m + b.m) <= o.tolCents && (refLevel(a, b) > 0 || (dist(a, b) <= o.windowDays && !refsConflict(a, b)));
        }, function (a, b) { return dist(a, b); });
        flipPairs.forEach(function (p) { res.flips.push({ a: p.a, b: p.b, diff: p.b.m - p.a.m }); });

        // 7) توقيت أبعد من النافذة (يُعلَّم تأخيرًا لا خطأ)
        var timing = pairsGreedy(free(O), free(S), function (a, b) { return sameAmount(a, b, o.tolCents) && dist(a, b) <= o.timingDays && !refsConflict(a, b); }, function (a, b) { return dist(a, b); });
        timing.forEach(function (p) { res.matches.push({ a: p.a, b: p.b, pass: 'timing', level: 0, confidence: 'تأخير توقيت', timing: true }); });

        // 8) مبلغ قريب مع تاريخ (تقريب/ضريبة/تبديل أرقام/فاصلة عشرية) بلا مرجع
        var near = pairsGreedy(free(O), free(S), function (a, b) {
            if ((a.m > 0) !== (b.m > 0) || dist(a, b) > o.windowDays || refsConflict(a, b)) return false;
            var r = classifyDiff(a, b, o);
            return r === 'rounding' || r === 'vat-excl' || r === 'vat-incl' || r === 'transposition' || r === 'decimal';
        }, function (a, b) { return dist(a, b) + Math.abs(a.m - b.m) / 1e6; });
        near.forEach(function (p) {
            var reason = classifyDiff(p.a, p.b, o);
            res.diffs.push({ a: p.a, b: p.b, diff: p.b.m - p.a.m, reason: reason, reasonText: REASONS[reason][0], action: REASONS[reason][1], pass: 'near', lowConfidence: true });
        });

        // ── تصنيف المتبقي مع تشخيص وإجراء ──
        var oEnd = dayNum(ours.period && ours.period.to), sEnd = dayNum(supplier.period && supplier.period.to);
        var oStart = dayNum(ours.period && ours.period.from), sStart = dayNum(supplier.period && supplier.period.from);
        var matchedKeys = {};
        res.matches.forEach(function (m) { matchedKeys[m.a.side + '|' + m.a.refN + '|' + m.a.m] = 1; matchedKeys[m.b.side + '|' + m.b.refN + '|' + m.b.m] = 1; });

        function leftover(e, other) {
            var n = e.norm, cat, text, action, kind = 'error', sev = 2;
            var mySide = e.side;
            var lateInOwn = mySide === 'ours' ? (oEnd !== null && e.d !== null && oEnd - e.d <= 15) : (sEnd !== null && e.d !== null && sEnd - e.d <= 15);
            var otherEnd = mySide === 'ours' ? sEnd : oEnd, otherStart = mySide === 'ours' ? sStart : oStart;
            if (e.refN && matchedKeys[mySide + '|' + e.refN + '|' + e.m]) {
                return { cat: 'duplicate', text: 'قيد مكرر: المستند نفسه بالمبلغ نفسه سُجّل أكثر من مرة في الجانب ذاته', action: 'تحقق من التكرار واعكس القيد الزائد عند الطرف المسؤول', kind: 'error', sev: 3 };
            }
            // دفعة/فاتورة قرب نهاية فترتنا: «في الطريق» أولى بالتشخيص من «فصل فترات»
            var transit = (mySide === 'ours' && e.m < 0 && !NOTE_WORDS.test(n) && (lateInOwn || /شيك|cheque|check/.test(n)))
                || (mySide === 'supplier' && e.m > 0 && !DEBIT_NOTE.test(n) && lateInOwn);
            if (!transit && otherEnd !== null && e.d !== null && e.d > otherEnd) {
                return { cat: 'cutoff', text: 'قيد بعد نهاية فترة الطرف الآخر (فصل فترات)', action: 'يظهر في الفترة التالية عند الطرف الآخر؛ لا إجراء سوى المتابعة', kind: 'timing', sev: 1 };
            }
            if (!transit && otherStart !== null && e.d !== null && e.d < otherStart) {
                return { cat: 'cutoff', text: 'قيد قبل بداية فترة الطرف الآخر (فصل فترات)', action: 'تأكد أنه مضمَّن في الرصيد الافتتاحي للطرف الآخر', kind: 'timing', sev: 1 };
            }
            if (mySide === 'supplier') {
                if (e.m > 0) {
                    if (DEBIT_NOTE.test(n)) { cat = 'debit-note'; text = 'إشعار مدين من المورد غير مسجَّل عندنا'; action = 'اطلب نسخة الإشعار ووافق عليه أو اعترض قبل قيده'; }
                    else if (lateInOwn) { cat = 'goods-in-transit'; text = 'فاتورة قرب نهاية الفترة غير مسجَّلة عندنا: بضاعة أو خدمة قيد الاستلام'; action = 'تحقق من استلام البضاعة قبل نهاية الفترة وسجّل الفاتورة في الفترة الصحيحة'; kind = 'timing'; sev = 2; }
                    else { cat = 'invoice-not-in-ours'; text = 'فاتورة في كشف المورد ليست في دفاترنا'; action = 'اطلب صورة الفاتورة وأمر الشراء ومحضر الاستلام قبل أي قيد'; sev = 3; }
                } else if (NOTE_WORDS.test(n)) { cat = 'credit-note-not-recorded'; text = 'إشعار دائن/خصم/مرتجع سجّله المورد ولم نسجّله'; action = 'اطلب الإشعار وسجّله عندنا إن كان مستحقًا'; }
                else if (PAY_WORDS.test(n)) { cat = 'unexpected-payment'; text = 'دفعة يذكرها المورد ولا أثر لها في دفاترنا'; action = 'راجع كشف البنك وسندات الصرف؛ إن كانت دفعتنا فسجّلها، وإلا اطلب تفاصيلها'; sev = 3; }
                else { cat = 'credit-not-in-ours'; text = 'قيد دائن لدى المورد لا يقابله شيء عندنا'; action = 'اطلب تفاصيل القيد من المورد'; }
            } else {
                if (e.m < 0) {
                    if (NOTE_WORDS.test(n)) { cat = 'unaccepted-note'; text = 'إشعار دائن/مرتجع/خصم سجّلناه ولم يقبله المورد بعد'; action = 'أرسل للمورد نسخة الإشعار ومستند المرتجع ليسجّله، وهو أشيع أسباب النزاع'; sev = 3; }
                    else if (lateInOwn || /شيك|cheque|check/.test(n)) { cat = 'payment-in-transit'; text = 'دفعة سجّلناها قرب نهاية الفترة ولم يسجّلها المورد: دفعة/شيك في الطريق'; action = 'أرسل إثبات التحويل أو الشيك، واطلب تأكيد الاستلام'; kind = 'timing'; sev = 2; }
                    else if (PAY_WORDS.test(n)) { cat = 'payment-not-posted'; text = 'دفعة سجّلناها ولم يسجّلها المورد'; action = 'أرسل إثبات الدفع (إشعار بنكي) واطلب إقفالها على فواتيره'; sev = 3; }
                    else { cat = 'ours-credit-only'; text = 'قيد مدين لدينا لا يقابله شيء في كشف المورد'; action = 'راجع المستند وأرسل نسخته للمورد'; }
                } else { cat = 'invoice-not-in-supplier'; text = 'فاتورة مسجَّلة عندنا وغير موجودة في كشف المورد'; action = 'اطلب من المورد التحقق من إصدارها أو أرسل له نسخة الفاتورة'; sev = 3; }
            }
            return { cat: cat, text: text, action: action, kind: kind, sev: sev };
        }

        free(S).forEach(function (e) { var l = leftover(e); res.supplierOnly.push(Object.assign({ e: e }, l)); });
        free(O).forEach(function (e) { var l = leftover(e); res.oursOnly.push(Object.assign({ e: e }, l)); });

        // ── الجسر ───────────────────────────────────────────────────────────────
        var sum = function (arr, f) { return arr.reduce(function (s, x) { return s + f(x); }, 0); };
        var oClose = ours.closingPrinted !== null && ours.closingPrinted !== undefined ? ours.closingPrinted : ours.closingComputed;
        var sClose = supplier.closingPrinted !== null && supplier.closingPrinted !== undefined ? supplier.closingPrinted : supplier.closingComputed;
        var oC = ours.closingComputed, sC = supplier.closingComputed;
        var pairDiff = sum(res.matches, function (m) { return m.b.m - m.a.m; });
        var groupRes = sum(res.groups, function (gr) {
            var many = sum(gr.many, function (x) { return x.m; });
            return gr.side === 'ours' ? many - gr.single.m : gr.single.m - many;
        });
        var revRes = sum(res.reversals.supplier, function (r) { return r.a.m + r.b.m; }) - sum(res.reversals.ours, function (r) { return r.a.m + r.b.m; });
        var bridge = {
            oursClosing: oClose, supplierClosing: sClose, gross: sClose - oClose,
            openingDiff: supplier.opening - ours.opening,
            supplierOnly: sum(res.supplierOnly, function (x) { return x.e.m; }),
            oursOnly: -sum(res.oursOnly, function (x) { return x.e.m; }),
            amountDiffs: sum(res.diffs, function (d) { return d.diff; }),
            signFlips: sum(res.flips, function (f) { return f.diff; }),
            residual: pairDiff + groupRes + revRes,
            internalOurs: oClose - oC, internalSupplier: sClose - sC
        };
        bridge.explained = bridge.openingDiff + bridge.supplierOnly + bridge.oursOnly + bridge.amountDiffs + bridge.signFlips;
        bridge.expected = oClose + bridge.explained;
        bridge.unexplained = sClose - bridge.expected;           // = فروق التقريب + أخطاء الحساب الداخلية في الكشفين
        res.bridge = bridge;

        var tolAll = Math.max(o.tolCents, 1);
        res.status = Math.abs(bridge.gross) <= tolAll ? 'matched' : (Math.abs(bridge.unexplained) <= tolAll ? 'explained' : 'unexplained');
        res.kpis = {
            ours: O.length, supplier: S.length, matched: res.matches.length + res.groups.length, groups: res.groups.length, diffs: res.diffs.length + res.flips.length,
            supplierOnly: res.supplierOnly.length, oursOnly: res.oursOnly.length, reversals: res.reversals.ours.length + res.reversals.supplier.length,
            timing: res.matches.filter(function (m) { return m.timing; }).length
        };
        res.actions = buildActions(res);
        return res;
    };

    function buildActions(res) {
        var items = [];
        res.oursOnly.concat(res.supplierOnly).forEach(function (x) {
            items.push({ sev: x.sev, amount: Math.abs(x.e.m), side: x.e.side, cat: x.cat, ref: x.e.ref, date: x.e.date, text: x.text, action: x.action, e: x.e });
        });
        res.diffs.forEach(function (d) { items.push({ sev: Math.abs(d.diff) > 10000 ? 3 : 2, amount: Math.abs(d.diff), cat: 'amount-diff', ref: d.a.ref || d.b.ref, date: d.a.date || d.b.date, text: d.reasonText, action: d.action, side: 'both', d: d }); });
        res.flips.forEach(function (f) { items.push({ sev: 3, amount: Math.abs(f.diff), cat: 'sign-flip', ref: f.a.ref || f.b.ref, date: f.a.date, text: 'قيد بعكس الاتجاه عند أحد الطرفين (يضاعف الفرق)', action: 'راجع طبيعة المستند (فاتورة أم إشعار) وصحّح الاتجاه عند الطرف الخاطئ', side: 'both' }); });
        items.sort(function (a, b) { return (b.sev - a.sev) || (b.amount - a.amount); });
        return items;
    }

    SM.reasonLabels = REASONS;

    if (typeof module !== 'undefined' && module.exports) module.exports = SM;
})(typeof window !== 'undefined' ? window : globalThis);
