/* مطابق كشوفات الحساب — النواة: تطبيع العربية، قراءة الأرقام والتواريخ، تنسيق المبالغ.
   كل المبالغ تُحسب بالهللات (أعداد صحيحة) ولا نثق بالفاصلة العائمة مباشرة. */
(function (g) {
    'use strict';
    var SM = g.SM = g.SM || {};

    // ── تطبيع النص العربي (للمطابقة فقط: لا يُعرض للمستخدم) ─────────────────────
    var BIDI = /[‎‏‪-‮⁦-⁩​-‍﻿]/g;
    var DIACRITICS = /[ً-ٰٟۖ-ۭ]/g;
    var MAP = { 'ی': 'ي', 'ى': 'ي', 'ک': 'ك', 'ھ': 'ه', 'ہ': 'ه', 'ة': 'ه',
        'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا', 'ؤ': 'و', 'ئ': 'ي' };

    SM.toLatinDigits = function (s) {
        return String(s == null ? '' : s)
            .replace(/[٠-٩]/g, function (d) { return String(d.charCodeAt(0) - 0x0660); })
            .replace(/[۰-۹]/g, function (d) { return String(d.charCodeAt(0) - 0x06f0); })
            .replace(/٫/g, '.').replace(/٬/g, ',');
    };

    SM.normAr = function (s) {
        var t = String(s == null ? '' : s).normalize('NFKC').replace(BIDI, '').replace(/ـ/g, '').replace(DIACRITICS, '');
        t = t.replace(/[یىکھہةأإآٱؤئ]/g, function (c) { return MAP[c]; });
        return SM.toLatinDigits(t).toLowerCase().replace(/\s+/g, ' ').trim();
    };

    // ── الأرقام ─────────────────────────────────────────────────────────────────
    var CURRENCY = /(ر\.?\s?س|ريال|سعودي|sar|usd|aed|eur|دولار|درهم|\$|€|﷼)/gi;

    function cleanNumberText(raw) {
        var t = SM.toLatinDigits(String(raw)).normalize('NFKC').replace(BIDI, '');
        t = t.replace(CURRENCY, ' ').replace(/−|–|—/g, '-');
        return t.trim();
    }

    /** يحوّل نصًّا رقميًا خالصًا إلى {v, drcr} أو null إن كان نصًّا يحتوي أرقامًا فقط (مثل INV-123 أو قيمة1). */
    SM.parseNumberEx = function (raw) {
        if (raw == null || raw === '') return null;
        if (typeof raw === 'number') return isFinite(raw) ? { v: raw, drcr: null } : null;
        var t = cleanNumberText(raw);
        if (!t) return null;
        var neg = false, drcr = null;
        if (/^\(.*\)$/.test(t)) { neg = true; t = t.slice(1, -1).trim(); }
        var tail = t.match(/\s*(cr|dr|مدين|دائن)\.?$/i);
        if (tail) { drcr = /cr|دائن/i.test(tail[1]) ? 'cr' : 'dr'; t = t.slice(0, tail.index).trim(); }
        if (/-$/.test(t)) { neg = true; t = t.slice(0, -1).trim(); }
        if (/^-/.test(t)) { neg = !neg; t = t.slice(1).trim(); }
        if (/^\+/.test(t)) t = t.slice(1).trim();
        if (!/^\d[\d.,\s']*$/.test(t)) return null;
        t = t.replace(/[\s']/g, '');
        var dots = (t.match(/\./g) || []).length, commas = (t.match(/,/g) || []).length;
        var decSep = null;
        if (dots && commas) decSep = t.lastIndexOf('.') > t.lastIndexOf(',') ? '.' : ',';
        else if (dots === 1) decSep = '.';
        else if (commas === 1) decSep = (t.length - t.lastIndexOf(',') - 1) === 3 ? null : ',';      // 1,234 ألف، 12,50 كسور
        var intPart = t, frac = '';
        if (decSep) { var i = t.lastIndexOf(decSep); intPart = t.slice(0, i); frac = t.slice(i + 1); }
        intPart = intPart.replace(/[.,]/g, '');
        if (!/^\d+$/.test(intPart) || (frac && !/^\d+$/.test(frac))) return null;
        var n = parseFloat(intPart + (frac ? '.' + frac : ''));
        if (!isFinite(n)) return null;
        return { v: neg ? -n : n, drcr: drcr };
    };

    SM.parseNumber = function (raw) {
        var r = SM.parseNumberEx(raw);
        return r ? r.v : null;
    };

    /** يلتقط رقمًا نقديًّا من خلية قد تحوي نصًّا حولها؛ يفضّل ما له كسور أو فواصل آلاف. */
    SM.extractMoney = function (raw) {
        if (typeof raw === 'number') return isFinite(raw) ? raw : null;
        var direct = SM.parseNumber(raw);
        if (direct !== null) return direct;
        var t = cleanNumberText(raw), best = null, bestScore = -1;
        var re = /\(?-?\d[\d.,\s]*\d\)?-?|\(?-?\d\)?/g, m;
        while ((m = re.exec(t))) {
            var piece = m[0].trim();
            var val = SM.parseNumber(piece);
            if (val === null) continue;
            var score = (/[.,]\d{1,2}$/.test(piece) ? 3 : 0) + (/\d[.,]\d{3}/.test(piece) ? 2 : 0) + Math.min(piece.length, 10) / 10;
            if (score > bestScore) { bestScore = score; best = val; }
        }
        return best;
    };

    // ── التواريخ ────────────────────────────────────────────────────────────────
    var MONTHS = {
        jan: 1, january: 1, feb: 2, february: 2, mar: 3, march: 3, apr: 4, april: 4, may: 5, jun: 6, june: 6, jul: 7, july: 7,
        aug: 8, august: 8, sep: 9, sept: 9, september: 9, oct: 10, october: 10, nov: 11, november: 11, dec: 12, december: 12,
        'يناير': 1, 'كانون الثاني': 1, 'فبراير': 2, 'شباط': 2, 'مارس': 3, 'اذار': 3, 'ابريل': 4, 'نيسان': 4, 'مايو': 5, 'ايار': 5,
        'يونيو': 6, 'حزيران': 6, 'يوليو': 7, 'تموز': 7, 'اغسطس': 8, 'اب': 8, 'سبتمبر': 9, 'ايلول': 9, 'اكتوبر': 10,
        'تشرين الاول': 10, 'نوفمبر': 11, 'تشرين الثاني': 11, 'ديسمبر': 12, 'كانون الاول': 12
    };

    function pad(n) { return (n < 10 ? '0' : '') + n; }
    function validYmd(y, m, d) {
        if (y < 1990 || y > 2100 || m < 1 || m > 12 || d < 1 || d > 31) return null;
        var dt = new Date(Date.UTC(y, m - 1, d));
        if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== m - 1 || dt.getUTCDate() !== d) return null;
        return y + '-' + pad(m) + '-' + pad(d);
    }

    SM.excelSerialToIso = function (serial) {
        if (typeof serial !== 'number' || serial < 20000 || serial > 80000) return null;
        var dt = new Date(Math.round((serial - 25569) * 86400000));
        return validYmd(dt.getUTCFullYear(), dt.getUTCMonth() + 1, dt.getUTCDate());
    };

    /** يرجع 'YYYY-MM-DD' أو null. قد يظهر التاريخ في أي موضع داخل الخلية. */
    SM.parseDate = function (raw, dayFirst) {
        if (raw == null || raw === '') return null;
        if (dayFirst === undefined) dayFirst = true;
        if (typeof raw === 'number') return SM.excelSerialToIso(raw);
        var t = SM.normAr(raw);
        var m = t.match(/(\d{4})[\/\-.](\d{1,2})[\/\-.](\d{1,2})/);
        if (m) return validYmd(+m[1], +m[2], +m[3]);
        m = t.match(/(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4}|\d{2})(?!\d)/);
        if (m) {
            var a = +m[1], b = +m[2], y = +m[3];
            if (y < 100) y += 2000;
            var d = dayFirst ? a : b, mo = dayFirst ? b : a;
            var out = validYmd(y, mo, d);
            return out || validYmd(y, d, mo);                      // اعتمد المعكوس إن لم يصح الترتيب المختار
        }
        m = t.match(/(\d{1,2})[\s\-\/.]*([a-zء-ي]+(?:\s[ء-ي]+)?)[\s\-\/.,]*(\d{4}|\d{2})(?!\d)/);
        if (m && MONTHS[m[2].trim()]) { var yy = +m[3]; return validYmd(yy < 100 ? yy + 2000 : yy, MONTHS[m[2].trim()], +m[1]); }
        m = t.match(/([a-z]{3,9})[\s\-\/.]*(\d{1,2})[\s,\-\/.]*(\d{4})/);
        if (m && MONTHS[m[1]]) return validYmd(+m[3], MONTHS[m[1]], +m[2]);
        return null;
    };

    SM.isoToDisplay = function (iso) {
        if (!iso) return '';
        var p = iso.split('-');
        return p[2] + '/' + p[1] + '/' + p[0];
    };

    // ── المبالغ ─────────────────────────────────────────────────────────────────
    SM.cents = function (n) { return Math.round((Number(n) || 0) * 100 + (n < 0 ? -1e-9 : 1e-9)); };
    SM.fromCents = function (c) { return c / 100; };

    /** #,##0.00 بأرقام لاتينية؛ السالب بعلامة ناقص. */
    SM.fmt = function (n, opts) {
        var c = typeof n === 'number' ? Math.round(n * 100) : 0;
        var neg = c < 0; c = Math.abs(c);
        var whole = Math.floor(c / 100), frac = c % 100;
        var s = String(whole).replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '.' + (frac < 10 ? '0' : '') + frac;
        if (opts && opts.blankZero && c === 0) return '';
        return neg ? '-' + s : s;
    };

    SM.escapeHtml = function (s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    };

    /** رقم مرجعي مُطبَّع: بلا فواصل ولا أصفار بادئة، ومنه رموز رقمية للمطابقة الجزئية. */
    SM.normRef = function (s) {
        var t = SM.normAr(s).replace(/[^a-z0-9ء-ي]/g, '');
        return t.replace(/^0+(?=\d)/, '');
    };
    SM.refDigits = function (s) {
        var out = [], re = /\d{3,}/g, m, t = SM.toLatinDigits(s || '');
        while ((m = re.exec(t))) out.push(m[0].replace(/^0+(?=\d)/, ''));
        return out;
    };

    if (typeof module !== 'undefined' && module.exports) module.exports = SM;
})(typeof window !== 'undefined' ? window : globalThis);
