"""مطابق كشوفات الحساب: أداة مطابقة كشف المورد مع دفاترنا. تعمل كلها في المتصفح (static/statement)؛
الخادم يقدّم الصفحة فقط ولا يستقبل أي ملف أو بيانات مالية."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_safe

from apps.core.access import role_required
from apps.core.models import Role

RT = Role.RoleType
STATEMENT_ROLES = (RT.ADMIN, RT.CFO, RT.ACCOUNTANT, RT.CS_SUPERVISOR)

SCRIPTS = ('sm-core.js', 'sm-xlsx.js', 'sm-ledger.js', 'sm-engine.js', 'sm-table.js', 'sm-report.js', 'sm-readers.js', 'sm-app.js')
ASSET_VERSION = '20261020'


@login_required
@role_required(*STATEMENT_ROLES)
@require_safe
def statement_matcher(request):
    return render(request, 'pages/statement/matcher.html', {
        'page_title': 'مطابق كشوفات الحساب', 'scripts': SCRIPTS, 'asset_version': ASSET_VERSION})
