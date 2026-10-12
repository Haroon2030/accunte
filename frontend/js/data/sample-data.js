'use strict';

/* ---------- sample data (replace with Django API responses) ---------- */
let seq = 0;
const uid = function () { seq += 1; return 'm' + seq; };
const ago = function (d, hr) { return new Date(NOW.getTime() - ((d * 24) + (hr || 0)) * 3600 * 1000); };
const M = function (from, text, at, files) { return { id: uid(), from: from, text: text, at: at, files: files || [] }; };

function mk(o) {
  const created = ago(o.d, o.h);
  const done = o.stage === 4;
  const end = done ? ago(o.doneD) : NOW;
  const steps = done ? 4 : o.stage + 1;
  const reached = [];
  for (let i = 0; i <= o.stage; i++) reached.push(new Date(created.getTime() + (end - created) * i / steps));
  if (done) reached[4] = end;
  let messages = o.messages || [];
  if (o.stage >= 3) messages = [{ id: uid(), from: 'system', text: ADVANCE[2].note, at: reached[3], files: [] }].concat(messages);
  if (done) messages = messages.concat([{ id: uid(), from: 'system', text: ADVANCE[3].note, at: reached[4], files: [] }]);
  return {
    id: 'MT-2610-' + o.n, supplier: o.supplier, period: o.period, stage: o.stage, created: created,
    due: new Date(created.getTime() + SLA_DAYS * DAY), reached: reached, matcher: o.matcher || null, diff: o.diff == null ? null : o.diff,
    statement: { name: 'كشف-حساب-' + o.file + '.xlsx', size: o.size || 184320 }, notes: o.notes || '', messages: messages
  };
}
const SUP = ME.supplier;
const RAW = [
  { n: '0153', supplier: SUP, period: 'الربع الثالث 2026', file: 'Q3-2026', stage: 1, d: 0, h: 2 },
  { n: '0151', supplier: SUP, period: 'سبتمبر 2026', file: 'سبتمبر-2026', stage: 3, d: 4, matcher: 'خالد العتيبي', diff: 4320, messages: [
    M('matcher', 'السلام عليكم، عند المطابقة ظهر فرق 4,320 ر.س في الفاتورة INV-88213. الخصم التجاري المتفق عليه غير مسجل في كشفكم.', ago(0, 20)),
    M('supplier', 'وعليكم السلام. الخصم صدر بإشعار دائن بتاريخ 14 سبتمبر، أرفقته مع صورة من الفاتورة.', ago(0, 15), [{ name: 'إشعار-دائن-88213.pdf', size: 96256 }, { name: 'INV-88213.jpg', size: 412000 }]),
    M('matcher', 'وصلني الإشعار، شكراً. لكنه يغطي 3,100 ر.س فقط. هل هناك إشعار ثانٍ للمبلغ المتبقي 1,220 ر.س؟', ago(0, 2))
  ] },
  { n: '0148', supplier: SUP, period: 'أغسطس 2026', file: 'أغسطس-2026', stage: 4, d: 9, doneD: 5, matcher: 'هدى الشمري', diff: 0, messages: [
    M('matcher', 'تمت المطابقة وأرصدتنا متطابقة. هل تؤكدون الإغلاق؟', ago(5, 20)),
    M('supplier', 'نعم، نؤكد الإغلاق. شكراً لكم.', ago(5, 10))
  ] },
  { n: '0150', supplier: 'مؤسسة الصفوة للمنظفات', period: 'سبتمبر 2026', file: 'سبتمبر-2026', stage: 1, d: 1 },
  { n: '0146', supplier: 'مصنع الفجر للتغليف', period: 'سبتمبر 2026', file: 'سبتمبر-2026', stage: 2, d: 2, matcher: 'ريم الحربي', diff: 12780 },
  { n: '0144', supplier: 'شركة الخليج للعبوات', period: 'سبتمبر 2026', file: 'سبتمبر-2026', stage: 3, d: 3, matcher: 'خالد العتيبي', diff: 2150, messages: [
    M('matcher', 'مرحباً، نحتاج نسخة من أمر الشراء PO-5521. الكمية في الفاتورة تزيد 40 كرتوناً عن المستلم.', ago(0, 10)),
    M('supplier', 'تم، سنرسل أمر الشراء وإذن التسليم اليوم.', ago(0, 4))
  ] },
  { n: '0142', supplier: 'دار الغذاء التجارية', period: 'الربع الثالث 2026', file: 'Q3-2026', stage: 3, d: 8, matcher: 'ريم الحربي', diff: 31900, messages: [
    M('matcher', 'يوجد فرق 31,900 ر.س بسبب 3 فواتير غير مسجلة عندنا. نرجو إرسال أصولها لنراجعها مع المستودع.', ago(1, 12))
  ] },
  { n: '0139', supplier: 'مؤسسة الواحة للمواد الغذائية', period: 'سبتمبر 2026', file: 'سبتمبر-2026', stage: 2, d: 7, matcher: 'هدى الشمري', diff: 8640 },
  { n: '0136', supplier: 'مؤسسة الريان للتجارة', period: 'سبتمبر 2026', file: 'سبتمبر-2026', stage: 4, d: 6, doneD: 3, matcher: 'ريم الحربي', diff: 0 },
  { n: '0133', supplier: 'شركة البيان للأجهزة', period: 'أغسطس 2026', file: 'أغسطس-2026', stage: 4, d: 20, doneD: 15, matcher: 'خالد العتيبي', diff: 0 },
  { n: '0131', supplier: SUP, period: 'سبتمبر 2026', file: 'سبتمبر-2026', stage: 1, d: 2 },
  { n: '0130', supplier: 'مصنع الفجر للتغليف', period: 'أغسطس 2026', file: 'أغسطس-2026', stage: 2, d: 3, matcher: 'هدى الشمري', diff: 2230 },
  { n: '0129', supplier: 'شركة الخليج للعبوات', period: 'الربع الثالث 2026', file: 'الربع-الثالث-2026', stage: 3, d: 4, matcher: 'ريم الحربي', diff: 2960 },
  { n: '0128', supplier: 'دار الغذاء التجارية', period: 'يوليو 2026', file: 'يوليو-2026', stage: 4, d: 5, matcher: 'خالد العتيبي', diff: 0, doneD: 1 },
  { n: '0127', supplier: SUP, period: 'سبتمبر 2026', file: 'سبتمبر-2026', stage: 2, d: 6, matcher: 'هدى الشمري', diff: 4420 },
  { n: '0126', supplier: 'مؤسسة الريان للتجارة', period: 'أغسطس 2026', file: 'أغسطس-2026', stage: 3, d: 7, matcher: 'ريم الحربي', diff: 5150 },
  { n: '0125', supplier: 'شركة البيان للأجهزة', period: 'الربع الثالث 2026', file: 'الربع-الثالث-2026', stage: 1, d: 8 },
  { n: '0124', supplier: 'شركة الأفق للمشروبات', period: 'يوليو 2026', file: 'يوليو-2026', stage: 4, d: 9, matcher: 'هدى الشمري', diff: 0, doneD: 1 },
  { n: '0123', supplier: SUP, period: 'سبتمبر 2026', file: 'سبتمبر-2026', stage: 2, d: 10, matcher: 'ريم الحربي', diff: 7340 },
  { n: '0122', supplier: 'شركة المدار للأدوات المنزلية', period: 'أغسطس 2026', file: 'أغسطس-2026', stage: 3, d: 2, matcher: 'خالد العتيبي', diff: 8070 },
  { n: '0121', supplier: 'مؤسسة الصفوة للمنظفات', period: 'الربع الثالث 2026', file: 'الربع-الثالث-2026', stage: 4, d: 3, matcher: 'هدى الشمري', diff: 0, doneD: 0 },
  { n: '0120', supplier: 'مصنع الفجر للتغليف', period: 'يوليو 2026', file: 'يوليو-2026', stage: 1, d: 4 },
  { n: '0119', supplier: SUP, period: 'سبتمبر 2026', file: 'سبتمبر-2026', stage: 2, d: 5, matcher: 'خالد العتيبي', diff: 10260 },
  { n: '0118', supplier: 'دار الغذاء التجارية', period: 'أغسطس 2026', file: 'أغسطس-2026', stage: 3, d: 6, matcher: 'هدى الشمري', diff: 10990 },
  { n: '0117', supplier: 'مؤسسة الواحة للمواد الغذائية', period: 'الربع الثالث 2026', file: 'الربع-الثالث-2026', stage: 4, d: 7, matcher: 'ريم الحربي', diff: 0, doneD: 0 }
];

