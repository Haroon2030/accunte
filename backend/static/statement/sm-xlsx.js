/* مطابق كشوفات الحساب — قارئ ومولّد XLSX بلا مكتبات، وقارئ CSV بكشف الفاصل والترميز.
   يعمل في المتصفح وفي Node (للاختبارات). فك الضغط عبر DecompressionStream('deflate-raw'). */
(function (g) {
    'use strict';
    var SM = g.SM = g.SM || {};
    var enc = new TextEncoder();

    // ── ZIP ─────────────────────────────────────────────────────────────────────
    function u16(b, o) { return b[o] | (b[o + 1] << 8); }
    function u32(b, o) { return (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0; }

    function inflateRaw(bytes) {
        var ds = new DecompressionStream('deflate-raw');
        var stream = new Blob([bytes]).stream().pipeThrough(ds);
        return new Response(stream).arrayBuffer().then(function (ab) { return new Uint8Array(ab); });
    }

    /** يُرجع Promise<Map<string, Uint8Array>> لمحتويات الأرشيف. */
    SM.unzip = function (buffer) {
        var b = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
        var eocd = -1;
        for (var i = b.length - 22; i >= Math.max(0, b.length - 65557); i--) {
            if (u32(b, i) === 0x06054b50) { eocd = i; break; }
        }
        if (eocd < 0) return Promise.reject(new Error('الملف ليس أرشيف XLSX صالحًا'));
        var count = u16(b, eocd + 10), off = u32(b, eocd + 16), jobs = [], names = [];
        for (var n = 0; n < count; n++) {
            if (u32(b, off) !== 0x02014b50) break;
            var method = u16(b, off + 10), csize = u32(b, off + 20), nlen = u16(b, off + 28), elen = u16(b, off + 30),
                clen = u16(b, off + 32), lho = u32(b, off + 42);
            var name = new TextDecoder().decode(b.subarray(off + 46, off + 46 + nlen));
            var lnlen = u16(b, lho + 26), lelen = u16(b, lho + 28), start = lho + 30 + lnlen + lelen;
            var data = b.subarray(start, start + csize);
            names.push(name);
            jobs.push(method === 0 ? Promise.resolve(data) : method === 8 ? inflateRaw(data) : Promise.reject(new Error('ضغط غير مدعوم')));
            off += 46 + nlen + elen + clen;
        }
        return Promise.all(jobs).then(function (arr) {
            var map = new Map();
            names.forEach(function (nm, k) { map.set(nm, arr[k]); });
            return map;
        });
    };

    var CRC_TABLE = (function () {
        var t = new Uint32Array(256);
        for (var n = 0; n < 256; n++) {
            var c = n;
            for (var k = 0; k < 8; k++) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
            t[n] = c >>> 0;
        }
        return t;
    })();
    SM.crc32 = function (bytes) {
        var c = 0xffffffff;
        for (var i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
        return (c ^ 0xffffffff) >>> 0;
    };

    /** أرشيف ZIP بلا ضغط (store): صالح تمامًا لملفات XLSX. files: [{name, data: Uint8Array|string}] */
    SM.zipStore = function (files) {
        var chunks = [], central = [], offset = 0;
        function push(bytes) { chunks.push(bytes); offset += bytes.length; }
        function le16(v) { return [v & 255, (v >>> 8) & 255]; }
        function le32(v) { return [v & 255, (v >>> 8) & 255, (v >>> 16) & 255, (v >>> 24) & 255]; }
        files.forEach(function (f) {
            var nameB = enc.encode(f.name), data = typeof f.data === 'string' ? enc.encode(f.data) : f.data, crc = SM.crc32(data);
            var lho = offset;
            push(new Uint8Array([].concat(le32(0x04034b50), le16(20), le16(0x0800), le16(0), le16(0), le16(0x21), le32(crc),
                le32(data.length), le32(data.length), le16(nameB.length), le16(0))));
            push(nameB); push(data);
            central.push(new Uint8Array([].concat(le32(0x02014b50), le16(20), le16(20), le16(0x0800), le16(0), le16(0), le16(0x21),
                le32(crc), le32(data.length), le32(data.length), le16(nameB.length), le16(0), le16(0), le16(0), le16(0), le32(0), le32(lho))));
            central.push(nameB);
        });
        var cdStart = offset;
        central.forEach(push);
        var cdSize = offset - cdStart;
        push(new Uint8Array([].concat(le32(0x06054b50), le16(0), le16(0), le16(files.length), le16(files.length), le32(cdSize), le32(cdStart), le16(0))));
        var total = chunks.reduce(function (a, c) { return a + c.length; }, 0), out = new Uint8Array(total), pos = 0;
        chunks.forEach(function (c) { out.set(c, pos); pos += c.length; });
        return out;
    };

    // ── XML خفيف (ملفات XLSX مولَّدة آليًا فيكفي التعابير النمطية) ───────────────
    function unescapeXml(s) {
        return s.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos);/gi, function (m, e) {
            if (e[0] === '#') return String.fromCodePoint(e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10));
            return { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" }[e.toLowerCase()];
        });
    }
    function textOf(xml) {                                   // كل <t> داخل عنصر
        var out = '', re = /<t[^>]*>([\s\S]*?)<\/t>/g, m;
        while ((m = re.exec(xml))) out += m[1];
        return unescapeXml(out);
    }
    function attr(tag, name) {
        var m = tag.match(new RegExp('\\b' + name + '="([^"]*)"'));
        return m ? unescapeXml(m[1]) : null;
    }
    function colIndex(ref) {
        var letters = ref.replace(/[0-9]/g, ''), n = 0;
        for (var i = 0; i < letters.length; i++) n = n * 26 + (letters.charCodeAt(i) - 64);
        return n - 1;
    }
    var BUILTIN_DATE_FMTS = { 14: 1, 15: 1, 16: 1, 17: 1, 18: 1, 19: 1, 20: 1, 21: 1, 22: 1, 27: 1, 28: 1, 29: 1, 30: 1, 31: 1,
        32: 1, 33: 1, 34: 1, 35: 1, 36: 1, 45: 1, 46: 1, 47: 1, 50: 1, 51: 1, 52: 1, 53: 1, 54: 1, 55: 1, 56: 1, 57: 1, 58: 1 };

    function isDateFormatCode(code) {
        var c = code.replace(/"[^"]*"/g, '').replace(/\[[^\]]*\]/g, '').replace(/\\./g, '');
        return /[dmyhs]/i.test(c) && !/^[#0?.,%\s$€]*$/.test(c);
    }

    function dateXfs(stylesXml) {
        var custom = {}, re = /<numFmt\b[^>]*>/g, m;
        while ((m = re.exec(stylesXml || ''))) {
            var id = attr(m[0], 'numFmtId'), code = attr(m[0], 'formatCode');
            if (id != null && code != null) custom[id] = isDateFormatCode(code);
        }
        var cellXfs = (stylesXml || '').match(/<cellXfs[\s\S]*?<\/cellXfs>/);
        var flags = [];
        if (cellXfs) {
            var xr = /<xf\b[^>]*>/g, x;
            while ((x = xr.exec(cellXfs[0]))) {
                var nid = attr(x[0], 'numFmtId');
                flags.push(!!(BUILTIN_DATE_FMTS[nid] || custom[nid]));
            }
        }
        return flags;
    }

    function serialToIso(v) { return SM.excelSerialToIso ? SM.excelSerialToIso(v) : null; }

    /** يقرأ كل الأوراق: Promise<[{name, rows}]>؛ الخلايا نصوص/أرقام، والتواريخ تُحوَّل إلى YYYY-MM-DD. */
    SM.readXlsx = function (buffer) {
        return SM.unzip(buffer).then(function (zip) {
            function get(name) { var f = zip.get(name); return f ? new TextDecoder('utf-8').decode(f) : null; }
            var workbook = get('xl/workbook.xml');
            if (!workbook) throw new Error('الملف لا يحتوي مصنّفًا (workbook.xml)');
            var rels = get('xl/_rels/workbook.xml.rels') || '';
            var relMap = {}, rr = /<Relationship\b[^>]*>/g, r;
            while ((r = rr.exec(rels))) relMap[attr(r[0], 'Id')] = attr(r[0], 'Target');
            var shared = [], sst = get('xl/sharedStrings.xml');
            if (sst) {
                var sr = /<si\b[\s\S]*?<\/si>|<si\s*\/>/g, s;
                while ((s = sr.exec(sst))) shared.push(textOf(s[0]));
            }
            var dateFlags = dateXfs(get('xl/styles.xml'));
            var sheets = [], shRe = /<sheet\b[^>]*>/g, sh;
            while ((sh = shRe.exec(workbook))) {
                var rid = attr(sh[0], 'r:id'), target = relMap[rid] || '';
                var path = target.indexOf('/') === 0 ? target.slice(1) : 'xl/' + target.replace(/^\.\//, '');
                var xml = get(path);
                if (!xml) continue;
                sheets.push({ name: attr(sh[0], 'name') || 'Sheet', rows: parseSheet(xml, shared, dateFlags) });
            }
            return sheets;
        });
    };

    function parseSheet(xml, shared, dateFlags) {
        var rows = [], rowRe = /<row\b[^>]*?(?:\/>|>[\s\S]*?<\/row>)/g, rm, lastRow = -1;
        while ((rm = rowRe.exec(xml))) {
            var rtag = rm[0].match(/^<row\b[^>]*>/)[0];
            var rn = attr(rtag, 'r');
            var ri = rn ? parseInt(rn, 10) - 1 : lastRow + 1;
            while (rows.length < ri) rows.push([]);
            lastRow = ri;
            var row = [], cellRe = /<c\b[^>]*?(?:\/>|>[\s\S]*?<\/c>)/g, cm, seq = 0;
            while ((cm = cellRe.exec(rm[0]))) {
                var ctag = cm[0].match(/^<c\b[^>]*>/)[0];
                var ref = attr(ctag, 'r'), ci = ref ? colIndex(ref) : seq;
                seq = ci + 1;
                var t = attr(ctag, 't'), sIdx = attr(ctag, 's');
                var vm = cm[0].match(/<v>([\s\S]*?)<\/v>/), val = null;
                if (t === 's') val = vm ? shared[parseInt(vm[1], 10)] : '';
                else if (t === 'inlineStr') val = textOf(cm[0]);
                else if (t === 'str' || t === 'e') val = vm ? unescapeXml(vm[1]) : '';
                else if (t === 'b') val = vm ? (vm[1] === '1' ? 'TRUE' : 'FALSE') : '';
                else if (vm) {
                    var num = parseFloat(vm[1]);
                    val = num;
                    if (isFinite(num) && sIdx != null && dateFlags[parseInt(sIdx, 10)]) {
                        var iso = serialToIso(num);
                        if (iso) val = iso;
                    }
                }
                while (row.length < ci) row.push('');
                row[ci] = val == null ? '' : val;
            }
            rows.push(row);
        }
        return rows;
    }

    // ── مولّد XLSX ──────────────────────────────────────────────────────────────
    function xmlEsc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
    function colName(i) {
        var s = '';
        for (i++; i > 0; i = Math.floor((i - 1) / 26)) s = String.fromCharCode(65 + ((i - 1) % 26)) + s;
        return s;
    }
    function sanitizeSheetName(n, used) {
        var name = String(n).replace(/[\[\]:*?\/\\]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 31) || 'ورقة';
        var base = name, k = 2;
        while (used[name.toLowerCase()]) { name = base.slice(0, 28) + ' ' + k++; }
        used[name.toLowerCase()] = 1;
        return name;
    }

    var STYLES = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' +
        '<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00;[Red]-#,##0.00"/></numFmts>' +
        '<fonts count="3"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>' +
        '<fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>' +
        '<fill><patternFill patternType="solid"><fgColor rgb="FF13314A"/><bgColor indexed="64"/></patternFill></fill>' +
        '<fill><patternFill patternType="solid"><fgColor rgb="FFE6EEF8"/><bgColor indexed="64"/></patternFill></fill></fills>' +
        '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left/><right/><top style="thin"><color rgb="FF13314A"/></top><bottom style="double"><color rgb="FF13314A"/></bottom><diagonal/></border></borders>' +
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>' +
        '<cellXfs count="6">' +
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>' +
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>' +
        '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>' +
        '<xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1"/>' +
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>' +
        '<xf numFmtId="164" fontId="2" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyBorder="1"/>' +
        '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>';

    /** sheets: [{name, rows, header:true, widths:[...], bold:[rowIdx], total:[rowIdx]}]. الأرقام تُكتب أرقامًا ويُنسَّق المبلغ #,##0.00. */
    SM.buildXlsx = function (sheets) {
        var used = {}, files = [], sheetXml = [], names = [];
        sheets.forEach(function (sh, si) {
            var name = sanitizeSheetName(sh.name, used);
            names.push(name);
            var rowsXml = (sh.rows || []).map(function (row, ri) {
                var isHeader = sh.header !== false && ri === 0, isBold = (sh.bold || []).indexOf(ri) >= 0, isTotal = (sh.total || []).indexOf(ri) >= 0;
                var cells = row.map(function (v, ci) {
                    if (v === '' || v == null) return '';
                    var ref = colName(ci) + (ri + 1);
                    if (typeof v === 'number' && isFinite(v)) {
                        return '<c r="' + ref + '" s="' + (isTotal ? 5 : 2) + '"><v>' + v + '</v></c>';
                    }
                    var style = isHeader ? 1 : (isBold ? 3 : 4);
                    return '<c r="' + ref + '" t="inlineStr" s="' + style + '"><is><t xml:space="preserve">' + xmlEsc(v) + '</t></is></c>';
                }).join('');
                return '<row r="' + (ri + 1) + '"' + (isHeader ? ' ht="24" customHeight="1"' : '') + '>' + cells + '</row>';
            }).join('');
            var cols = (sh.widths || []).map(function (w, i) { return '<col min="' + (i + 1) + '" max="' + (i + 1) + '" width="' + w + '" customWidth="1"/>'; }).join('');
            var pane = sh.header !== false ? '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>' : '';
            sheetXml.push('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' +
                '<sheetViews><sheetView workbookViewId="0" rightToLeft="1"' + (si === 0 ? ' tabSelected="1"' : '') + '>' + pane + '</sheetView></sheetViews>' +
                (cols ? '<cols>' + cols + '</cols>' : '') + '<sheetData>' + rowsXml + '</sheetData></worksheet>');
        });
        files.push({ name: '[Content_Types].xml', data: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
            sheets.map(function (_, i) { return '<Override PartName="/xl/worksheets/sheet' + (i + 1) + '.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'; }).join('') + '</Types>' });
        files.push({ name: '_rels/.rels', data: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>' });
        files.push({ name: 'xl/workbook.xml', data: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView activeTab="0"/></bookViews><sheets>' +
            names.map(function (n, i) { return '<sheet name="' + xmlEsc(n) + '" sheetId="' + (i + 1) + '" r:id="rId' + (i + 1) + '"/>'; }).join('') + '</sheets></workbook>' });
        files.push({ name: 'xl/_rels/workbook.xml.rels', data: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
            names.map(function (_, i) { return '<Relationship Id="rId' + (i + 1) + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet' + (i + 1) + '.xml"/>'; }).join('') +
            '<Relationship Id="rId' + (names.length + 1) + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>' });
        files.push({ name: 'xl/styles.xml', data: STYLES });
        sheetXml.forEach(function (x, i) { files.push({ name: 'xl/worksheets/sheet' + (i + 1) + '.xml', data: x }); });
        return SM.zipStore(files);
    };

    // ── CSV / TSV / TXT ─────────────────────────────────────────────────────────
    SM.decodeText = function (bytes) {
        var b = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
        try { return new TextDecoder('utf-8', { fatal: true }).decode(b).replace(/^﻿/, ''); }
        catch (e) { return new TextDecoder('windows-1256').decode(b); }
    };

    SM.parseCsv = function (text) {
        text = String(text).replace(/^﻿/, '');
        var sample = text.split(/\r?\n/).slice(0, 20).join('\n'), best = ',', bestN = -1;
        [',', ';', '\t', '|'].forEach(function (d) {
            var n = (sample.match(new RegExp(d === '|' ? '\\|' : d, 'g')) || []).length;
            if (n > bestN) { bestN = n; best = d; }
        });
        var rows = [], row = [], cur = '', q = false;
        for (var i = 0; i < text.length; i++) {
            var ch = text[i];
            if (q) {
                if (ch === '"') { if (text[i + 1] === '"') { cur += '"'; i++; } else q = false; } else cur += ch;
            } else if (ch === '"') q = true;
            else if (ch === best) { row.push(cur); cur = ''; }
            else if (ch === '\n' || ch === '\r') {
                if (ch === '\r' && text[i + 1] === '\n') i++;
                row.push(cur); cur = ''; rows.push(row); row = [];
            } else cur += ch;
        }
        if (cur !== '' || row.length) { row.push(cur); rows.push(row); }
        return rows.filter(function (r) { return r.some(function (c) { return String(c).trim() !== ''; }); });
    };

    if (typeof module !== 'undefined' && module.exports) module.exports = SM;
})(typeof window !== 'undefined' ? window : globalThis);
