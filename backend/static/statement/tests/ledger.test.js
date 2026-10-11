const test = require('node:test');
const assert = require('node:assert/strict');
const SM = require('../sm-core.js');
require('../sm-xlsx.js');
require('../sm-ledger.js');

const c = (n) => Math.round(n * 100);

// دفاترنا: حساب المورد (الدائن يزيد المستحق له)
const OURS = [
    ['شركة محمد رشيد الرشيد للتجارة'],
    ['كشف حساب مورد'],
    ['اسم المورد: شركة الأفق للتوريدات'],
    [],
    ['التاريخ', 'رقم المستند', 'البيان', 'مدين', 'دائن', 'الرصيد'],
    ['', '', 'رصيد افتتاحي', '', 5000, 5000],
    ['2026-01-05', 'INV-1001', 'فاتورة مشتريات', '', 10000, 15000],
    ['2026-01-12', 'PAY-77', 'سداد دفعة بنكية', 4000, '', 11000],
    ['2026-01-20', 'INV-1002', 'فاتورة مشتريات', '', 2500.5, 13500.5],
    ['2026-01-25', 'CN-9', 'اشعار دائن مرتجع', 500.5, '', 13000],
    ['', '', 'الإجمالي', 4500.5, 12500.5, 13000]
];

test('دفاترنا: أعمدة بالترويسة، افتتاحي مُسمّى، إجمالي مستبعد، تكامل الرصيد', () => {
    const side = SM.parseSide({ rows: OURS }, { sideDefault: false });
    assert.equal(side.mapHow, 'header');
    assert.equal(side.party, 'شركة الأفق للتوريدات');
    assert.equal(side.opening, c(5000));
    assert.match(side.openingSource, /رصيد افتتاحي/);
    assert.equal(side.txns.length, 4);
    assert.equal(side.entries.filter((e) => e.kind === 'total').length, 1);
    assert.equal(side.closingComputed, c(13000));
    assert.equal(side.closingPrinted, c(13000));
    assert.equal(side.balanceCheck.ok, true);
    assert.equal(side.orient.debitIncreases, false);          // الفواتير في الدائن
    assert.deepEqual(side.txns.map((t) => t.m), [c(10000), -c(4000), c(2500.5), -c(500.5)]);
    assert.deepEqual(side.period, { from: '2026-01-05', to: '2026-01-25' });
});

// كشف المورد: الفواتير مدين (منظوره)، تنازلي، بلا سطر افتتاحي مُسمّى
const SUPPLIER_DESC = [
    ['Date', 'Doc No', 'Description', 'Debit', 'Credit', 'Balance'],
    ['25/01/2026', 'CN-9', 'Credit note return', '', 500.5, 13000],
    ['20/01/2026', 'INV-1002', 'Invoice 1002', 2500.5, '', 13500.5],
    ['12/01/2026', 'PAY-77', 'Payment received transfer', '', 4000, 11000],
    ['05/01/2026', 'INV-1001', 'Invoice 1001', 10000, '', 15000]
];

test('كشف المورد التنازلي: يُعاد ترتيبه والافتتاحي يُشتق من رصيد أول حركة', () => {
    const side = SM.parseSide({ rows: SUPPLIER_DESC }, { sideDefault: true });
    assert.equal(side.reversed, true);
    assert.equal(side.orient.debitIncreases, true);
    assert.equal(side.txns[0].ref, 'INV-1001');
    assert.equal(side.opening, c(5000));
    assert.equal(side.openingSource, 'محسوب من رصيد أول حركة');
    assert.equal(side.closingComputed, c(13000));
    assert.equal(side.balanceCheck.ok, true);
});

test('افتتاحي في رأس الكشف خارج الجدول', () => {
    const rows = [['الرصيد السابق: 5,000.00'], ['التاريخ', 'المرجع', 'البيان', 'مدين', 'دائن'],
        ['2026-01-05', 'A1', 'فاتورة', '', 100], ['2026-01-06', 'A2', 'فاتورة', '', 50]];
    const side = SM.parseSide({ rows }, { sideDefault: false });
    assert.equal(side.opening, c(5000));
    assert.equal(side.openingSource, 'من رأس الكشف');
    assert.equal(side.closingComputed, c(5150));
});

