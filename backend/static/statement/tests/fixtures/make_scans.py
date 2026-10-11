"""يولّد PDF بطبقة نصية (عربي مُشكَّل بترتيب بصري كما تفعل أنظمة كثيرة) وصورة ممسوحة وPDF صوري.
يحتاج: reportlab, arabic_reshaper, python-bidi, Pillow. التشغيل: python make_scans.py"""
import os

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = r'C:\Windows\Fonts\tahoma.ttf'
pdfmetrics.registerFont(TTFont('Tahoma', FONT))


def vis(text):
    """نص بصري: تشكيل الحروف + ترتيب العرض (كما يُخزَّن في PDF كثيرة)."""
    if any('\u0600' <= ch <= '\u06ff' for ch in text):
        return get_display(arabic_reshaper.reshape(text))
    return text


HEADER = ['التاريخ', 'رقم المستند', 'البيان', 'مدين', 'دائن', 'الرصيد']
COLS_X = [540, 470, 330, 215, 150, 75]        # مراكز الأعمدة من اليمين لليسار (نقاط)
SUPPLIER_ROWS = [
    ['', '', 'رصيد افتتاحي', '5,000.00', '', '5,000.00'],
    ['05/01/2026', 'INV-1001', 'فاتورة مشتريات', '10,000.00', '', '15,000.00'],
    ['12/01/2026', 'PAY-77', 'دفعة مستلمة تحويل', '', '4,000.00', '11,000.00'],
    ['20/01/2026', 'INV-1002', 'فاتورة مشتريات', '2,500.50', '', '13,500.50'],
    ['27/01/2026', 'INV-1003', 'فاتورة مشتريات', '1,500.00', '', '15,000.50'],
]
PREFACE = ['كشف حساب العميل', 'اسم المورد: شركة الأفق للتوريدات']


def make_pdf(name, rows, with_text=True):
    c = canvas.Canvas(os.path.join(HERE, name), pagesize=A4)
    w, h = A4
    y = h - 60
    c.setFont('Tahoma', 13)
    for line in PREFACE:
        c.drawRightString(w - 55, y, vis(line)); y -= 22
    y -= 14
    c.setFont('Tahoma', 10)
    for x, label in zip(COLS_X, HEADER):
        c.drawCentredString(x, y, vis(label))
    c.line(40, y - 5, w - 40, y - 5)
    y -= 24
    for row in rows:
        for x, cell in zip(COLS_X, row):
            if cell:
                c.drawCentredString(x, y, vis(cell))
        y -= 20
    c.save()


def make_png(name, rows, scale=2.2, noise=True):
    W, H = int(595 * scale), int(420 * scale)
    img = Image.new('L', (W, H), 255)
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, int(12 * scale)); fh = ImageFont.truetype(FONT, int(14 * scale))
    y = int(40 * scale)
    for line in PREFACE:
        d.text((W - int(55 * scale), y), vis(line), font=fh, fill=20, anchor='ra'); y += int(24 * scale)
    y += int(14 * scale)
    for x, label in zip(COLS_X, HEADER):
        d.text((int(x * scale), y), vis(label), font=f, fill=10, anchor='ma')
    d.line([(int(40 * scale), y + int(20 * scale)), (W - int(40 * scale), y + int(20 * scale))], fill=60, width=2)
    y += int(34 * scale)
    for row in rows:
        for x, cell in zip(COLS_X, row):
            if cell:
                d.text((int(x * scale), y), vis(cell), font=f, fill=25, anchor='ma')
        y += int(26 * scale)
    if noise:
        img = img.rotate(0.6, fillcolor=255).filter(ImageFilter.GaussianBlur(0.6))
    img.save(os.path.join(HERE, name))
    return name


def make_image_pdf(name, png):
    c = canvas.Canvas(os.path.join(HERE, name), pagesize=A4)
    w, h = A4
    c.drawImage(os.path.join(HERE, png), 20, h - 520, width=w - 40, height=(w - 40) * 420 / 595)
    c.save()


if __name__ == '__main__':
    make_pdf('pdf_supplier.pdf', SUPPLIER_ROWS)
    png = make_png('img_supplier.png', SUPPLIER_ROWS)
    make_image_pdf('pdf_scanned.pdf', png)
    print('scans written')
