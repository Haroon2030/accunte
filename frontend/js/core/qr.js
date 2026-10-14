'use strict';

/* ---------- QR code (byte mode, error correction L, versions 1-12) and the ZATCA simple-invoice payload ---------- */
const QR_ECC_PER_BLOCK = [0, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24];       // level L, index = version
const QR_BLOCKS = [0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4];

function qrRawModules(ver) {
  let r = (16 * ver + 128) * ver + 64;
  if (ver >= 2) { const na = Math.floor(ver / 7) + 2; r -= (25 * na - 10) * na - 55; if (ver >= 7) r -= 36; }
  return r;
}
function qrGfMul(x, y) {
  let z = 0;
  for (let i = 7; i >= 0; i--) { z = (z << 1) ^ ((z >>> 7) * 0x11D); z ^= ((y >>> i) & 1) * x; }
  return z;
}
function qrDivisor(degree) {
  const res = []; for (let i = 0; i < degree - 1; i++) res.push(0); res.push(1);
  let root = 1;
  for (let i = 0; i < degree; i++) {
    for (let j = 0; j < res.length; j++) { res[j] = qrGfMul(res[j], root); if (j + 1 < res.length) res[j] ^= res[j + 1]; }
    root = qrGfMul(root, 2);
  }
  return res;
}
function qrRemainder(data, div) {
  const res = div.map(function () { return 0; });
  data.forEach(function (b) {
    const f = b ^ res.shift(); res.push(0);
    div.forEach(function (c, i) { res[i] ^= qrGfMul(c, f); });
  });
  return res;
}
function qrBytes(text) { return Array.prototype.slice.call(new TextEncoder().encode(text)); }