function mkC(o) {
  const created = ago(o.d, o.h);
  const done = o.stage === 3;
  const end = done ? ago(o.doneD) : NOW;
  const steps = done ? 3 : o.stage + 1;
  const reached = [];
  for (let i = 0; i <= o.stage; i++) reached.push(new Date(created.getTime() + (end - created) * i / steps));
  let messages = [M('supplier', o.body, created, o.files)].concat(o.messages || []);
  if (o.stage >= 2) messages.splice(1, 0, { id: uid(), from: 'system', text: C_ADV[1].note, at: reached[2], files: [] });
  if (done) messages = messages.concat([{ id: uid(), from: 'system', text: C_ADV[2].note, at: reached[3], files: [] }]);
  return { id: 'SH-2610-' + o.n, supplier: o.supplier, category: o.category, subject: o.subject, related: o.related || null, stage: o.stage, created: created, reached: reached, messages: messages };
}
const RAWC = [
  { n: '0009', supplier: SUP, category: 'دفعة غير مستلمة', subject: 'دفعة سبتمبر لم تصل رغم اعتمادها', body: 'اعتمد المحاسب دفعة بمبلغ 48,500 ر.س بتاريخ 20 سبتمبر ولم تصل لحسابنا حتى الآن. نرجو المتابعة.', stage: 2, d: 2, files: [{ name: 'إشعار-اعتماد-الدفعة.pdf', size: 88064 }], messages: [
    M('manager', 'استلمت شكواك وتواصلت مع الخزينة. أحتاج إشعار التحويل البنكي من جهتكم إن وصلكم.', ago(0, 10))
  ] },
  { n: '0008', supplier: 'شركة الخليج للعبوات', category: 'تأخر الرد على الطلبات', subject: 'مضى أسبوع على طلب المطابقة', body: 'قدمنا طلب المطابقة قبل أسبوع ولم يصلنا رد واضح، ونحتاج إغلاق الأرصدة قبل نهاية الشهر.', related: 'MT-2610-0144', stage: 1, d: 0, h: 5 },
  { n: '0006', supplier: 'مؤسسة الريان للتجارة', category: 'أخرى', subject: 'تعدد الجهات التي نتواصل معها', body: 'نحتاج مسؤولاً واحداً نتواصل معه بدل تعدد الجهات في كل مرة.', stage: 3, d: 6, doneD: 4, messages: [
    M('manager', 'تم تحديد مطابق مسؤول عن حسابكم: ريم الحربي. نعتذر عن التأخير.', ago(4, 12))
  ] },
  { n: '0005', supplier: SUP, category: 'تأخر في السداد', subject: 'تأخر اعتماد الدفعة بعد انتهاء المطابقة', body: 'انتهت المطابقة منذ أسبوعين ولم تُجدول الدفعة بعد.', stage: 3, d: 10, doneD: 8, messages: [
    M('manager', 'تم اعتماد الدفعة وجدولتها للأسبوع القادم.', ago(8, 12))
  ] },
  { n: '0010', supplier: 'مصنع الفجر للتغليف', category: 'دفعة غير مستلمة', subject: 'دفعة معلقة منذ أسبوعين', body: 'تفاصيل الشكوى: دفعة معلقة منذ أسبوعين. نرجو المراجعة والإفادة.', stage: 1, d: 3 },
  { n: '0011', supplier: 'دار الغذاء التجارية', category: 'تأخر في السداد', subject: 'استفسار عن موعد الصرف', body: 'تفاصيل الشكوى: استفسار عن موعد الصرف. نرجو المراجعة والإفادة.', stage: 2, d: 4 },
  { n: '0012', supplier: 'مؤسسة الواحة للمواد الغذائية', category: 'تأخر الرد على الطلبات', subject: 'لا رد على طلب المطابقة', body: 'تفاصيل الشكوى: لا رد على طلب المطابقة. نرجو المراجعة والإفادة.', stage: 3, d: 5, doneD: 2 },
  { n: '0013', supplier: 'شركة البيان للأجهزة', category: 'أخرى', subject: 'طلب تغيير جهة التواصل', body: 'تفاصيل الشكوى: طلب تغيير جهة التواصل. نرجو المراجعة والإفادة.', stage: 1, d: 6 },
  { n: '0014', supplier: 'شركة الأفق للمشروبات', category: 'دفعة غير مستلمة', subject: 'تحويل ناقص عن المبلغ المعتمد', body: 'تفاصيل الشكوى: تحويل ناقص عن المبلغ المعتمد. نرجو المراجعة والإفادة.', stage: 3, d: 7, doneD: 1 },
  { n: '0015', supplier: 'مصنع النور للألبان', category: 'تأخر في السداد', subject: 'تأخر جدولة الدفعة', body: 'تفاصيل الشكوى: تأخر جدولة الدفعة. نرجو المراجعة والإفادة.', stage: 2, d: 8 },
  { n: '0016', supplier: 'مؤسسة الصفوة للمنظفات', category: 'أخرى', subject: 'ملاحظة على آلية الطلبات', body: 'تفاصيل الشكوى: ملاحظة على آلية الطلبات. نرجو المراجعة والإفادة.', stage: 3, d: 9, doneD: 0 }
];
