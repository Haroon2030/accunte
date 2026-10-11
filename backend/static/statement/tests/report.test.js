const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const SM = require('../sm-core.js');
require('../sm-xlsx.js');
require('../sm-ledger.js');
require('../sm-engine.js');
require('../sm-report.js');

const H = ['التاريخ', 'رقم المستند', 'البيان', 'مدين', 'دائن', 'الرصيد'];
function ours(open, items) { let bal = open; const rows = [['اسم المورد: شركة الأفق للتوريدات'], H, ['', '', 'رصيد افتتاحي', '', open, open]]; for (const [d, ref, desc, inc, dec] of items) { bal += (inc || 0) - (dec || 0); rows.push([d, ref, desc, dec || '', inc || '', bal]); } return { rows }; }
function supp(open, items) { let bal = open; const rows = [H, ['', '', 'رصيد افتتاحي', open, '', open]]; for (const [d, ref, desc, inc, dec] of items) { bal += (inc || 0) - (dec || 0); rows.push([d, ref, desc, inc || '', dec || '', bal]); } return { rows }; }

const OURS = ours(5000, [['2026-01-05', 'INV-1001', 'فاتورة مشتريات', 10000, 0], ['2026-01-12', 'PAY-77', 'سداد دفعة بنكية', 0, 4000], ['2026-01-26', 'CN-5', 'إشعار دائن مرتجع', 0, 700],
    ['2026-01-28', 'PAY-80', 'سداد دفعة بنكية', 0, 3000], ['2026-01-06', 'A1', 'فاتورة مشتريات', 1000, 0]]);
const SUPP = supp(5000, [['2026-01-05', 'INV-1001', 'فاتورة مشتريات', 10000, 0], ['2026-01-12', 'PAY-77', 'سداد دفعة بنكية', 0, 4000], ['2026-01-27', 'INV-1003', 'فاتورة مشتريات', 1500, 0],
    ['2026-01-06', 'A1', 'فاتورة مشتريات', 1150, 0]]);
const ctx = { company: 'شركة محمد رشيد الرشيد للتجارة' };
const res = SM.reconcile(SM.parseSide(OURS, { sideDefault: false }), SM.parseSide(SUPP, { sideDefault: true }));

test('الملخص النصي يحوي الحالة والجسر وأهم الإجراءات', () => {
    const t = SM.summaryText(res, ctx);
    assert.match(t, /المورد: شركة الأفق للتوريدات/);
    assert.match(t, /الحالة: الفرق مفسَّر/);
    assert.match(t, /أهم الإجراءات/);
    assert.match(t, /1\./);
});

test('الجسر: الأسطر والإجمالي المنتهي بالفرق غير المفسَّر صفر', () => {
    const lines = SM.bridgeLines(res);
    assert.equal(lines[0].key, 'ours');
    assert.equal(lines[lines.length - 1].amount, 0);
    assert.match(SM.bridgeHtml(res), /فرق غير مفسَّر/);
});

test('التقرير: الأقسام والقيود المقترحة بلا ترحيل قبل المستند', () => {
    const html = SM.buildReportHtml(res, ctx);
    for (const s of ['١. الخلاصة', '٢. جسر المطابقة', '٣. تحليل الفرق', '٤. الإجراءات', '٥. قيود تسوية مقترحة', '٦. مؤشرات المخاطر', 'لا يُرحَّل أي قيد قبل']) assert.ok(html.includes(s), s);
    assert.match(html, /دفعة\/شيك في الطريق/);
    assert.match(html, /فرق ضريبة القيمة المضافة/);
    assert.ok(!/<script/i.test(html));
});

test('الخطاب: موجَّه للمورد بجداول الدفعات والبنود وفروق المبالغ والتوقيع', () => {
    const html = SM.buildLetterHtml(res, ctx);
    assert.match(html, /السادة \/ <b>شركة الأفق للتوريدات<\/b>/);
    assert.match(html, /دفعات سُدِّدت من طرفنا/);
    assert.match(html, /إشعارات دائنة/);
    assert.match(html, /بنود في كشفكم لا نجدها/);
    assert.match(html, /فروق في مبالغ/);
    assert.match(html, /class="sign"/);
});

test('المخرجات تهرب النص: لا حقن HTML من البيان', () => {
    const evil = ours(0, [['2026-01-05', 'X<1>', '<img src=x onerror=alert(1)>', 100, 0]]);
    const r = SM.reconcile(SM.parseSide(evil, { sideDefault: false }), SM.parseSide(supp(0, []), { sideDefault: true }));
    for (const html of [SM.buildReportHtml(r, ctx), SM.buildLetterHtml(r, ctx)]) assert.ok(!html.includes('<img'), 'لم يُهرَّب');
});

test('تصدير Excel: عشر أوراق قابلة للقراءة بالقيم الصحيحة', async () => {
    const sheets = SM.buildWorkbook(res, ctx);
    assert.equal(sheets.length, 10);
    const bytes = SM.buildXlsx(sheets);
    const back = await SM.readXlsx(bytes);
    assert.equal(back.length, 10);
    assert.deepEqual(back.map((s) => s.name), ['الملخص', 'الجسر', 'تحتاج إجراء', 'فروق المبالغ', 'عند المورد فقط', 'عندنا فقط', 'مجمّعة', 'متطابقة', 'انعكاسات', 'سلامة الكشف']);
    const bridge = back[1].rows;
    assert.equal(bridge[0][0], 'البند');
    assert.equal(bridge[1][1], res.bridge.oursClosing / 100);
    fs.writeFileSync(process.env.SM_XLSX_OUT || require('node:os').tmpdir() + '/sm-report-test.xlsx', bytes);
});