/* returns an array of rows (true = dark) */
function qrEncode(text) {
  const bytes = qrBytes(text);
  let ver = 1;
  for (; ver <= 12; ver++) {
    const cap = Math.floor(qrRawModules(ver) / 8) - QR_ECC_PER_BLOCK[ver] * QR_BLOCKS[ver];
    const need = 4 + (ver < 10 ? 8 : 16) + bytes.length * 8;
    if (need <= cap * 8) break;
  }
  if (ver > 12) throw new Error('النص أطول من أن يُرمَّز.');
  const dataCw = Math.floor(qrRawModules(ver) / 8) - QR_ECC_PER_BLOCK[ver] * QR_BLOCKS[ver];

  /* bit stream */
  const bits = [];
  const put = function (v, n) { for (let i = n - 1; i >= 0; i--) bits.push((v >>> i) & 1); };
  put(4, 4); put(bytes.length, ver < 10 ? 8 : 16); bytes.forEach(function (b) { put(b, 8); });
  put(0, Math.min(4, dataCw * 8 - bits.length));
  while (bits.length % 8) bits.push(0);
  for (let pad = 0xEC; bits.length < dataCw * 8; pad ^= 0xEC ^ 0x11) put(pad, 8);
  const data = []; for (let i = 0; i < bits.length; i += 8) { let v = 0; for (let j = 0; j < 8; j++) v = (v << 1) | bits[i + j]; data.push(v); }

  /* error correction and interleaving */
  const nb = QR_BLOCKS[ver], ecl = QR_ECC_PER_BLOCK[ver], raw = Math.floor(qrRawModules(ver) / 8);
  const nShort = nb - raw % nb, shortLen = Math.floor(raw / nb);
  const div = qrDivisor(ecl), blocks = [];
  for (let i = 0, k = 0; i < nb; i++) {
    const dat = data.slice(k, k + shortLen - ecl + (i < nShort ? 0 : 1)); k += dat.length;
    const ec = qrRemainder(dat, div);
    if (i < nShort) dat.push(0);
    blocks.push(dat.concat(ec));
  }
  const all = [];
  for (let i = 0; i < blocks[0].length; i++) blocks.forEach(function (b, j) { if (i !== shortLen - ecl || j >= nShort) all.push(b[i]); });

  /* matrix */
  const size = ver * 4 + 17;
  const mod = [], fn = [];
  for (let y = 0; y < size; y++) { mod.push(new Array(size).fill(false)); fn.push(new Array(size).fill(false)); }
  const setFn = function (x, y, dark) { mod[y][x] = dark; fn[y][x] = true; };
  for (let i = 0; i < size; i++) { setFn(6, i, i % 2 === 0); setFn(i, 6, i % 2 === 0); }
  const finder = function (cx, cy) {
    for (let dy = -4; dy <= 4; dy++) for (let dx = -4; dx <= 4; dx++) {
      const d = Math.max(Math.abs(dx), Math.abs(dy)), x = cx + dx, y = cy + dy;
      if (x >= 0 && x < size && y >= 0 && y < size) setFn(x, y, d !== 2 && d !== 4);
    }
  };
  finder(3, 3); finder(size - 4, 3); finder(3, size - 4);
  const pos = [];
  if (ver > 1) {
    const na = Math.floor(ver / 7) + 2, step = ver === 32 ? 26 : Math.ceil((ver * 4 + 4) / (na * 2 - 2)) * 2;
    pos.push(6); for (let p = size - 7; pos.length < na; p -= step) pos.splice(1, 0, p);
  }
  pos.forEach(function (py, i) {
    pos.forEach(function (px, j) {
      if ((i === 0 && j === 0) || (i === 0 && j === pos.length - 1) || (i === pos.length - 1 && j === 0)) return;
      for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) setFn(px + dx, py + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
    });
  });
  const bit = function (v, i) { return ((v >>> i) & 1) !== 0; };
  const formatBits = function (mask) {
    const d = (1 << 3) | mask;            // level L = 01
    let r = d; for (let i = 0; i < 10; i++) r = (r << 1) ^ ((r >>> 9) * 0x537);
    const b = ((d << 10) | r) ^ 0x5412;
    for (let i = 0; i <= 5; i++) setFn(8, i, bit(b, i));
    setFn(8, 7, bit(b, 6)); setFn(8, 8, bit(b, 7)); setFn(7, 8, bit(b, 8));
    for (let i = 9; i < 15; i++) setFn(14 - i, 8, bit(b, i));
    for (let i = 0; i < 8; i++) setFn(size - 1 - i, 8, bit(b, i));
    for (let i = 8; i < 15; i++) setFn(8, size - 15 + i, bit(b, i));
    setFn(8, size - 8, true);
  };
  formatBits(0);
  if (ver >= 7) {
    let r = ver; for (let i = 0; i < 12; i++) r = (r << 1) ^ ((r >>> 11) * 0x1F25);
    const b = (ver << 12) | r;
    for (let i = 0; i < 18; i++) { const a = size - 11 + i % 3, c = Math.floor(i / 3); setFn(a, c, bit(b, i)); setFn(c, a, bit(b, i)); }
  }
  /* codewords, zig-zag */
  let k = 0;
  for (let right = size - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (let vert = 0; vert < size; vert++) for (let j = 0; j < 2; j++) {
      const x = right - j, up = ((right + 1) & 2) === 0, y = up ? size - 1 - vert : vert;
      if (!fn[y][x] && k < all.length * 8) { mod[y][x] = bit(all[k >>> 3], 7 - (k & 7)); k++; }
    }
  }
  /* mask 0, then the real format bits */
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) if (!fn[y][x] && (x + y) % 2 === 0) mod[y][x] = !mod[y][x];
  formatBits(0);
  return mod;
}

/* an inline SVG string for the code, with a four-module quiet zone */
function qrSvg(text, px) {
  const m = qrEncode(text), n = m.length, q = 4;
  let d = '';
  m.forEach(function (row, y) { let x = 0; while (x < n) { if (row[x]) { let w = 1; while (x + w < n && row[x + w]) w++; d += 'M' + (x + q) + ' ' + (y + q) + 'h' + w + 'v1h-' + w + 'z'; x += w; } else x++; } });
  return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + (n + q * 2) + ' ' + (n + q * 2) + '" width="' + (px || 160) + '" height="' + (px || 160) + '" shape-rendering="crispEdges" role="img" aria-label="رمز الاستجابة السريعة للفاتورة"><rect width="100%" height="100%" fill="#fff"/><path d="' + d + '" fill="#000"/></svg>';
}

/* ZATCA phase-1 payload: seller name, VAT number, time, total with VAT, VAT amount; each as tag-length-value, then base64 */
function zatcaPayload(sellerName, vatNo, isoTime, total, vatAmount) {
  const tlv = function (tag, v) { const b = qrBytes(String(v)); return [tag, b.length].concat(b); };
  const all = [].concat(tlv(1, sellerName), tlv(2, vatNo), tlv(3, isoTime), tlv(4, Number(total).toFixed(2)), tlv(5, Number(vatAmount).toFixed(2)));
  let s = ''; all.forEach(function (b) { s += String.fromCharCode(b); });
  return btoa(s);
}
