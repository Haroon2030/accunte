const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const SM = require('../sm-core.js');
require('../sm-xlsx.js');
require('../sm-ledger.js');
require('../sm-engine.js');
require('../sm-report.js');

const fx = (n) => fs.readFileSync(path.join(__dirname, 'fixtures', n));
const c = (n) => Math.round(n * 100);

async function readBest(name) {
    const sheets = await SM.readXlsx(fx(name));
    return { name, rows: sheets[0].rows, preface: [] };
}

test('ملف Excel حقيقي (openpyxl): تواريخ خلايا، عنوان مدمج، إجمالي، افتتاحي مُسمّى', async () => {
    const side = SM.parseSide(await readBest('fixture_ours.xlsx'), { sideDefault: false });
    assert.equal(side.mapHow, 'header');
    assert.equal(side.party, 'شركة الأفق للتوريدات');
    assert.equal(side.txns.length, 5);
    assert.equal(side.txns[0].date, '2026-01-05');
    assert.equal(side.opening, c(5000));
    assert.equal(side.closingComputed, c(9800.5));
    assert.equal(side.closingPrinted, c(9800.5));
    assert.equal(side.balanceCheck.ok, true);
    assert.equal(side.entries.filter((e) => e.kind === 'total').length, 1);
});

test('كشف مورد حقيقي: تنازلي، تواريخ نصية، افتتاحي في الرأس، عنوان «المبلغ» فوق مدين/دائن', async () => {
    const side = SM.parseSide(await readBest('fixture_supplier.xlsx'), { sideDefault: true });
    assert.equal(side.reversed, true);
    assert.equal(side.opening, c(5000));
    assert.equal(side.openingSource, 'من رأس الكشف');
    assert.equal(side.txns.length, 5);
    assert.equal(side.txns[0].ref, 'INV-1001');
    assert.equal(side.closingComputed, c(16150.5));
    assert.equal(side.balanceCheck.ok, true);
    assert.ok(side.map.balance !== undefined);
});

test('مطابقة الملفين الحقيقيين: النتيجة والجسر', async () => {
    const o = SM.parseSide(await readBest('fixture_ours.xlsx'), { sideDefault: false });
    const s = SM.parseSide(await readBest('fixture_supplier.xlsx'), { sideDefault: true });
    const r = SM.reconcile(o, s);
    assert.equal(r.matches.length, 3);                                   // INV-1001, PAY-77, INV-1002
    assert.equal(r.diffs.length, 0);
    assert.deepEqual(r.oursOnly.map((x) => x.cat).sort(), ['payment-in-transit', 'unaccepted-note']);
    assert.deepEqual(r.supplierOnly.map((x) => x.cat).sort(), ['goods-in-transit', 'invoice-not-in-ours']);
    assert.equal(r.bridge.unexplained, 0);
    assert.equal(r.bridge.gross, s.closingComputed - o.closingComputed);
    assert.equal(r.status, 'explained');
});

test('CSV بترميز windows-1256 وفاصلة عشرية أوروبية', () => {
    const rows = SM.parseCsv(SM.decodeText(new Uint8Array(fx('fixture_cp1256.csv'))));
    const side = SM.parseSide({ rows }, { sideDefault: false });
    assert.equal(side.opening, c(100));
    assert.equal(side.txns.length, 2);
    assert.equal(side.closingComputed, c(130));
    assert.equal(side.txns[0].credit, c(50));
});
