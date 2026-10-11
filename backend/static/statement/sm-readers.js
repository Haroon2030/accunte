/* مطابق كشوفات الحساب — قراءة الملفات: XLSX/CSV داخليًا بلا مكتبات، وPDF (pdf.js) وصور/ممسوحات (Tesseract.js) تُحمَّل عند الحاجة.
   كل المعالجة داخل المتصفح؛ لا يُرسَل أي ملف إلى أي خادم. */
(function (g) {
    'use strict';
    var SM = g.SM = g.SM || {};

    var LIBS = {
        pdf: { src: 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js', worker: 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js', global: 'pdfjsLib' },
        ocr: { src: 'https://cdnjs.cloudflare.com/ajax/libs/tesseract.js/5.0.5/tesseract.min.js', global: 'Tesseract' },
        sheetjs: { src: 'https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js', global: 'XLSX' }
    };
    var loading = {};

    function loadLib(key) {
        var lib = LIBS[key];
        if (g[lib.global]) return Promise.resolve(g[lib.global]);
        if (loading[key]) return loading[key];
        loading[key] = new Promise(function (resolve, reject) {
            var s = document.createElement('script');
            s.src = lib.src; s.crossOrigin = 'anonymous';
            s.onload = function () { if (key === 'pdf') g.pdfjsLib.GlobalWorkerOptions.workerSrc = lib.worker; resolve(g[lib.global]); };
            s.onerror = function () { delete loading[key]; reject(new Error('تعذّر تحميل مكتبة القراءة (' + key + '). تأكد من اتصال الإنترنت أو استخدم ملف Excel/CSV.')); };
            document.head.appendChild(s);
        });
        return loading[key];
    }
    SM.loadLib = loadLib;

    var EXCEL = /\.(xlsx|xlsm)$/i, LEGACY = /\.(xls|xlsb|ods)$/i, TEXT = /\.(csv|tsv|txt)$/i, PDF = /\.pdf$/i, IMAGE = /\.(jpe?g|png|webp|gif|heic|heif|bmp|tiff?)$/i;
    SM.ACCEPT = '.xlsx,.xlsm,.xls,.xlsb,.ods,.csv,.tsv,.txt,.pdf,.jpg,.jpeg,.png,.webp,.gif,.heic,.bmp,.tif,.tiff,image/*';
    SM.fileKind = function (name) {
        if (EXCEL.test(name)) return 'xlsx';
        if (LEGACY.test(name)) return 'legacy';
        if (TEXT.test(name)) return 'text';
        if (PDF.test(name)) return 'pdf';
        if (IMAGE.test(name)) return 'image';
        return null;
    };

    function readAsBuffer(file) {
        return file.arrayBuffer ? file.arrayBuffer() : new Promise(function (res, rej) {
            var r = new FileReader(); r.onload = function () { res(r.result); }; r.onerror = rej; r.readAsArrayBuffer(file);
        });
    }

    function scoreTable(rows) {
        var hdr = SM.findHeader(rows);
        return (hdr ? 1000 + hdr.score : 0) + Math.min(rows.length, 500);
    }

    function bestTable(sheets, file) {
        var tables = sheets.filter(function (s) { return s.rows && s.rows.length; }).map(function (s) { return { name: s.name, rows: s.rows, preface: [], source: 'excel' }; });
        tables.sort(function (a, b) { return scoreTable(b.rows) - scoreTable(a.rows); });
        return tables;
    }

    // ── Excel / CSV ─────────────────────────────────────────────────────────────
    function readExcel(file) {
        return readAsBuffer(file).then(SM.readXlsx).then(function (sheets) { return { tables: bestTable(sheets, file) }; });
    }
    function readText(file) {
        return readAsBuffer(file).then(function (buf) { return { tables: [{ name: file.name, rows: SM.parseCsv(SM.decodeText(new Uint8Array(buf))), preface: [], source: 'csv' }] }; });
    }
    function readLegacy(file) {
        return Promise.all([loadLib('sheetjs'), readAsBuffer(file)]).then(function (r) {
            var wb = r[0].read(new Uint8Array(r[1]), { type: 'array', cellDates: true });
            var sheets = wb.SheetNames.map(function (n) {
                var rows = r[0].utils.sheet_to_json(wb.Sheets[n], { header: 1, raw: true, defval: '' }).map(function (row) {
                    return row.map(function (v) { return v instanceof Date ? v.toISOString().slice(0, 10) : v; });
                });
                return { name: n, rows: rows };
            });
            return { tables: bestTable(sheets, file) };
        });
    }

    // ── PDF ─────────────────────────────────────────────────────────────────────
    function pdfPageWords(page, viewport) {
        return page.getTextContent().then(function (tc) {
            var words = [];
            tc.items.forEach(function (it) {
                var text = it.str;
                if (!text || !text.trim()) return;
                var tr = it.transform, x = tr[4], yTop = viewport.height - tr[5] - (it.height || Math.abs(tr[3]));
                var h = it.height || Math.abs(tr[3]) || 10, width = it.width || (text.length * h * 0.5);
                var parts = text.split(/(\s+)/), pos = 0, total = Math.max(1, text.length), rtl = /[؀-ۿﭐ-﷿ﹰ-﻿]/.test(text);
                parts.forEach(function (p) {
                    if (p && p.trim()) {
                        // نص عربي: الكلمة الأولى في الترتيب المنطقي هي الأقرب لليمين
                        var a0 = pos / total, a1 = (pos + p.length) / total;
                        words.push({ text: p, x0: x + width * (rtl ? 1 - a1 : a0), x1: x + width * (rtl ? 1 - a0 : a1), y0: yTop, y1: yTop + h });
                    }
                    pos += p.length;
                });
            });
            return words;
        });
    }

    function readPdf(file, opts) {
        var progress = opts.onProgress || function () {};
        return Promise.all([loadLib('pdf'), readAsBuffer(file)]).then(function (r) {
            return r[0].getDocument({ data: new Uint8Array(r[1]) }).promise;
        }).then(function (pdf) {
            var allWords = [], offset = 0, scanned = 0, chain = Promise.resolve();
            for (var p = 1; p <= pdf.numPages; p++) (function (n) {
                chain = chain.then(function () {
                    progress('قراءة الصفحة ' + n + ' من ' + pdf.numPages);
                    return pdf.getPage(n).then(function (page) {
                        var vp = page.getViewport({ scale: 1 });
                        return pdfPageWords(page, vp).then(function (words) {
                            if (words.length >= 12) {
                                words.forEach(function (w) { w.y0 += offset; w.y1 += offset; });
                                allWords = allWords.concat(words);
                                offset += vp.height;
                                return null;
                            }
                            scanned++;                                              // صفحة ممسوحة: OCR
                            var scale = 2.5, big = page.getViewport({ scale: scale }), canvas = document.createElement('canvas');
                            canvas.width = big.width; canvas.height = big.height;
                            return page.render({ canvasContext: canvas.getContext('2d'), viewport: big }).promise.then(function () {
                                return SM.ocrCanvas(canvas, { onProgress: function (t) { progress('الصفحة ' + n + ': ' + t); } });
                            }).then(function (ws) {
                                ws.forEach(function (w) { w.x0 /= scale; w.x1 /= scale; w.y0 = w.y0 / scale + offset; w.y1 = w.y1 / scale + offset; });
                                allWords = allWords.concat(ws);
                                offset += vp.height;
                            });
                        });
                    });
                });
            })(p);
            return chain.then(function () {
                var table = SM.wordsToTable(allWords);
                table.name = file.name; table.source = scanned ? 'pdf-ocr' : 'pdf';
                return { tables: [table], note: scanned ? 'تمت قراءة ' + scanned + ' صفحة ممسوحة بالتعرّف الضوئي (OCR)، راجع الأرقام في خطوة المراجعة' : '' };
            });
        });
    }

    // ── الصور والممسوحات (OCR) ───────────────────────────────────────────────────
    function preprocess(img) {
        var maxSide = 3200, scale = Math.min(2, maxSide / Math.max(img.width, img.height));
        if (scale < 1) scale = maxSide / Math.max(img.width, img.height);
        var canvas = document.createElement('canvas');
        canvas.width = Math.round(img.width * scale); canvas.height = Math.round(img.height * scale);
        var ctx = canvas.getContext('2d');
        ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        var data = ctx.getImageData(0, 0, canvas.width, canvas.height), d = data.data, lo = 255, hi = 0, i;
        for (i = 0; i < d.length; i += 4) {
            var gray = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
            d[i] = d[i + 1] = d[i + 2] = gray;
            if (gray < lo) lo = gray; if (gray > hi) hi = gray;
        }
        var range = Math.max(1, hi - lo);
        for (i = 0; i < d.length; i += 4) { var v = Math.max(0, Math.min(255, (d[i] - lo) * 255 / range)); d[i] = d[i + 1] = d[i + 2] = v; }
        ctx.putImageData(data, 0, 0);
        return canvas;
    }

    function tesseractWords(result) {
        var out = [];
        (result.data.words || []).forEach(function (w) {
            if (w.text && w.text.trim()) out.push({ text: w.text.trim(), x0: w.bbox.x0, x1: w.bbox.x1, y0: w.bbox.y0, y1: w.bbox.y1, conf: w.confidence });
        });
        return out;
    }

    /** OCR بمرور عادي (ara+eng) ثم مرور أرقام فقط يُصحِّح كلمات الأرقام والتواريخ. */
    SM.ocrCanvas = function (canvas, opts) {
        var progress = (opts && opts.onProgress) || function () {}, workers = [];
        function cleanup() { workers.forEach(function (w) { try { w.terminate(); } catch (e) { /* لا شيء */ } }); }
        return loadLib('ocr').then(function (T) {
            progress('تحميل محرك التعرّف الضوئي...');
            return T.createWorker('ara+eng', 1, { logger: function (m) { if (m.status === 'recognizing text') progress('التعرّف الضوئي ' + Math.round(m.progress * 100) + '%'); } });
        }).then(function (worker) {
            workers.push(worker);
            return worker.recognize(canvas).then(function (res) { return { worker: worker, words: tesseractWords(res) }; });
        }).then(function (first) {
            progress('مرور الأرقام والتواريخ...');
            return g.Tesseract.createWorker('eng', 1, {}).then(function (w2) {
                workers.push(w2);
                return w2.setParameters({ tessedit_char_whitelist: '0123456789.,-()/' }).then(function () { return w2.recognize(canvas); });
            }).then(function (res2) {
                var digitWords = tesseractWords(res2);
                first.words.forEach(function (w) {
                    if (!/\d/.test(w.text)) return;
                    var best = null, bestOverlap = 0;
                    digitWords.forEach(function (d) {
                        var ox = Math.min(w.x1, d.x1) - Math.max(w.x0, d.x0), oy = Math.min(w.y1, d.y1) - Math.max(w.y0, d.y0);
                        if (ox > 0 && oy > 0 && ox / Math.max(1, Math.max(w.x1 - w.x0, d.x1 - d.x0)) > 0.6 && ox * oy > bestOverlap) { bestOverlap = ox * oy; best = d; }
                    });
                    if (best && best.text.length >= w.text.replace(/[^\d.,\-()\/]/g, '').length) { w.text = best.text; w.conf = Math.max(w.conf || 0, best.conf || 0); }
                });
                return first.words;
            });
        }).then(function (words) { cleanup(); return words; }, function (e) { cleanup(); throw e; });
    };

    function readImage(file, opts) {
        var progress = opts.onProgress || function () {};
        if (/\.(heic|heif)$/i.test(file.name)) {
            return createImageBitmap(file).then(null, function () { throw new Error('صيغة HEIC غير مدعومة في هذا المتصفح. حوّل الصورة إلى JPG أو PNG ثم أعد الرفع.'); }).then(function (bmp) { return ocrBitmap(bmp, file, progress); });
        }
        return createImageBitmap(file).then(function (bmp) { return ocrBitmap(bmp, file, progress); }, function () { throw new Error('تعذّر فتح الصورة. جرّب تحويلها إلى JPG أو PNG.'); });
    }
    function ocrBitmap(bmp, file, progress) {
        var canvas = preprocess(bmp);
        return SM.ocrCanvas(canvas, { onProgress: progress }).then(function (words) {
            var table = SM.wordsToTable(words);
            table.name = file.name; table.source = 'image-ocr';
            return { tables: [table], note: 'قُرئت الصورة بالتعرّف الضوئي (OCR)؛ الأسطر منخفضة الثقة مظلَّلة بالأحمر في المراجعة، وفحص الرصيد الجاري يكشف أخطاء القراءة' };
        });
    }

    /** نقطة الدخول: يُرجع Promise<{name, tables:[{name,rows,preface,confs?,source}], note?}> */
    SM.readFile = function (file, opts) {
        opts = opts || {};
        var kind = SM.fileKind(file.name);
        if (!kind && /^image\//.test(file.type || '')) kind = 'image';
        if (!kind) return Promise.reject(new Error('نوع الملف غير مدعوم: ' + file.name));
        var p = kind === 'xlsx' ? readExcel(file) : kind === 'text' ? readText(file) : kind === 'legacy' ? readLegacy(file) : kind === 'pdf' ? readPdf(file, opts) : readImage(file, opts);
        return p.then(function (res) {
            res.name = file.name;
            if (!res.tables.length || res.tables.every(function (t) { return !t.rows.length; })) throw new Error('لم تُقرأ أي بيانات من الملف ' + file.name + '. إن كان ممسوحًا بجودة منخفضة فجرّب نسخة أوضح.');
            return res;
        });
    };

    if (typeof module !== 'undefined' && module.exports) module.exports = SM;
})(typeof window !== 'undefined' ? window : globalThis);
