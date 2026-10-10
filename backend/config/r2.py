"""
بناء خيارات تخزين Cloudflare R2 (S3-compatible) من كائن إعدادات واحد.
يُستعمل من base.py (تخزين الوسائط الافتراضي) ومن التخزين الخاص للمرفقات، فيبقى المنطق في مكان واحد.
"""

REQUIRED = ('R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET_NAME', 'R2_ENDPOINT_URL')


def missing_settings(cfg):
    return [name for name in REQUIRED if not getattr(cfg, name, '')]


def storage_options(cfg):
    """cfg: أي كائن له خصائص R2_* (django.conf.settings أو SimpleNamespace)."""
    public_domain = (getattr(cfg, 'R2_PUBLIC_DOMAIN', '') or '').strip()
    return {
        'access_key': cfg.R2_ACCESS_KEY_ID,
        'secret_key': cfg.R2_SECRET_ACCESS_KEY,
        'bucket_name': cfg.R2_BUCKET_NAME,
        'endpoint_url': cfg.R2_ENDPOINT_URL,
        'region_name': getattr(cfg, 'R2_REGION', 'auto'),
        'signature_version': 's3v4',
        'addressing_style': 'path',
        # روابط موقّعة مؤقتة (الـbucket خاص). عند وجود دومين عام نستعمل روابطه بلا توقيع
        'querystring_auth': bool(getattr(cfg, 'R2_SIGNED_URLS', True)) and not public_domain,
        'querystring_expire': int(getattr(cfg, 'R2_SIGNED_URL_EXPIRE', 3600)),
        'custom_domain': public_domain or None,
        'location': (getattr(cfg, 'R2_PREFIX', '') or '').strip('/'),
        'file_overwrite': False,
        'default_acl': None,
    }
