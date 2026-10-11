const test = require('node:test');
const assert = require('node:assert/strict');
const SM = require('../sm-core.js');
require('../sm-xlsx.js');
require('../sm-ledger.js');
require('../sm-table.js');

// يبني صناديق كلمات صفحة RTL: الأعمدة من اليمين: تاريخ، مستند، بيان، مدين، دائن، رصيد
const COLX = { date: 540, ref: 470, desc: 340, debit: 220, credit: 150, bal: 70 };
const H = 12;
function w(text, cx, y, width) {
    width = width || Math.max(20, text.length * 6);
    return { text, x0: cx - width / 2, x1: cx + width / 2, y0: y, y1: y + H, conf: 95 };
}
function page(rows, extra) {
    const words = (extra || []).slice();
    rows.forEach((r, i) => {
        const y = 100 + i * 20;
        r.forEach((cell, k) => {
            if (cell === '' || cell == null) return;
            const key = Object.keys(COLX)[k];
            String(cell).split(' ').forEach((tok, j, arr) => words.push(w(tok, COLX[key] + (arr.length > 1 ? (j - (arr.length - 1) / 2) * 38 * (key === 'desc' ? -1 : -1) : 0), y)));
        });
    });
    return words;
}
const col = (t, label) => t.rows[0].indexOf(label);
const HEADER = ['التاريخ', 'رقم المستند', 'البيان', 'مدين', 'دائن', 'الرصيد'];

test('جدول بترويسة: الأعمدة تُنسب بالمنطقة والمبالغ تؤخذ رقمية فقط', () => {
    const words = page([HEADER,
        ['05/01/2026', 'INV-1001', 'فاتورة مشتريات رقم', '', '10,000.00', '15,000.00'],
        ['12/01/2026', 'PAY-77', 'سداد دفعة', '4,000.00', '', '11,000.00']], [w('كشف حساب مورد', 300, 40), w('الرصيد السابق: 5,000.00', 300, 62, 120)]);
    const t = SM.wordsToTable(words);
    assert.equal(t.how, 'header');
    assert.equal(t.rows.length, 3);
    assert.deepEqual(t.rows[1].map((x) => x), t.rows[1]);
    const side = SM.parseSide(t, { sideDefault: false });
    assert.equal(side.opening, 500000);
    assert.equal(side.txns.length, 2);
    assert.equal(side.txns[0].ref, 'INV-1001');
    assert.equal(side.txns[0].credit, 1000000);
    assert.equal(side.txns[1].debit, 400000);
    assert.equal(side.closingComputed, 1100000);
    assert.equal(side.balanceCheck.ok, true);
});

test('عنوان رئيسي فوق عنوانين فرعيين (المبلغ فوق مدين/دائن) يُهمَل', () => {
    const hdr = [w('التاريخ', COLX.date, 100), w('المستند', COLX.ref, 100), w('البيان', COLX.desc, 100), w('المبلغ', 185, 80, 160), w('مدين', COLX.debit, 100), w('دائن', COLX.credit, 100), w('الرصيد', COLX.bal, 100)];
    const rows = [['05/01/2026', 'A1', 'فاتورة', '', '300.00', '300.00']];
    const words = hdr.slice();
    rows.forEach((r, i) => r.forEach((cell, k) => { if (cell) words.push(w(cell, Object.values(COLX)[k], 130 + i * 20)); }));
    const t = SM.wordsToTable(words);
    assert.equal(t.rows[0].length, 6);                                    // لا عمود «المبلغ» زائد
    assert.equal(t.rows[1][col(t, 'دائن')], '300.00');
});

test('سطر وصف متابع يُدمج في السطر السابق', () => {
    const words = page([HEADER, ['05/01/2026', 'INV-1', 'فاتورة مشتريات', '', '100.00', '100.00']]);
    words.push(w('تكملة الوصف', COLX.desc, 140));
    const t = SM.wordsToTable(words);
    assert.equal(t.rows.length, 2);
    assert.match(t.rows[1][col(t, 'البيان')], /فاتورة/);
    assert.match(t.rows[1][col(t, 'البيان')], /تكملة/);
});

test('حروف متفرقة (حرف لكل كلمة) تُدمج في كلمات', () => {
    const letters = 'مدين'.split('').reverse();                           // بترتيب الصفحة من اليسار لليمين: ن ي د م
    const split = [];
    ['التاريخ', 'البيان', 'دائن', 'الرصيد'].forEach((label, k) => split.push(w(label, [540, 340, 150, 70][k], 100)));
    letters.forEach((ch, i) => split.push({ text: ch, x0: 205 + i * 6, x1: 210 + i * 6, y0: 100, y1: 112 }));
    const lines = SM.linesFromWords(split);
    const texts = lines[0].words.map((x) => x.text);
    assert.ok(texts.includes('مدين'), texts.join('|'));
});

test('ترتيب بصري معكوس يُكتشف ويُصلَّح', () => {
    const rev = (s) => Array.from(s).reverse().join('');
    const words = HEADER.map((h, k) => w(rev(h), Object.values(COLX)[k], 100));
    assert.equal(SM.fixVisualOrder(words), true);
    assert.equal(words[3].text, 'مدين');
});

test('بلا ترويسة: تقسيم مرن (تاريخ/مرجع/وصف/أرقام آخر السطر)', () => {
    const words = [];
    [['05/01/2026', 'INV-1', 'فاتورة', '100.00', '100.00'], ['10/01/2026', 'PAY-1', 'سداد', '40.00', '60.00']].forEach((r, i) => {
        r.forEach((cell, k) => words.push(w(cell, 560 - k * 90, 100 + i * 20)));
    });
    const t = SM.wordsToTable(words);
    assert.equal(t.how, 'loose');
    assert.equal(t.rows.length, 2);
    assert.equal(t.rows[0][0], '05/01/2026');
    assert.deepEqual(t.rows[0].slice(3), ['100.00', '100.00']);
});

test('ثقة OCR تُحمل لكل سطر', () => {
    const words = page([HEADER, ['05/01/2026', 'INV-1', 'فاتورة', '', '100.00', '100.00']]);
    words[words.length - 1].conf = 41;
    const t = SM.wordsToTable(words);
    assert.equal(t.confs[1], 41);
});
