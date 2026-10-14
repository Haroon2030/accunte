"""Plain dict serializers. Field names match what the frontend already uses."""


def iso(dt):
    return dt.isoformat() if dt else None


def user_out(u):
    from .permissions import allowed_pages
    return {
        'pages': allowed_pages(u), 'customPages': u.pages is not None,
        'id': u.pk, 'name': u.name, 'username': u.username, 'role': u.role, 'org': u.org,
        'code': u.code or '', 'taxNo': u.tax_no, 'active': u.is_active,
        'mustChange': u.must_change_password, 'last': iso(u.last_login), 'created': iso(u.created_at),
    }


def file_out(a):
    return {'id': a.pk, 'name': a.original_name, 'size': a.size, 'url': f'/api/attachments/{a.pk}/download/'}


def message_out(m):
    who = m.sender.name if m.sender else ''
    return {
        'id': m.pk, 'from': m.kind, 'sender': who, 'text': m.text, 'at': iso(m.created_at),
        'files': [file_out(a) for a in m.files.all()],
    }


def request_out(r, messages=True):
    statement = next((a for a in r.attachments.all() if a.kind == 'statement'), None)
    result = next((a for a in r.attachments.all() if a.kind == 'result'), None)
    out = {
        'id': r.number, 'pk': r.pk, 'supplier': r.supplier.org or r.supplier.name, 'supplierCode': r.supplier.code or '',
        'supplierId': r.supplier_id, 'period': r.period, 'notes': r.notes, 'stage': r.stage,
        'matcher': r.matcher.name if r.matcher else None, 'matcherId': r.matcher_id,
        'diff': float(r.diff) if r.diff is not None else None,
        'created': iso(r.created_at), 'due': iso(r.due_at), 'reached': r.reached,
        'statement': file_out(statement) if statement else None,
        'result': file_out(result) if result else None,
    }
    if messages:
        out['messages'] = [message_out(m) for m in r.messages.all()]
    return out


def complaint_out(c, messages=True):
    out = {
        'id': c.number, 'pk': c.pk, 'supplier': c.supplier.org or c.supplier.name, 'supplierId': c.supplier_id,
        'category': c.category, 'subject': c.subject, 'related': c.related.number if c.related else None,
        'stage': c.stage, 'created': iso(c.created_at), 'reached': c.reached,
    }
    if messages:
        out['messages'] = [message_out(m) for m in c.messages.all()]
    return out


def notice_out(n):
    from django.conf import settings
    items = []
    for it in n.items:
        from decimal import ROUND_HALF_UP, Decimal
        qty, price, disc = Decimal(str(it['qty'])), Decimal(str(it['price'])), Decimal(str(it.get('discount') or 0))
        gross = (qty * price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        net = gross - disc
        tax = (net * n.vat_rate / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        items.append({'code': it.get('code', ''), 'name': it['name'], 'qty': float(qty), 'price': float(price), 'discount': float(disc),
                      'amount': float(gross), 'tax': float(tax), 'total': float(net + tax)})
    return {
        'id': n.number, 'pk': n.pk, 'supplier': n.supplier.org or n.supplier.name, 'supplierId': n.supplier_id,
        'supplierTax': n.supplier.tax_no, 'supplierCode': n.supplier.code or '', 'buyer': n.buyer or {},
        'issuedAt': iso(n.issued_at), 'dueDate': n.due_date.isoformat() if n.due_date else None,
        'paymentMethod': n.payment_method, 'description': n.description, 'items': items,
        'discount': float(n.discount), 'subtotal': float(n.subtotal), 'vat': float(n.vat), 'vatRate': float(n.vat_rate), 'total': float(n.total),
        'issuedBy': n.issued_by.name if n.issued_by else '', 'seller': dict(settings.COMPANY_PROFILE),
    }
