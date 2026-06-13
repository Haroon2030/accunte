from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError


class SimplePasswordChangeForm(PasswordChangeForm):
    """نموذج تغيير كلمة مرور مبسط مع رسائل عربية وقبول 4 أحرف."""

    def clean_old_password(self):
        old_password = (self.data.get('old_password') or '').strip()
        if not old_password:
            raise ValidationError('يرجى إدخال كلمة المرور الحالية')
        if not self.user.check_password(old_password):
            raise ValidationError(
                'كلمة المرور الحالية غير صحيحة. '
                'أدخل كلمة المرور التي تسجل بها الدخول، وليس كلمة المرور الجديدة.'
            )
        return old_password

    def clean_new_password1(self):
        new_password = (self.data.get('new_password1') or '').strip()
        if not new_password:
            raise ValidationError('يرجى إدخال كلمة المرور الجديدة')
        if len(new_password) < 4:
            raise ValidationError('كلمة المرور يجب أن تكون 4 أحرف على الأقل')
        old_password = (self.data.get('old_password') or '').strip()
        if old_password and new_password == old_password:
            raise ValidationError('كلمة المرور الجديدة يجب أن تختلف عن كلمة المرور الحالية')
        password_validation.validate_password(new_password, self.user)
        return new_password

    def clean_new_password2(self):
        new_password2 = (self.data.get('new_password2') or '').strip()
        new_password1 = self.cleaned_data.get('new_password1')
        if not new_password2:
            raise ValidationError('يرجى تأكيد كلمة المرور الجديدة')
        if new_password1 and new_password2 != new_password1:
            raise ValidationError('كلمة المرور الجديدة غير متطابقة')
        return new_password2
