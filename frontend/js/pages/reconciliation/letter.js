'use strict';

/* ---------- the official reconciliation letter to the supplier (printable, with the supplier's acknowledgement) ---------- */
function RcLetter(props) {
  const res = props.res;
  const [supplier, setSupplier] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [days, setDays] = useState('7');
  const [note, setNote] = useState('');
  const [annex, setAnnex] = useState(false);
  const ref = 'RL-' + res.at.getFullYear() + String(res.at.getMonth() + 1).padStart(2, '0') + String(res.at.getDate()).padStart(2, '0') + '-' + String(res.at.getHours()).padStart(2, '0') + String(res.at.getMinutes()).padStart(2, '0');
  const open = res.items.filter(function (i) { return i.status !== 'matched' && i.status !== 'matched_amount'; });
  const agreed = res.items.length - open.length;
  const balanced = Math.abs(res.diff) < 0.5;
  const byValue = function (list) { return list.slice().sort(function (a, b) { return Math.abs(rcCardAmount(b)) - Math.abs(rcCardAmount(a)); }); };
  const groups = [
    { key: 'theirs', title: 'بنود في كشفكم لم نجدها في دفاترنا', list: byValue(open.filter(function (i) { return i.status === 'only_supplier'; })) },
    { key: 'ours', title: 'بنود في دفاترنا لم نجدها في كشفكم', list: byValue(open.filter(function (i) { return i.status === 'only_company'; })) },
    { key: 'diff', title: 'بنود متطابقة الرقم باختلاف المبلغ', list: byValue(open.filter(function (i) { return i.status === 'amount_diff'; })) }
  ].filter(function (g) { return g.list.length; });
  const LIMIT = 15;

  const rowOf = function (it) {
    const v = rcCardAmount(it);
    return tr({ key: it.id },
      td(null, it.date ? fmtDate(it.date) : '—'),
      td({ className: 'mono' }, it.doc || '—'),
      td(null, RC_KIND[it.kind] + ((it.descA || it.descB) ? ' · ' + (it.descA || it.descB).slice(0, 60) : '')),
      td({ className: 'num' }, span({ className: 'mono', dir: 'ltr' }, it.status === 'amount_diff' ? rcMoney(it.amtA) + ' / ' + rcMoney(it.amtB) : rcPlain(v))));
  };
  const tbl = function (list, key) {
    return div({ key: key, className: 'tablewrap stmt' }, table({ className: 'dt' },
      thead(null, tr(null, th({ scope: 'col' }, 'التاريخ'), th({ scope: 'col' }, 'المستند'), th({ scope: 'col' }, 'البيان'),
        th({ scope: 'col', className: 'num' }, key === 'diff' ? 'كشفكم / دفاترنا' : 'المبلغ'))),
      tbody(null, list.map(rowOf))));
  };
  const field = function (id, labelText, value, set, extra) {
    return div({ className: 'rcl-f' }, label({ htmlFor: id }, labelText), input(Object.assign({ id: id, value: value, onChange: function (e) { set(e.target.value); } }, extra || {})));
  };

  return div({ className: 'rcl' },
    div({ className: 'rcl-form noprint' },
      field('rl-sup', 'اسم المورد', supplier, setSupplier, { placeholder: 'مثال: شركة الوطنية للتنمية الزراعية', autoComplete: 'off' }),
      field('rl-from', 'الفترة من', from, setFrom, { type: 'date' }),
      field('rl-to', 'إلى', to, setTo, { type: 'date' }),
      field('rl-days', 'مهلة الرد (أيام عمل)', days, setDays, { type: 'number', min: 1, max: 60, inputMode: 'numeric' }),
      div({ className: 'rcl-f wide' }, label({ htmlFor: 'rl-note' }, 'ملاحظة إضافية (اختياري)'), textarea({ id: 'rl-note', rows: 2, value: note, onChange: function (e) { setNote(e.target.value); } })),
      div({ className: 'rcl-acts' },
        label({ className: 'rcl-chk' }, input({ type: 'checkbox', checked: annex, onChange: function (e) { setAnnex(e.target.checked); } }), 'إرفاق ملحق بكل البنود (' + open.length + ')'),
        button({ type: 'button', className: 'btn primary', onClick: function () { try { rcPrint(false); } catch (e) { props.onToast('الطباعة غير متاحة هنا.'); } } }, h(Icon, { name: 'print', size: 16 }), 'طباعة الخطاب / PDF'))),

    div({ className: 'rc-doc rcl-doc' },
      div({ className: 'rc-letter' },
        div({ className: 'rc-org' }, strong(null, 'أسواق الرشيد'), span(null, 'الإدارة المالية · قسم المطابقة')),
        div({ className: 'rc-ref' }, div(null, span(null, 'الرقم'), strong({ className: 'mono' }, ref)), div(null, span(null, 'التاريخ'), strong(null, fmtDate(res.at))))),
      div({ className: 'rcl-to' }, p(null, 'السادة / ', strong(null, supplier.trim() || '……………………………')), p({ className: 'muted' }, 'المحترمين')),
      p(null, 'السلام عليكم ورحمة الله وبركاته،'),
      p({ className: 'rcl-subject' }, strong(null, 'الموضوع: مطابقة كشف حساب' + (from && to ? ' عن الفترة من ' + fmtDate(new Date(from)) + ' إلى ' + fmtDate(new Date(to)) : ''))),
      p(null, 'إشارةً إلى كشف حسابكم، وبعد مطابقته مع قيود دفاترنا، نفيدكم بنتيجة المطابقة على النحو الآتي:'),
      div({ className: 'tablewrap stmt' }, table({ className: 'dt' },
        thead(null, tr(null, th({ scope: 'col' }, 'البيان'), th({ scope: 'col', className: 'num' }, 'المبلغ (ر.س)'))),
        tbody(null,
          tr(null, td(null, 'رصيدكم حسب كشفكم'), td({ className: 'num' }, span({ className: 'mono', dir: 'ltr' }, rcMoney(res.sumA)))),
          tr(null, td(null, 'رصيدكم حسب دفاترنا'), td({ className: 'num' }, span({ className: 'mono', dir: 'ltr' }, rcMoney(res.sumB)))),
          tr({ className: 'strong' }, td(null, 'الفرق بين الرصيدين'), td({ className: 'num' }, span({ className: 'mono rc-diff' + (balanced ? '' : ' off'), dir: 'ltr' }, balanced ? 'لا يوجد فرق' : rcMoney(res.diff)))),
          tr(null, td(null, 'الحركات المتطابقة'), td({ className: 'num' }, span({ className: 'mono', dir: 'ltr' }, agreed + ' / ' + res.items.length)))))),
      balanced
        ? p(null, 'وعليه فإن الرصيدين متطابقان، ونأمل التكرم بتأكيد ذلك بتوقيع الإقرار أدناه وإعادته إلينا.')
        : [p({ key: 'p' }, 'وقد تبيّن وجود فروق بين الكشفين، وفيما يلي أبرز البنود التي تحتاج إلى مراجعتكم:'),
          groups.map(function (g) {
            return div({ key: g.key, className: 'rcl-group' }, h4(null, g.title + ' (' + g.list.length + ')'), tbl(g.list.slice(0, LIMIT), g.key),
              g.list.length > LIMIT ? p({ className: 'muted small' }, 'وعدد ' + (g.list.length - LIMIT) + ' بنداً آخر' + (annex ? ' في الملحق المرفق.' : '.')) : null);
          }),
          p({ key: 'q' }, 'نأمل مراجعة هذه البنود والإفادة بما لديكم من مستندات داعمة (فواتير، سندات تسليم، إشعارات دائنة، إثباتات سداد) خلال ', strong(null, (days || '7') + ' أيام عمل'),
            ' من تاريخ هذا الخطاب، وفي حال عدم ورود ردكم خلال المدة المذكورة يُعتمد الرصيد حسب دفاترنا.')],
      note.trim() ? p({ className: 'rcl-note' }, note.trim()) : null,
      p(null, 'وتفضلوا بقبول فائق الاحترام والتقدير،'),
      div({ className: 'rc-sign' }, ['أعدّه' + (props.by ? ': ' + props.by : ''), 'مدير الإدارة المالية', 'الختم'].map(function (t) { return div({ key: t }, span(null, t), div({ className: 'rc-line' })); })),

      div({ className: 'rcl-ack' },
        h4(null, 'إقرار المورد'),
        p(null, 'نقر نحن ', strong(null, supplier.trim() || '……………………………'), ' بأن رصيدنا لدى أسواق الرشيد بتاريخ ………………… هو ', span({ className: 'rcl-blank' }), ' ريال سعودي',
          ' ☐ ونوافق على ما ورد في هذا الخطاب  ☐ ولنا الملاحظات المرفقة.'),
        div({ className: 'rc-sign' }, ['الاسم', 'التوقيع', 'الختم والتاريخ'].map(function (t) { return div({ key: t }, span(null, t), div({ className: 'rc-line' })); }))),

      annex && open.length ? div({ className: 'rcl-annex' }, h4(null, 'الملحق: كل البنود التي تحتاج إلى مراجعة (' + open.length + ')'), tbl(byValue(open), 'annex')) : null));
}
