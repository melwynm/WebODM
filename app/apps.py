from django.apps import AppConfig


class MainConfig(AppConfig):
    name = 'app'
    verbose_name = 'Application'

    def ready(self):
        # Pillow 10+ removed Image.ANTIALIAS, but pilkit 2 still references it.
        try:
            from PIL import Image
            if not hasattr(Image, "ANTIALIAS") and hasattr(Image, "Resampling"):
                Image.ANTIALIAS = Image.Resampling.LANCZOS
        except Exception:
            pass