test('افتتاحي بلا أي تسمية: سطر أول برصيد فقط', () => {
    const rows = [['التاريخ', 'المرجع', 'البيان', 'مدين', 'دائن', 'الرصيد'],
        ['', '', '', '', '', 1200], ['2026-02-01', 'F1', 'فاتورة', '', 300, 1500], ['2026-02-03', 'P1', 'دفعة', 200, '', 1300]];
    const side = SM.parseSide({ rows }, { sideDefault: false });
    assert.equal(side.opening, c(1200));
    assert.equal(side.closingComputed, c(1300));
    assert.equal(side.txns.length, 2);
});

test('كلمات افتتاحي متنوعة وسطر مرحَّل مكرر في أعلى صفحة', () => {
    for (const label of ['رصيد مدور', 'الرصيد المنقول من الكشف السابق', 'B/F', 'Brought forward', 'ما قبله', 'رصيد أول المدة', 'Opening balance']) {
        const rows = [['التاريخ', 'المرجع', 'البيان', 'مدين', 'دائن', 'الرصيد'], ['', '', label, '', 700, 700], ['2026-02-01', 'F1', 'فاتورة', '', 300, 1000]];
        const side = SM.parseSide({ rows }, { sideDefault: false });
        assert.equal(side.opening, c(700), label);
        assert.equal(side.txns.length, 1, label);
    }
    const rows = [['التاريخ', 'المرجع', 'البيان', 'مدين', 'دائن', 'الرصيد'], ['', '', 'رصيد افتتاحي', '', 100, 100],
        ['2026-02-01', 'F1', 'فاتورة', '', 50, 150], ['', '', 'مرحل لصفحة تالية', '', '', 150], ['', '', 'منقول من الصفحة السابقة', '', '', 150],
        ['2026-02-02', 'F2', 'فاتورة', '', 25, 175]];
    const side = SM.parseSide({ rows }, { sideDefault: false });
    assert.equal(side.txns.length, 2);
    assert.equal(side.closingComputed, c(175));
    assert.equal(side.entries.filter((e) => e.kind === 'carry').length, 2);
});

test('رأسان متراكبان (المبلغ فوق مدين/دائن) وعمودا رصيد', () => {
    const rows = [['', '', '', 'المبلغ', 'المبلغ', ''], ['التاريخ', 'رقم السند', 'البيان', 'مدين', 'دائن', 'الرصيد'],
        ['2026-03-01', 'S1', 'فاتورة', '', 80, 80], ['2026-03-02', 'S2', 'سداد', 30, '', 50]];
    const side = SM.parseSide({ rows }, { sideDefault: false });
    assert.deepEqual(Object.keys(side.map).sort(), ['balance', 'credit', 'date', 'debit', 'desc', 'ref'].sort());
    assert.equal(side.closingComputed, c(50));
});

test('عمود واحد بإشارة (المبلغ) واتجاه من الكلمات', () => {
    const rows = [['Date', 'Ref', 'Description', 'Amount'], ['2026-03-01', 'I1', 'Invoice', 100], ['2026-03-05', 'P1', 'Payment', -40]];
    const side = SM.parseSide({ rows }, { sideDefault: true });
    assert.equal(side.map.amount, 3);
    assert.equal(side.closingComputed, c(60));
});

test('بلا ترويسة: استنتاج الأعمدة من المحتوى', () => {
    const rows = [['05/01/2026', 'INV-1', 'فاتورة مشتريات', '', 100, 100], ['10/01/2026', 'PAY-1', 'سداد', 40, '', 60], ['15/01/2026', 'INV-2', 'فاتورة مشتريات', '', 25, 85]];
    const side = SM.parseSide({ rows }, { sideDefault: false });
    assert.equal(side.mapHow, 'inferred');
    assert.equal(side.map.date, 0);
    assert.equal(side.map.balance, 5);
    assert.equal(side.txns.length, 3);
    assert.equal(side.closingComputed, c(85));
    assert.equal(side.balanceCheck.ok, true);
});

