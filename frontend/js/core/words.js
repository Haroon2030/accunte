'use strict';

/* ---------- an amount in Arabic words: 3450.5 -> "ثلاثة آلاف وأربعمائة وخمسون ريالاً سعودياً وخمسون هللة" ---------- */
const AR_ONES = ['', 'واحد', 'اثنان', 'ثلاثة', 'أربعة', 'خمسة', 'ستة', 'سبعة', 'ثمانية', 'تسعة', 'عشرة', 'أحد عشر', 'اثنا عشر', 'ثلاثة عشر', 'أربعة عشر', 'خمسة عشر', 'ستة عشر', 'سبعة عشر', 'ثمانية عشر', 'تسعة عشر'];
const AR_TENS = ['', '', 'عشرون', 'ثلاثون', 'أربعون', 'خمسون', 'ستون', 'سبعون', 'ثمانون', 'تسعون'];
const AR_HUNDREDS = ['', 'مائة', 'مئتان', 'ثلاثمائة', 'أربعمائة', 'خمسمائة', 'ستمائة', 'سبعمائة', 'ثمانمائة', 'تسعمائة'];
/* [one, two, 3-10, 11+] for each scale */
const AR_SCALES = [null, ['ألف', 'ألفان', 'آلاف', 'ألفاً'], ['مليون', 'مليونان', 'ملايين', 'مليوناً'], ['مليار', 'ملياران', 'مليارات', 'ملياراً']];

function arUnder1000(n) {
  const parts = [];
  const h = Math.floor(n / 100), r = n % 100;
  if (h) parts.push(AR_HUNDREDS[h]);
  if (r) {
    if (r < 20) parts.push(AR_ONES[r]);
    else { const o = r % 10, t = Math.floor(r / 10); parts.push(o ? AR_ONES[o] + ' و' + AR_TENS[t] : AR_TENS[t]); }
  }
  return parts.join(' و');
}
function arInt(n) {
  if (n === 0) return 'صفر';
  const chunks = [];
  let scale = 0;
  while (n > 0 && scale < 4) {
    const c = n % 1000; n = Math.floor(n / 1000);
    if (c) {
      let t;
      if (scale === 0) t = arUnder1000(c);
      else if (c === 1) t = AR_SCALES[scale][0];
      else if (c === 2) t = AR_SCALES[scale][1];
      else if (c <= 10) t = AR_ONES[c] + ' ' + AR_SCALES[scale][2];
      else t = arUnder1000(c) + ' ' + AR_SCALES[scale][3];
      chunks.unshift(t);
    }
    scale++;
  }
  return chunks.join(' و');
}
function arMoney(v) {
  const cents = Math.round(Math.abs(Number(v) || 0) * 100);
  const riyal = Math.floor(cents / 100), hal = cents % 100;
  let t = arInt(riyal) + ' ريال سعودي';
  if (hal) t += ' و' + arInt(hal) + ' هللة';
  return t;
}
