const test = require('node:test');
const assert = require('node:assert/strict');
const SM = require('../sm-core.js');
require('../sm-xlsx.js');
require('../sm-ledger.js');
require('../sm-engine.js');

const c = (n) => Math.round(n * 100);
const H = ['التاريخ', 'رقم المستند', 'البيان', 'مدين', 'دائن', 'الرصيد'];

// يبني جدول دفاترنا (الدائن يزيد المستحق) برصيد جارٍ صحيح
function ours(open, items) {
    let bal = open; const rows = [H, ['', '', 'رصيد افتتاحي', '', open, open]];
    for (const [d, ref, desc, inc, dec] of items) { bal += (inc || 0) - (dec || 0); rows.push([d, ref, desc, dec || '', inc || '', bal]); }
    return { rows };
}
// كشف المورد (المدين يزيد المستحق له)
function supp(open, items) {
    let bal = open; const rows = [H, ['', '', 'رصيد افتتاحي', open, '', open]];
    for (const [d, ref, desc, inc, dec] of items) { bal += (inc || 0) - (dec || 0); rows.push([d, ref, desc, inc || '', dec || '', bal]); }
    return { rows };
}
const run = (o, s, opts) => SM.reconcile(SM.parseSide(o, { sideDefault: false }), SM.parseSide(s, { sideDefault: true }), opts);

const BASE = [
    ['2026-01-05', 'INV-1001', 'فاتورة مشتريات', 10000, 0],
    ['2026-01-12', 'PAY-77', 'سداد دفعة بنكية', 0, 4000],
    ['2026-01-20', 'INV-1002', 'فاتورة مشتريات', 2500.5, 0]
];

test('تطابق كامل', () => {
    const r = run(ours(5000, BASE), supp(5000, BASE));
    assert.equal(r.status, 'matched');
    assert.equal(r.matches.length, 3);
    assert.equal(r.bridge.gross, 0);
    assert.equal(r.bridge.unexplained, 0);
    assert.equal(r.supplierOnly.length + r.oursOnly.length + r.diffs.length, 0);
    assert.ok(r.matches.every((m) => m.pass === 'ref' && m.level === 1));
});

test('مطابقة بالمبلغ والتاريخ حين تختلف المراجع أو تغيب', () => {
    const sItems = BASE.map(([d, , desc, i, dd]) => [d, '', desc, i, dd]);
    const r = run(ours(5000, BASE), supp(5000, sItems));
    assert.equal(r.matches.length, 3);
    assert.ok(r.matches.every((m) => m.pass === 'amount-date'));
    assert.equal(r.status, 'matched');
});

test('دفعة في الطريق + فاتورة بضاعة في الطريق + إشعار غير مقبول: الجسر يغلق', () => {
    const o = ours(5000, [...BASE, ['2026-01-28', 'PAY-80', 'سداد دفعة بنكية', 0, 3000], ['2026-01-26', 'CN-5', 'إشعار دائن مرتجع', 0, 700]]);
    const s = supp(5000, [...BASE, ['2026-01-27', 'INV-1003', 'فاتورة مشتريات', 1500, 0]]);
    const r = run(o, s);
    const cats = (arr) => arr.map((x) => x.cat).sort();
    assert.deepEqual(cats(r.oursOnly), ['payment-in-transit', 'unaccepted-note']);
    assert.deepEqual(cats(r.supplierOnly), ['goods-in-transit']);
    assert.equal(r.status, 'explained');
    // رصيدنا = 5000+12500.5-4000-3000-700 = 9800.5 ، رصيد المورد = 5000+12500.5-4000+1500 = 15000.5
    assert.equal(r.bridge.gross, c(15000.5 - 9800.5));
    assert.equal(r.bridge.supplierOnly, c(1500));
    assert.equal(r.bridge.oursOnly, c(3700));
    assert.equal(r.bridge.unexplained, 0);
    assert.equal(r.bridge.expected, r.bridge.supplierClosing);
    assert.ok(r.actions[0].sev >= r.actions[r.actions.length - 1].sev);
});

test('فرق مبلغ لنفس المرجع: ضريبة، تبديل أرقام، فاصلة عشرية، تقريب', () => {
    const o = ours(0, [['2026-01-05', 'A1', 'فاتورة', 1000, 0], ['2026-01-06', 'A2', 'فاتورة', 1234, 0], ['2026-01-07', 'A3', 'فاتورة', 50, 0], ['2026-01-08', 'A4', 'فاتورة', 200, 0]]);
    const s = supp(0, [['2026-01-05', 'A1', 'فاتورة', 1150, 0], ['2026-01-06', 'A2', 'فاتورة', 1324, 0], ['2026-01-07', 'A3', 'فاتورة', 500, 0], ['2026-01-08', 'A4', 'فاتورة', 200.4, 0]]);
    const r = run(o, s);
    const byRef = Object.fromEntries(r.diffs.map((d) => [d.a.ref, d]));
    assert.equal(byRef.A1.reason, 'vat-excl');
    assert.equal(byRef.A2.reason, 'transposition');
    assert.equal(byRef.A3.reason, 'decimal');
    assert.equal(byRef.A4.reason, 'rounding');
    assert.equal(r.bridge.amountDiffs, c(150 + 90 + 450 + 0.4));
    assert.equal(r.bridge.unexplained, 0);
    assert.equal(r.status, 'explained');
});

test('انعكاس الإشارة: فاتورة عندنا كإشعار عندهم', () => {
    const o = ours(0, [['2026-01-05', 'X1', 'فاتورة', 500, 0]]);
    const s = supp(0, [['2026-01-05', 'X1', 'مرتجع', 0, 500]]);
    const r = run(o, s);
    assert.equal(r.flips.length, 1);
    assert.equal(r.flips[0].diff, -c(1000));
    assert.equal(r.bridge.unexplained, 0);
});

