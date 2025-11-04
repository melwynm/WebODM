from django.apps import AppConfig


def _ensure_pillow_antialias_alias():
    """Backwards compatibility for Pillow >= 10 where ANTIALIAS was removed."""

    try:
        from PIL import Image
    except Exception:  # pragma: no cover - Pillow missing or broken
        return

    resampling = getattr(Image, "Resampling", None)
    if resampling is None:
        return

    if not hasattr(Image, "ANTIALIAS"):
        # ANTIALIAS mapped to LANCZOS for Pillow < 10
        setattr(Image, "ANTIALIAS", resampling.LANCZOS)


class MainConfig(AppConfig):
    name = 'app'
    verbose_name = 'Application'

    def ready(self):
        _ensure_pillow_antialias_alias()
