"""
geometry_correction/plugin.py
WebODM Plugin entry point.
"""

from app.plugins import PluginBase, Menu, MountPoint


class Plugin(PluginBase):
    """
    GeometryCorrection Plugin
    Adds AI-assisted geometric correction (RANSAC plane-snapping +
    Hough-line orthomosaic alignment) to WebODM tasks as a post-processing step.
    """

    def main_menu(self):
        return [
            Menu(
                "Geometry Correction",
                "/plugins/geometry_correction/",
                "fa fa-drafting-compass",
            )
        ]

    def include_js_files(self):
        return ["main.js"]

    def include_css_files(self):
        return []

    def build_jsx_components(self):
        return []

    def api_mount_points(self):
        from .views import router
        return [MountPoint("geometry_correction/", router)]
