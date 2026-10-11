/* مطابق كشوفات الحساب — إعادة بناء الجدول من صناديق الكلمات (PDF/OCR) لكشوف عربية من اليمين لليسار.
   كلمة = {text, x0, x1, y0, y1, conf?}. المخرج {rows, preface, confs} يغذّي SM.parseSide مباشرة. */
(function (g) {
    'use strict';
    var SM = g.SM = g.SM || {};
    var AR = /[؀-ۿ]/;

    function median(arr) {
        if (!arr.length) return 10;
        var a = arr.slice().sort(function (x, y) { return x - y; });
        return a[Math.floor(a.length / 2)];
    }
    function mid(w) { return (w.y0 + w.y1) / 2; }
    function cx(w) { return (w.x0 + w.x1) / 2; }
    function height(w) { return Math.max(1, w.y1 - w.y0); }

    // ── ترتيب بصري معكوس: نكشفه بمطابقة كلمات الترويسة ──────────────────────────
    function reverseStr(s) { return Array.from(s).reverse().join(''); }
    SM.fixVisualOrder = function (words) {
        var normal = 0, reversed = 0;
        words.forEach(function (w) {
            if (!AR.test(w.text)) return;
            if (SM.labelField(w.text)) normal++;
            if (SM.labelField(reverseStr(w.text))) reversed++;
        });
        if (reversed > normal && reversed >= 2) {
            words.forEach(function (w) { if (AR.test(w.text)) w.text = reverseStr(w.text); });
            return true;
        }
        return false;
    };

    // ── أسطر ────────────────────────────────────────────────────────────────────
    function readingOrder(ws) {
        var arabic = ws.some(function (w) { return AR.test(w.text); });
        return ws.slice().sort(function (a, b) { return arabic ? b.x0 - a.x0 : a.x0 - b.x0; });
    }
    function joinWords(ws) { return readingOrder(ws).map(function (w) { return w.text; }).join(' ').replace(/\s+/g, ' ').trim(); }

    /** يدمج الحروف المتفرقة (بعض ملفات PDF تخزّن حرفًا حرفًا): الأجزاء الملاصقة فعليًا تصبح كلمة. */
    function mergeGlyphs(ws, h) {
        var asc = ws.slice().sort(function (a, b) { return a.x0 - b.x0; }), out = [], run = null;
        asc.forEach(function (w) {
            if (run && (w.x0 - run.x1) < 0.18 * h && (run.text.length <= 2 || w.text.length <= 1) && Math.abs(mid(w) - mid(run)) < h * 0.6) {
                run.parts.push(w); run.x1 = Math.max(run.x1, w.x1); run.y0 = Math.min(run.y0, w.y0); run.y1 = Math.max(run.y1, w.y1);
                run.conf = Math.min(run.conf, w.conf === undefined ? 100 : w.conf);
            } else {
                if (run) out.push(run);
                run = { parts: [w], x0: w.x0, x1: w.x1, y0: w.y0, y1: w.y1, conf: w.conf === undefined ? 100 : w.conf, text: '' };
            }
        });
        if (run) out.push(run);
        return out.map(function (r) {
            var t = r.parts.length === 1 ? r.parts[0].text : joinWords(r.parts).replace(/ /g, '');
            return { text: t, x0: r.x0, x1: r.x1, y0: r.y0, y1: r.y1, conf: r.conf };
        });
    }

    SM.linesFromWords = function (words) {
        words = words.filter(function (w) { return w && String(w.text).trim(); });
        if (!words.length) return [];
        var h = median(words.map(height)), sorted = words.slice().sort(function (a, b) { return mid(a) - mid(b); }), lines = [], cur = null;
        sorted.forEach(function (w) {
            if (cur && Math.abs(mid(w) - cur.y) <= h * 0.55) { cur.words.push(w); cur.y = (cur.y * (cur.words.length - 1) + mid(w)) / cur.words.length; }
            else { cur = { y: mid(w), words: [w] }; lines.push(cur); }
        });
        lines.forEach(function (l) { l.h = h; l.words = mergeGlyphs(l.words, h); l.words.sort(function (a, b) { return b.x0 - a.x0; }); });
        return lines;
    };

    /** عبارات الترويسة: كلمات متجاورة تُجمع (رقم + المستند). */
    function phrases(line) {
        var out = [], cur = null;
        line.words.slice().sort(function (a, b) { return b.x0 - a.x0; }).forEach(function (w) {          // من اليمين لليسار
            if (cur && (cur.x0 - w.x1) <= line.h * 0.9) { cur.words.push(w); cur.x0 = Math.min(cur.x0, w.x0); }
            else { cur = { words: [w], x0: w.x0, x1: w.x1 }; out.push(cur); }
            cur.x1 = Math.max(cur.x1, w.x1);
        });
        out.forEach(function (p) { p.text = joinWords(p.words); p.cx = (p.x0 + p.x1) / 2; });
        return out;
    }

    function findHeaderBand(lines) {
        var best = null;
        for (var i = 0; i < Math.min(lines.length, 40); i++) {
            for (var span = 1; span <= 3 && i + span <= lines.length; span++) {
                var anchors = [], fields = {}, distinct = 0;
                for (var k = i; k < i + span; k++) {
                    if (k > i && lines[k].y - lines[k - 1].y > lines[k].h * 2.6) break;
                    phrases(lines[k]).forEach(function (p) {
                        var f = SM.labelField(p.text);
                        if (!f || f === 'due') return;
                        anchors.push({ field: f, p: p });
                        if (!fields[f]) { fields[f] = 1; distinct++; }
                    });
                }
                var money = fields.debit || fields.credit || fields.amount || fields.balance, id = fields.date || fields.ref || fields.desc;
                if (distinct >= 3 && money && id) {
                    var score = distinct * 10 - span;
                    if (!best || score > best.score) best = { start: i, end: i + span - 1, anchors: anchors, score: score };
                }
            }
        }
        return best;
    }

    function numericToken(words) {
        var best = null, bestScore = -1;
        words.forEach(function (w) {
            var v = SM.parseNumber(w.text);
            if (v === null) return;
            var score = (/[.,]\d{2}$/.test(w.text) ? 2 : 0) + w.text.length / 20;
            if (score > bestScore) { bestScore = score; best = w; }
        });
        return best;
    }

    /** يُرجع {rows, preface, confs, how}. pageW اختياري. */
    SM.wordsToTable = function (words, opts) {
        opts = opts || {};
        words.forEach(function (w) { w.text = String(w.text).normalize('NFKC').replace(/[‎‏‪-‮⁦-⁩]/g, ''); });   // أشكال العرض (ﻣﺪﻳﻦ) ← حروف عادية
        SM.fixVisualOrder(words);
        var lines = SM.linesFromWords(words);
        if (!lines.length) return { rows: [], preface: [], confs: [], how: 'empty' };
        var band = findHeaderBand(lines);
        if (!band) return looseTable(lines);

        // مرتكزات الأعمدة: حذف عنوان رئيسي يمتد فوق عنوانين فرعيين (المبلغ فوق مدين/دائن)
        var anchors = band.anchors.slice();
        var sub = anchors.filter(function (a) { return a.field === 'debit' || a.field === 'credit'; });
        anchors = anchors.filter(function (a) {
            if (a.field !== 'amount' || sub.length < 2) return true;
            return !sub.every(function (s) { return s.p.cx >= a.p.x0 - 2 && s.p.cx <= a.p.x1 + 2; });
        });
        var byField = {};
        anchors.forEach(function (a) { if (!byField[a.field]) byField[a.field] = a; });
        var cols = Object.keys(byField).map(function (f) { return { field: f, cx: byField[f].p.cx, label: byField[f].p.text }; }).sort(function (a, b) { return a.cx - b.cx; });
        cols.forEach(function (col, idx) {
            col.lo = idx === 0 ? -Infinity : (cols[idx - 1].cx + col.cx) / 2;
            col.hi = idx === cols.length - 1 ? Infinity : (col.cx + cols[idx + 1].cx) / 2;
        });
        var preface = lines.slice(0, band.start).map(function (l) { return joinWords(l.words); });
        var headerRow = cols.map(function (c) { return c.label; });
        var rows = [headerRow], confs = [100], prev = null;
        for (var i = band.end + 1; i < lines.length; i++) {
            var line = lines[i], cells = cols.map(function () { return []; });
            line.words.forEach(function (w) {
                var x = cx(w);
                for (var c = 0; c < cols.length; c++) if (x >= cols[c].lo && x < cols[c].hi) { cells[c].push(w); break; }
            });
            var row = cols.map(function (col, c) {
                var ws = cells[c];
                if (!ws.length) return '';
                if (col.field === 'debit' || col.field === 'credit' || col.field === 'amount' || col.field === 'balance') {
                    var tok = numericToken(ws);
                    if (tok) { var t = tok.text; var neighbor = ws.filter(function (w) { return w !== tok && /^(cr|dr|دائن|مدين)$/i.test(w.text); })[0]; return neighbor ? t + ' ' + neighbor.text : t; }
                    return '';
                }
                if (col.field === 'date') {
                    var dw = ws.filter(function (w) { return SM.parseDate(w.text); })[0];
                    return dw ? dw.text : joinWords(ws);
                }
                return joinWords(ws);
            });
            var minConf = 100;
            line.words.forEach(function (w) { if (w.conf !== undefined) minConf = Math.min(minConf, w.conf); });
            var onlyDesc = cols.every(function (col, c) { return !row[c] || col.field === 'desc'; }) && cols.some(function (col, c) { return col.field === 'desc' && row[c]; });
            if (onlyDesc && prev) {                                  // سطر وصف متابع لسطر سابق
                var di = cols.map(function (c) { return c.field; }).indexOf('desc');
                prev[di] = (prev[di] + ' ' + row[di]).trim();
                continue;
            }
            if (row.some(function (v) { return v !== ''; })) { rows.push(row); confs.push(minConf); prev = row; }
        }
        return { rows: rows, preface: preface, confs: confs, how: 'header' };
    };

    /** احتياطي بلا ترويسة: تاريخ / مرجع / وصف / أرقام في آخر السطر. */
    function looseTable(lines) {
        var rows = [], confs = [];
        lines.forEach(function (l) {
            var ws = readingOrder(l.words), date = '', nums = [], rest = [], conf = 100;
            ws.forEach(function (w) {
                if (w.conf !== undefined) conf = Math.min(conf, w.conf);
                if (!date && SM.parseDate(w.text) && /[\/\-.]/.test(w.text)) date = w.text;
                else if (SM.parseNumber(w.text) !== null && /[.,]|\d{4,}/.test(w.text)) nums.push(w.text);
                else rest.push(w.text);
            });
            if (!date && !nums.length) return;
            var ref = rest.filter(function (t) { return /\d/.test(t) && t.length <= 24 && !AR.test(t); })[0] || '';
            var desc = rest.filter(function (t) { return t !== ref; }).join(' ');
            rows.push([date, ref, desc].concat(nums.slice(-3)));
            confs.push(conf);
        });
        return { rows: rows, preface: [], confs: confs, how: 'loose' };
    }

    if (typeof module !== 'undefined' && module.exports) module.exports = SM;
})(typeof window !== 'undefined' ? window : globalThis);