test('تجميع: فاتورة واحدة عندنا = سطران عند المورد (نفس المرجع)', () => {
    const o = ours(0, [['2026-01-05', 'G1', 'فاتورة', 1000, 0]]);
    const s = supp(0, [['2026-01-05', 'G1', 'فاتورة جزء 1', 600, 0], ['2026-01-05', 'G1', 'فاتورة جزء 2', 400, 0]]);
    const r = run(o, s);
    assert.equal(r.groups.length, 1);
    assert.equal(r.groups[0].pass, 'ref-group');
    assert.equal(r.groups[0].many.length, 2);
    assert.equal(r.status, 'matched');
});

test('تجميع بمجموع الجزئيات: دفعة واحدة تسدّد ثلاث فواتير', () => {
    const o = ours(0, [['2026-01-02', 'I1', 'فاتورة', 100, 0], ['2026-01-03', 'I2', 'فاتورة', 250, 0], ['2026-01-04', 'I3', 'فاتورة', 150, 0], ['2026-01-20', 'P1', 'سداد', 0, 500]]);
    const s = supp(0, [['2026-01-02', 'I1', 'فاتورة', 100, 0], ['2026-01-03', 'I2', 'فاتورة', 250, 0], ['2026-01-04', 'I3', 'فاتورة', 150, 0],
        ['2026-01-20', 'R1', 'دفعة', 0, 100], ['2026-01-20', 'R2', 'دفعة', 0, 250], ['2026-01-20', 'R3', 'دفعة', 0, 150]]);
    const r = run(o, s);
    assert.equal(r.groups.length, 1);
    assert.equal(r.groups[0].side, 'ours');
    assert.equal(r.groups[0].many.length, 3);
    assert.equal(r.bridge.unexplained, 0);
});

test('قيد مكرر عند المورد', () => {
    const o = ours(0, [['2026-01-05', 'D1', 'فاتورة', 300, 0]]);
    const s = supp(0, [['2026-01-05', 'D1', 'فاتورة', 300, 0], ['2026-01-05', 'D1', 'فاتورة', 300, 0]]);
    const r = run(o, s);
    assert.equal(r.supplierOnly.length, 1);
    assert.equal(r.supplierOnly[0].cat, 'duplicate');
    assert.equal(r.bridge.supplierOnly, c(300));
});

test('انعكاس داخلي (إلغاء قيد) عند المورد لا يظهر فرقًا', () => {
    const o = ours(0, [['2026-01-05', 'K1', 'فاتورة', 100, 0]]);
    const s = supp(0, [['2026-01-05', 'K1', 'فاتورة', 100, 0], ['2026-01-06', 'K9', 'فاتورة خاطئة', 80, 0], ['2026-01-07', 'K9', 'إلغاء قيد', 0, 80]]);
    const r = run(o, s);
    assert.equal(r.reversals.supplier.length, 1);
    assert.equal(r.supplierOnly.length, 0);
    assert.equal(r.status, 'matched');
});

test('تأخير توقيت أبعد من النافذة يُعلَّم ولا يُعد فرقًا', () => {
    const o = ours(0, [['2026-01-02', 'T1', 'سداد', 0, 800]]);
    const s = supp(0, [['2026-02-10', 'Z9', 'دفعة', 0, 800]]);
    const r = run(o, s, { windowDays: 7, timingDays: 60 });
    assert.equal(r.matches.length, 1);
    assert.equal(r.matches[0].timing, true);
    assert.equal(r.kpis.timing, 1);
});

test('فرق الرصيد الافتتاحي يظهر كبند مستقل', () => {
    const r = run(ours(5000, BASE), supp(4000, BASE));
    assert.equal(r.bridge.openingDiff, -c(1000));
    assert.equal(r.status, 'explained');
    assert.equal(r.bridge.unexplained, 0);
});

test('فصل الفترات: قيد بعد نهاية فترة الطرف الآخر', () => {
    const o = ours(0, [['2026-01-05', 'M1', 'فاتورة', 100, 0], ['2026-02-05', 'M2', 'فاتورة', 40, 0]]);
    const s = supp(0, [['2026-01-05', 'M1', 'فاتورة', 100, 0]]);
    const r = run(o, s);
    assert.equal(r.oursOnly[0].cat, 'cutoff');
    assert.equal(r.oursOnly[0].kind, 'timing');
});

test('خطأ حسابي داخل الكشف يُحسب فرقًا غير مفسَّر', () => {
    const o = ours(0, BASE);
    const sRows = supp(0, BASE);
    sRows.rows[sRows.rows.length - 1][5] = 99999;                 // رصيد مطبوع خاطئ في آخر سطر
    const r = run(o, sRows);
    assert.notEqual(r.bridge.unexplained, 0);
    assert.equal(r.status, 'unexplained');
    assert.ok(r.supplier.warnings.some((w) => w.code === 'closing-mismatch'));
});

test('أداء: ألف حركة بالجانبين خلال زمن معقول', () => {
    const items = [];
    for (let i = 0; i < 1000; i++) items.push([`2026-0${1 + (i % 9)}-${String(1 + (i % 27)).padStart(2, '0')}`, `R${i}`, 'فاتورة مشتريات', 100 + i, 0]);
    const t0 = Date.now();
    const r = run(ours(0, items), supp(0, items));
    assert.equal(r.matches.length, 1000);
    assert.ok(Date.now() - t0 < 4000, 'تجاوز زمن المطابقة');
});
