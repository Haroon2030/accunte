const test = require('node:test');
const assert = require('node:assert/strict');
const SM = require('../sm-core.js');
require('../sm-xlsx.js');

test('parseNumber: صيغ المبالغ', () => {
    const cases = [['1,234.56', 1234.56], ['1.234,56', 1234.56], ['(1,500.00)', -1500], ['٣٤٥٫٥٠', 345.5], ['12,50', 12.5],
        ['1,234', 1234], ['100-', -100], ['-45.5', -45.5], ['1 250,75', 1250.75], ['0', 0], ['٠', 0], ['  7 ', 7], ['2,500,000.00', 2500000]];
    for (const [raw, want] of cases) assert.equal(SM.parseNumber(raw), want, raw);
});

test('parseNumber: يرفض النص الذي يحوي أرقامًا فقط', () => {
    for (const raw of ['INV-123', 'قيمة1', 'abc', '12abc', '', null, '--', 'F-2026/55']) assert.equal(SM.parseNumber(raw), null, String(raw));
});

test('parseNumber: Cr/Dr والعملات', () => {
    assert.equal(SM.parseNumberEx('500 Cr').drcr, 'cr');
    assert.equal(SM.parseNumberEx('500 Dr').drcr, 'dr');
    assert.equal(SM.parseNumber('1,250.00 ر.س'), 1250);
    assert.equal(SM.parseNumber('SAR 99.5'), 99.5);
});

test('extractMoney: يلتقط المبلغ من نص حوله', () => {
    assert.equal(SM.extractMoney('فاتورة رقم 123 مبلغ 1,250.75 ر.س'), 1250.75);
    assert.equal(SM.extractMoney(55), 55);
    assert.equal(SM.extractMoney('بدون أرقام'), null);
});

test('parseDate: الصيغ المختلفة', () => {
    assert.equal(SM.parseDate('05/01/2026'), '2026-01-05');
    assert.equal(SM.parseDate('2026-1-5'), '2026-01-05');
    assert.equal(SM.parseDate('5-Jan-26'), '2026-01-05');
    assert.equal(SM.parseDate('١٥ يناير ٢٠٢٦'), '2026-01-15');
    assert.equal(SM.parseDate('Jan 5, 2026'), '2026-01-05');
    assert.equal(SM.parseDate('تاريخ الفاتورة 12/03/2026 م'), '2026-03-12');
    assert.equal(SM.parseDate('01/05/2026', false), '2026-01-05');
    assert.equal(SM.parseDate('13/05/2026', false), '2026-05-13');      // لا يصح شهر 13: يُعكس
    assert.equal(SM.parseDate('31/02/2026'), null);
    assert.equal(SM.parseDate('hello'), null);
    assert.equal(SM.parseDate(46027), '2026-01-05');
});

test('fmt: #,##0.00 بأرقام لاتينية', () => {
    assert.equal(SM.fmt(1234.5), '1,234.50');
    assert.equal(SM.fmt(-1234.5), '-1,234.50');
    assert.equal(SM.fmt(0), '0.00');
    assert.equal(SM.fmt(1234567.891), '1,234,567.89');
    assert.equal(SM.fmt(0, { blankZero: true }), '');
});

test('normAr: يوحّد الحروف والتشكيل', () => {
    assert.equal(SM.normAr('التاریخ'), SM.normAr('التاريخ'));
    assert.equal(SM.normAr('مَدين'), SM.normAr('مدين'));
    assert.equal(SM.normAr('رصيد افتتاحي'), 'رصيد افتتاحي');
    assert.equal(SM.normAr('الرصيــد'), 'الرصيد');
    assert.equal(SM.normAr('٢٠٢٦'), '2026');
});

test('normRef / refDigits', () => {
    assert.equal(SM.normRef('INV-000123'), 'inv000123');
    assert.equal(SM.normRef('000123'), '123');
    assert.deepEqual(SM.refDigits('فاتورة رقم 000456 وسند 78'), ['456']);
});

