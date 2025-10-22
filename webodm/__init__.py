"""WebODM package initialization."""

# Some third-party packages still rely on the deprecated ``ugettext_lazy``
# symbol that was removed in Django 4+. Import errors from these packages
# prevent the project from starting up, so we provide the legacy alias here
# if Django no longer exposes it.
try:  # pragma: no cover - defensive patching
    from django.utils import translation

    if not hasattr(translation, "ugettext_lazy"):
        from django.utils.translation import gettext_lazy

        translation.ugettext_lazy = gettext_lazy  # type: ignore[attr-defined]
except Exception:
    # The import above may fail when Django is not available (for example
    # during packaging) – in that case we simply skip the compatibility shim.
    pass

