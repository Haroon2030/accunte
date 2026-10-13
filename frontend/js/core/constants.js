'use strict';

/* ---------- domain constants ---------- */
const DAY = 864e5;
const NOW = new Date();
const SLA_DAYS = 5;
const ROLE_NAME = { supplier: 'المورد', matcher: 'المطابق', manager: 'المدير المالي', recon: 'مطابقة الكشوف', users: 'المستخدمون' };
const ME = { supplier: 'شركة النخبة للتوريدات', matcher: 'خالد العتيبي', manager: 'سلمان القحطاني' };
const STAGES = [
  { title: 'تقديم الطلب', desc: 'تم رفع طلبك بنجاح.' },
  { title: 'بانتظار الاستلام', desc: 'تم استلام طلبك من قبل موظف خدمات الموردين.' },
  { title: 'قيد المطابقة', desc: 'جاري العمل على مطابقة كشف الحساب.' },
  { title: 'مراسلات واستيضاح', desc: 'طلب مستندات لاستكمال مطابقة كشف الحساب.' },
  { title: 'الإنجاز', desc: 'تمت مطابقة كشف الحساب.' },
  { title: 'إرسال ملف المطابقة', desc: 'بانتظار إرسال ملف المطابقة.', doneDesc: 'تم إرسال ملف المطابقة من قبل موظف خدمات الموردين.' }
];
const ADVANCE = {
  1: { label: 'استلام الطلب وإسناده للمطابق', note: 'بدأت المطابقة على كشف الحساب' },
  2: { label: 'فتح مراسلة مع المورد', note: 'فُتحت قناة المراسلة مع المورد' },
  3: { label: 'إغلاق المراسلة وإنجاز الطلب', note: 'أُغلقت المراسلة وأُنجز الطلب' },
  4: { label: 'إرسال الملف إلى المورد', note: 'أُرسل ملف المطابقة إلى المورد' }
};
/* complaint service: goes straight to the finance manager, no matcher involved */
const C_STAGES = [
  { title: 'تقديم الشكوى', desc: 'سجّل المورد شكواه برقم فريد.' },
  { title: 'وصلت المدير المالي', desc: 'تصل مباشرة إلى المدير المالي دون المرور بالمطابقين.' },
  { title: 'قيد المراجعة', desc: 'المدير المالي يراجع الشكوى ويتواصل مع الجهات المعنية.' },
  { title: 'الرد والإغلاق', desc: 'رد المدير المالي بالقرار وأُغلقت الشكوى.' }
];
const C_ADV = {
  1: { label: 'بدء مراجعة الشكوى', note: 'بدأ المدير المالي مراجعة الشكوى' },
  2: { label: 'الرد وإغلاق الشكوى', note: 'أُغلقت الشكوى بعد رد المدير المالي' }
};
const C_CATS = ['دفعة غير مستلمة', 'فرق في الرصيد لم يُحسم', 'تأخر في السداد', 'تأخر الرد على الطلبات', 'تعامل موظف', 'أخرى'];

/* ---------- formatting ---------- */
function intl(opts) {
  try { return new Intl.DateTimeFormat('ar-SA-u-ca-gregory-nu-latn', opts); }
  catch (e) { return new Intl.DateTimeFormat('en-GB', opts); }
}
const dateFmt = intl({ day: 'numeric', month: 'short' });
const timeFmt = intl({ hour: 'numeric', minute: '2-digit', hour12: true });
const fmtDate = function (d) { return dateFmt.format(d); };
const fmtDT = function (d) { return dateFmt.format(d) + ' · ' + timeFmt.format(d); };
const unit = function (n, one, two, few, many) { return n === 1 ? one : n === 2 ? two : n + ' ' + (n <= 10 ? few : many); };
function since(d) {
  const m = Math.max(1, Math.round((NOW - d) / 60000));
  if (m < 60) return 'منذ ' + unit(m, 'دقيقة', 'دقيقتين', 'دقائق', 'دقيقة');
  const hr = Math.round(m / 60);
  if (hr < 24) return 'منذ ' + unit(hr, 'ساعة', 'ساعتين', 'ساعات', 'ساعة');
  const dd = Math.round(hr / 24);
  return 'منذ ' + unit(dd, 'يوم', 'يومين', 'أيام', 'يوماً');
}
const sar = function (n) { return n == null ? '—' : n === 0 ? 'لا فروقات' : new Intl.NumberFormat('en-US').format(n) + ' ر.س'; };
const fmtSize = function (b) { return b < 1048576 ? Math.max(1, Math.round(b / 1024)) + ' KB' : (b / 1048576).toFixed(1) + ' MB'; };
