'use strict';

/* ---------- the result as a diagnosis: summary, why the balances differ, what to do, and a card per open item ---------- */

/* title, diagnosis and action for each kind of open item (the keys come from rcCatOf in the engine) */
const RC_CARD = {
  inv_supplier: { title: 'فاتورة لدى المورد غير مسجلة لدينا', tone: 'amber',
    why: 'المورد سجّل فاتورة لا نظير لها في دفاترنا: لم تُدخل عندنا أو لم تُستلم.',
    todo: 'تحقق من استلام الفاتورة واسم المورد عليها، وابحث عن تكرار، واسأل المورد عن سند التسليم.' },
  inv_company: { title: 'فاتورة لدينا لم تظهر في كشف المورد', tone: 'blue',
    why: 'فاتورة سجّلناها ولم تظهر عند المورد: تأخر ترحيل أو لم تصله.',
    todo: 'أرسل للمورد نسخة الفاتورة وتأكد من تسليمها وإدخالها عنده.' },
  pay_company: { title: 'دفعة سددناها ولم يسجلها المورد', tone: 'blue',
    why: 'المورد لم يخصم الدفعة من رصيده: لم يستلمها أو لم يوزّعها على الفواتير.',
    todo: 'أرسل له إثبات التحويل وتاريخه واطلب تأكيد القيد.' },
  pay_supplier: { title: 'دفعة لدى المورد غير مسجلة لدينا', tone: 'amber',
    why: 'المورد سجّل استلام دفعة لا نجد لها قيداً عندنا.',
    todo: 'تحقق من السداد في كشف البنك، ثم سجّلها أو اعترض عليها.' },
  cn_supplier: { title: 'إشعار دائن/تخفيض لدى المورد غير مسجل لدينا', tone: 'amber',
    why: 'المورد خفّض رصيده بمبلغ لم نسجله (إشعار دائن، خصم، أو مرتجع اعترف به).',
    todo: 'اطلب نسخة المستند وسجّله، فهو لصالح الشركة.' },
  cn_company: { title: 'مرتجع أو خصم لدينا لم يعترف به المورد', tone: 'amber',
    why: 'أكثر فروقات الموردين شيوعاً: مرتجع لم يستلمه المورد بعد أو لم يوثّقه، أو خصم تعاقدي لم يقبله، أو فرق سعر خصمناه.',
    todo: 'أرسل للمورد نسخة سند الإرجاع الموقّع أو كشف احتساب الخصم مع بند الاتفاقية، واطلب إشعاراً دائناً مقابلاً.' },
  adj_company: { title: 'تسوية داخلية لدينا لا تظهر عند المورد', tone: 'blue',
    why: 'قيد داخلي (تكاليف أو مخزون) لا يخص المورد ولا يظهر في كشفه.',
    todo: 'راجعه داخلياً، ولا يُرسل للمورد.' },
  timing: { title: 'فرق توقيت: حركة بعد نهاية فترة الكشف الآخر', tone: 'blue',
    why: 'الحركة تقع بعد آخر تاريخ في الكشف الآخر، فلم تصل إليه بعد.',
    todo: 'لا تعالجها الآن؛ تتسوّى تلقائياً عند استلام الكشف للفترة التالية.' },
  adj_supplier: { title: 'تسوية لدى المورد غير مسجلة لدينا', tone: 'amber',
    why: 'المورد أجرى تسوية في حسابه لا نجدها في دفاترنا.',
    todo: 'اطلب تفاصيل التسوية ومستندها قبل قبولها.' },
  amount_diff: { title: 'فرق في مبلغ مستند متطابق الرقم', tone: 'red',
    why: 'المستند موجود عند الطرفين بمبلغين مختلفين: خصم تجاري أو ضريبة أو فرق تسعير.',
    todo: 'طابق الفاتورة الأصلية مع كشفك، وحدد الطرف المخطئ وصحّح القيد.' },
  matched_amount: { title: 'مطابق بالمبلغ دون رقم مستند', tone: 'blue',
    why: 'نفس المبلغ والتاريخ تقريباً لكن رقم المستند مختلف أو غائب.',
    todo: 'أكّد أنهما بند واحد وطابق رقم المستند.' },
  opening: { title: 'فرق في الرصيد الافتتاحي', tone: 'red',
    why: 'الرصيدان الافتتاحيان مختلفان: فرق مرحّل من فترة سابقة.',
    todo: 'راجع آخر مطابقة معتمدة مع المورد ومذكرة تسويتها، أو اطلب كشف الفترة السابقة.' }
};