test('XLSX: كتابة ثم قراءة تعيد نفس البيانات (أرقام ونصوص وعربي)', async () => {
    const rows = [['التاريخ', 'البيان', 'مدين', 'دائن'], ['2026-01-05', 'فاتورة <1> & "اختبار"', 1234.5, ''], ['', 'الإجمالي', 1234.5, 0]];
    const bytes = SM.buildXlsx([{ name: 'كشف: الحساب/1', rows, widths: [14, 40, 14, 14] }, { name: 'ثانية', rows: [['x'], [1]] }]);
    const sheets = await SM.readXlsx(bytes);
    assert.equal(sheets.length, 2);
    assert.equal(sheets[0].name, 'كشف الحساب 1');                // الأحرف الممنوعة في اسم الورقة تُستبدل
    assert.deepEqual(sheets[0].rows[0], rows[0]);
    assert.equal(sheets[0].rows[1][1], 'فاتورة <1> & "اختبار"');
    assert.equal(sheets[0].rows[1][2], 1234.5);
    assert.equal(sheets[1].rows[1][0], 1);
});

test('XLSX: ملف بتاريخ (نمط خلية) وسلسلة مشتركة يُقرأ كما في Excel', async () => {
    // أرشيف مصغّر مبني يدويًا يحاكي ما يكتبه Excel: sharedStrings + styles بنمط تاريخ + خلية تاريخ برقم تسلسلي
    const files = [
        { name: '[Content_Types].xml', data: '<Types/>' },
        { name: 'xl/workbook.xml', data: '<workbook xmlns:r="x"><sheets><sheet name="كشف" sheetId="1" r:id="rId1"/></sheets></workbook>' },
        { name: 'xl/_rels/workbook.xml.rels', data: '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>' },
        { name: 'xl/sharedStrings.xml', data: '<sst><si><t>التاريخ</t></si><si><r><t>مبلغ </t></r><r><t>الفاتورة</t></r></si></sst>' },
        { name: 'xl/styles.xml', data: '<styleSheet><numFmts count="1"><numFmt numFmtId="170" formatCode="dd/mm/yyyy"/></numFmts><cellXfs count="3"><xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="170"/></cellXfs></styleSheet>' },
        { name: 'xl/worksheets/sheet1.xml', data: '<worksheet><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1" t="s"><v>1</v></c></row><row r="3"><c r="A3" s="1"><v>46027</v></c><c r="B3" s="2"><v>46028</v></c><c r="C3"><v>99.5</v></c><c r="D3" t="inlineStr"><is><t>نص</t></is></c></row></sheetData></worksheet>' },
    ];
    const sheets = await SM.readXlsx(SM.zipStore(files));
    const rows = sheets[0].rows;
    assert.deepEqual(rows[0], ['التاريخ', '', 'مبلغ الفاتورة']);
    assert.deepEqual(rows[1], []);
    assert.deepEqual(rows[2], ['2026-01-05', '2026-01-06', 99.5, 'نص']);
});

test('CSV: كشف الفاصل والاقتباس والترميز', () => {
    const rows = SM.parseCsv('التاريخ;البيان;المبلغ\n05/01/2026;"فاتورة; خاصة";1.234,50\n\n06/01/2026;دفعة;"1,000"');
    assert.equal(rows.length, 3);
    assert.deepEqual(rows[1], ['05/01/2026', 'فاتورة; خاصة', '1.234,50']);
    assert.deepEqual(SM.parseCsv('a\tb\n1\t2'), [['a', 'b'], ['1', '2']]);
    const bytes = new Uint8Array([0xc7, 0xe1, 0xca, 0xc7, 0xd1, 0xed, 0xce]);    // «التاريخ» بترميز windows-1256
    assert.equal(SM.decodeText(bytes), 'التاريخ');
    assert.equal(SM.decodeText(new TextEncoder().encode('﻿مرحبا')), 'مرحبا');
});

test('ZIP: قيمة CRC32 المعروفة', () => {
    assert.equal(SM.crc32(new TextEncoder().encode('123456789')), 0xcbf43926);
});
