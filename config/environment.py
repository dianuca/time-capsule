"""Read deployment options without loading .env files or exposing their values."""

import re
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def boolean(environ, name, default):
    value = environ.get(name)
    if value is None:
        return default
    value = value.strip().lower()
    if value in {"true", "1", "yes", "on"}:
        return True
    if value in {"false", "0", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"{name} must be a boolean (true/false).")


def comma_list(environ, name):
    return [part.strip() for part in environ.get(name, "").split(",") if part.strip()]


def security_settings(environ):
    debug = boolean(environ, "DJANGO_DEBUG", True)
    secret = environ.get("DJANGO_SECRET_KEY", "").strip()
    hosts = comma_list(environ, "DJANGO_ALLOWED_HOSTS")
    origins = comma_list(environ, "DJANGO_CSRF_TRUSTED_ORIGINS")
    if not debug:
        if len(secret) < 50 or len(set(secret)) < 5 or secret.startswith("django-insecure-"):
            raise ImproperlyConfigured("DJANGO_SECRET_KEY must be a strong, private key of at least 50 characters when DJANGO_DEBUG=false.")
        if not hosts:
            raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS is required when DJANGO_DEBUG=false.")
    for host in hosts:
        if not re.fullmatch(r"\.?[a-zA-Z0-9][a-zA-Z0-9.-]*|\[[0-9a-fA-F:]+\]", host):
            raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must contain hostnames or IP addresses, without wildcards, schemes, ports or paths.")
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            valid = (
                parsed.scheme in ({"http", "https"} if debug else {"https"})
                and parsed.hostname and "*" not in parsed.hostname
                and parsed.username is None and parsed.password is None
                and not parsed.path and not parsed.query and not parsed.fragment
            )
            parsed.port  # Validate the optional port too.
        except ValueError:
            valid = False
        if not valid:
            raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS must contain exact origins without paths; production requires HTTPS.")
    try:
        hsts = int(environ.get("DJANGO_HSTS_SECONDS", "0" if debug else "3600"))
        if hsts < 0:
            raise ValueError
    except ValueError as exc:
        raise ImproperlyConfigured("DJANGO_HSTS_SECONDS must be a nonnegative integer.") from exc
    return {
        "DEBUG": debug,
        "SECRET_KEY": secret or "django-insecure-local-development-only-never-use-this-key-in-production",
        "ALLOWED_HOSTS": hosts or ["localhost", "127.0.0.1", "[::1]"],
        "CSRF_TRUSTED_ORIGINS": origins,
        "SECURE_SSL_REDIRECT": not debug,
        "SESSION_COOKIE_SECURE": not debug,
        "CSRF_COOKIE_SECURE": not debug,
        "SECURE_HSTS_SECONDS": hsts,
        "SECURE_HSTS_INCLUDE_SUBDOMAINS": False,
        "SECURE_HSTS_PRELOAD": False,
        "SECURE_PROXY_SSL_HEADER": ("HTTP_X_FORWARDED_PROTO", "https") if boolean(environ, "DJANGO_TRUST_PROXY_HEADERS", False) else None,
    }