/* the amount a card shows: the movement itself, or the gap for a pair that disagrees */
function rcCardAmount(it) {
  if (it.status === 'only_supplier') return it.amtA;
  if (it.status === 'after_period') return it.amtA != null ? it.amtA : it.amtB;
  if (it.status === 'only_company') return it.amtB;
  /* a pair matched by amount has no difference to show: its amount is the figure */
  if (it.status === 'matched_amount') return it.amtA != null ? it.amtA : it.amtB;
  return it.diff;
}
const rcPlain = function (v) { return (v < 0 ? '-' : '') + rcMoney(Math.abs(v)); };
const rcBr = function (v) { return Math.abs(v) < 0.005 ? '0.00' : (v < 0 ? '(' + rcMoney(-v) + ')' : rcMoney(v)); };

function RcDiagnosis(props) {
  const res = props.res;
  const open = res.items.filter(function (i) { return i.status !== 'matched' && i.status !== 'matched_amount' && i.status !== 'cancelled' && i.status !== 'after_period'; });
  const cancelledN = res.items.filter(function (i) { return i.status === 'cancelled'; }).length;
  const byAmountOnly = res.items.filter(function (i) { return i.status === 'matched_amount'; });
  const timingN = res.items.filter(function (i) { return i.status === 'after_period'; }).length;
  const agreed = res.items.length - open.length - cancelledN - timingN;
  const ranked = open.concat(byAmountOnly).map(function (i) { return { it: i, cat: rcCatOf(i), v: rcCardAmount(i) }; })
    .sort(function (a, b) { return Math.abs(b.v) - Math.abs(a.v); });
  const [filter, setFilter] = useState('all');
  const [limit, setLimit] = useState(40);
  const shownAll = filter === 'all' ? ranked : ranked.filter(function (x) { return x.cat === filter; });
  const shown = shownAll.slice(0, limit);

  const toYours = res.lines.map(function (l) { return Object.assign({}, l, { effect: -l.effect }); });
  const expected = res.sumB + toYours.reduce(function (s, l) { return s + l.effect; }, 0);
  const gap = expected - res.sumA;
  const diff = res.sumA - res.sumB;
  /* the timing part is the movements after the other statement's end; the rest is the real difference */
  const timingSum = res.items.filter(function (i) { return i.status === 'after_period'; }).reduce(function (t, i) { return t + ((i.amtA || 0) - (i.amtB || 0)); }, 0);
  const realDiff = diff - timingSum;
  const verdict = Math.abs(diff) < 0.5 ? { t: 'الرصيدان متطابقان', c: 'ok' }
    : Math.abs(gap) <= 0.5 ? { t: 'يوجد فرق مفسَّر بالكامل', c: 'warn' } : { t: 'يوجد فرق غير مفسَّر', c: 'bad' };
  const cats = {};
  ranked.forEach(function (x) { cats[x.cat] = (cats[x.cat] || 0) + 1; });

  /* what to do first: the biggest open items, in plain sentences */
  const top = ranked.filter(function (x) { return x.cat !== 'matched_amount'; }).slice(0, 5);
  const more = Math.max(0, ranked.length - top.length);

  const kpi = function (n, label, tone) { return div({ key: label, className: 'rcd-kpi' + (tone ? ' ' + tone : '') }, strong(null, n), span(null, label)); };
  const pct = res.items.length ? Math.round(agreed / res.items.length * 100) : 0;
  const count = function (st) { return res.items.filter(function (i) { return i.status === st; }).length; };

  return div({ className: 'rcd' },
    section({ className: 'rcd-sum' },
      div({ className: 'rcd-sumhead' }, h3(null, 'ملخص المطابقة'), span({ className: 'rcd-verdict ' + verdict.c }, verdict.t)),
      div({ className: 'rcd-grid' },
        div(null, span(null, 'رصيد المورد في دفاترنا'), strong({ className: 'mono' }, rcMoney(res.sumB))),
        div(null, span(null, 'رصيدنا في كشفه'), strong({ className: 'mono' }, rcMoney(res.sumA))),
        div(null, span(null, 'الفرق بين الرصيدين'), strong({ className: 'mono big' + (Math.abs(diff) < 0.5 ? '' : ' off') }, rcMoney(diff))),
        div(null, span(null, 'الحركات المطابقة'), strong({ className: 'mono' }, agreed + ' / ' + (res.items.length - cancelledN)))),
      toYours.length ? p({ className: 'rcd-why' }, strong(null, 'يتكون الفرق من: '),
        toYours.map(function (l, i) { return span({ key: l.key }, (i ? '، ' : '') + l.label + (l.count ? ' (' + l.count + ')' : '') + ' ', span({ className: 'mono rcd-num', dir: 'ltr' }, (l.effect > 0 ? '+' : '-') + rcMoney(Math.abs(l.effect)))); }),
        '.') : null,
      top.length ? div({ className: 'rcd-todo' }, strong(null, 'المطلوب:'),
        ol(null, top.map(function (x) {
          const c = RC_CARD[x.cat];
          return li({ key: x.it.id }, strong(null, c.title), ' ', span({ className: 'mono rcd-num', dir: 'ltr' }, rcPlain(x.v)), ': ', c.todo);
        })),
        more ? p({ className: 'muted small' }, 'و' + more + ' بنداً آخر في القائمة أدناه.') : null) : null),

    section({ className: 'rcd-bridge' },
      div({ className: 'rcd-brow main' }, span(null, 'رصيد المورد في دفاترنا'), strong({ className: 'mono' }, rcBr(res.sumB))),
      toYours.map(function (l) {
        return div({ key: l.key, className: 'rcd-brow' }, span(null, l.label, l.count ? span({ className: 'rcd-n' }, l.count + ' بند') : null),
          strong({ className: 'mono' }, (l.effect > 0 ? '+ ' : '− ') + rcMoney(Math.abs(l.effect))));
      }),
      div({ className: 'rcd-brow total' }, span(null, 'الرصيد المتوقع في كشفه'), strong({ className: 'mono' }, rcBr(expected))),
      div({ className: 'rcd-brow main' }, span(null, 'رصيد المورد حسب كشفه'), strong({ className: 'mono' }, rcBr(res.sumA))),
      div({ className: 'rcd-unexp' + (Math.abs(gap) > 0.5 ? ' off' : '') },
        strong(null, 'الفرق غير المفسَّر'),
        span({ className: 'muted' }, Math.abs(gap) > 0.5 ? 'بعد كل التسويات يبقى مبلغ لا تفسره الحركات. تأكد أن كل الصفحات قُرئت وأن الأرصدة الافتتاحية صحيحة.' : 'كل الفرق بين الرصيدين مفسَّر بالحركات أعلاه.'),
        span({ className: 'mono big' }, rcMoney(gap)))),
    p({ className: 'muted small' }, 'الأرصدة معروضة كمبلغ مستحق للمورد؛ القيمة السالبة تعني أن المورد مدين لنا.'),

    div({ className: 'rcd-kpis' },
      kpi(pct + '%', 'نسبة الحركات المطابقة'),
      kpi(count('matched'), 'تطابق مباشر'),
      kpi(count('matched_amount'), 'تطابق بالمبلغ فقط'),
      kpi(count('amount_diff'), 'فروق مبالغ', count('amount_diff') ? 'warn' : ''),
      kpi(count('only_supplier'), 'لدى المورد فقط', count('only_supplier') ? 'warn' : ''),
      kpi(count('only_company'), 'لدينا فقط', count('only_company') ? 'warn' : ''),
      kpi(cancelledN, 'قيود ملغاة (صافيها صفر)'),
      kpi(rcMoney(timingSum), 'منه فروق توقيت'),
      kpi(rcMoney(realDiff), 'الفرق الحقيقي')),

    ranked.length ? div({ className: 'rcd-list' },
      div({ className: 'rcd-filters noprint', role: 'group', 'aria-label': 'تصفية البنود' },
        button({ type: 'button', className: 'fchip', 'aria-pressed': filter === 'all', onClick: function () { setFilter('all'); setLimit(40); } }, 'الكل', h('b', null, ranked.length)),
        Object.keys(cats).map(function (k) {
          return button({ key: k, type: 'button', className: 'fchip', 'aria-pressed': filter === k, onClick: function () { setFilter(k); setLimit(40); } }, RC_CARD[k].title, h('b', null, cats[k]));
        })),
      shown.map(function (x) {
        const c = RC_CARD[x.cat], it = x.it;
        const side = it.status === 'only_company' ? 'دفاترنا' : it.status === 'only_supplier' ? 'كشف المورد' : 'الطرفان';
        const meta = [side, it.date ? fmtDate(it.date) : null, it.doc ? 'المرجع ' + it.doc : null, RC_KIND[it.kind], rcPlain(x.v), (it.descA || it.descB || '').slice(0, 90)].filter(Boolean).join(' | ');
        return div({ key: it.id, className: 'rcd-card ' + c.tone },
          div({ className: 'rcd-chead' }, h4(null, c.title), span({ className: 'mono rcd-amt' }, rcPlain(x.v))),
          div({ className: 'rcd-meta' }, meta),
          p(null, strong(null, 'التشخيص: '), c.why),
          p(null, strong(null, 'الإجراء: '), c.todo));
      }),
      shownAll.length > shown.length ? button({ type: 'button', className: 'btn ghost rcd-more', onClick: function () { setLimit(limit + 60); } }, 'عرض المزيد (' + (shownAll.length - shown.length) + ' بنداً متبقياً)') : null)
      : div({ className: 'note' }, 'لا توجد بنود تحتاج إجراءً: كل الحركات متطابقة.'));
}