test('إجماليات بلا عنوان تُستبعد', () => {
    const rows = [['التاريخ', 'المرجع', 'البيان', 'مدين', 'دائن'], ['2026-01-01', 'A', 'فاتورة', '', 100], ['2026-01-02', 'B', 'فاتورة', '', 50],
        ['2026-01-03', 'C', 'سداد', 30, ''], ['', '', '', 30, 150]];
    const side = SM.parseSide({ rows }, { sideDefault: false });
    assert.equal(side.txns.length, 3);
    assert.equal(side.closingComputed, c(120));
});

test('تكامل الرصيد: يكتشف سطرًا خاطئ الرصيد ويقترح الصحيح', () => {
    const rows = [['التاريخ', 'المرجع', 'البيان', 'مدين', 'دائن', 'الرصيد'], ['', '', 'رصيد افتتاحي', '', 100, 100],
        ['2026-01-01', 'A', 'فاتورة', '', 50, 150], ['2026-01-02', 'B', 'فاتورة', '', 40, 999], ['2026-01-03', 'C', 'سداد', 20, '', 170]];
    const side = SM.parseSide({ rows }, { sideDefault: false });
    const bad = side.txns.filter((t) => t.flags.includes('balance'));
    assert.equal(bad.length, 1);
    assert.equal(bad[0].ref, 'B');
    assert.equal(bad[0].balExpected, c(190));
    assert.equal(side.balanceCheck.ok, false);
    assert.ok(side.warnings.some((w) => w.code === 'balance-chain'));
});

test('تعارض الافتتاحي مع رصيد أول حركة: تحذير مع القيمة المتسقة', () => {
    const rows = [['التاريخ', 'المرجع', 'البيان', 'مدين', 'دائن', 'الرصيد'], ['', '', 'رصيد افتتاحي', '', 100, 100], ['2026-01-01', 'A', 'فاتورة', '', 50, 250]];
    const side = SM.parseSide({ rows }, { sideDefault: false });
    const w = side.warnings.find((x) => x.code === 'opening-conflict');
    assert.ok(w);
    assert.equal(w.suggest, c(200));
});

test('رصيد افتتاحي يدوي يتقدّم على كل شيء', () => {
    const side = SM.parseSide({ rows: OURS }, { sideDefault: false, openingOverride: c(1) });
    assert.equal(side.opening, c(1));
    assert.match(side.openingSource, /يدويًا/);
});

test('تشخيص محدد عند غياب الحركات', () => {
    const side = SM.parseSide({ rows: [['التاريخ', 'البيان'], ['2026-01-01', 'x']] }, {});
    assert.ok(side.txns.length === 0);
    assert.ok(side.diagnosis);
    assert.equal(SM.parseSide({ rows: [] }, {}).diagnosis, 'لم تُقرأ أي بيانات من الملف');
});

test('أرصدة Dr/Cr: الأقلية تُقلب', () => {
    const rows = [['التاريخ', 'المرجع', 'البيان', 'مدين', 'دائن', 'الرصيد'], ['', '', 'رصيد افتتاحي', '', 100, '100 Cr'],
        ['2026-01-01', 'A', 'فاتورة', '', 50, '150 Cr'], ['2026-01-02', 'B', 'سداد', 200, '', '50 Dr']];
    const side = SM.parseSide({ rows }, { sideDefault: false });
    assert.equal(side.closingComputed, c(-50));
    assert.equal(side.balanceCheck.ok, true);
});

test('افتتاحي بوصف ناقص (OCR): «رصيد» وحدها أو سطر بلا تاريخ ومرجع', () => {
    for (const label of ['رصيد', '', 'ل ا']) {
        const rows = [['التاريخ', 'المرجع', 'البيان', 'مدين', 'دائن', 'الرصيد'], ['', '', label, '', 100, 100], ['2026-02-01', 'F1', 'فاتورة', '', 50, 150]];
        const side = SM.parseSide({ rows }, { sideDefault: false });
        assert.equal(side.opening, c(100), JSON.stringify(label));
        assert.equal(side.txns.length, 1, JSON.stringify(label));
    }
    const rows = [['التاريخ', 'المرجع', 'البيان', 'مدين', 'دائن', 'الرصيد'], ['', '', 'دفعة مقدمة', 40, '', -40], ['2026-02-01', 'F1', 'فاتورة', '', 50, 10]];
    assert.equal(SM.parseSide({ rows }, { sideDefault: false }).txns.length, 2);          // كلمات سداد: حركة لا افتتاحي
});
