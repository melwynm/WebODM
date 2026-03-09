import datetime
import math
import logging
import time
from django import template
from webodm import settings
from django.utils.translation import gettext as _
from app.models import Setting, Theme

register = template.Library()
logger = logging.getLogger('app.logger')

_DEFAULT_THEME = Theme(name='Default')


def _resolve_settings(context):
    settings_obj = None

    if context is not None:
        try:
            settings_obj = context.get('SETTINGS')
        except Exception:
            try:
                settings_obj = context['SETTINGS']
            except Exception:
                settings_obj = None

    if settings_obj is None:
        try:
            settings_obj = Setting.objects.select_related('theme').first()
        except Exception as e:
            logger.warning("Cannot load settings from database: %s" % str(e))
            settings_obj = None

    return settings_obj


@register.simple_tag
def task_options_docs_link():
    return settings.TASK_OPTIONS_DOCS_LINK


@register.simple_tag
def gcp_docs_link():
    return '<a href="%s" target="_blank">' % settings.GCP_DOCS_LINK


@register.simple_tag
def reset_password_link():
    return settings.RESET_PASSWORD_LINK


@register.simple_tag
def has_external_auth():
    return settings.EXTERNAL_AUTH_ENDPOINT != ""


@register.filter
def disk_size(megabytes):
    k = 1000
    k2 = k ** 2
    k3 = k ** 3
    if megabytes <= k2:
        return str(round(megabytes / k, 2)) + ' GB'
    elif megabytes <= k3:
        return str(round(megabytes / k2, 2)) + ' TB'
    else:
        return str(round(megabytes / k3, 2)) + ' PB'


@register.simple_tag
def percentage(num, den, maximum=None):
    if den == 0:
        return 100
    perc = max(0, num / den * 100)
    if maximum is not None:
        perc = min(perc, maximum)
    return perc


@register.simple_tag(takes_context=True)
def quota_exceeded_grace_period(context):
    deadline = context.request.user.profile.get_quota_deadline()
    now = time.time()
    if deadline is None:
        deadline = now + settings.QUOTA_EXCEEDED_GRACE_PERIOD * 60 * 60
    diff = max(0, deadline - now)
    if diff >= 60*60*24*2:
        return _("in %(num)s days") % {"num": math.floor(diff / (60*60*24))}
    elif diff >= 60*60*2:
        return _("in %(num)s hours") % {"num": math.floor(diff / (60*60))}
    elif diff > 1:
        return _("in %(num)s minutes") % {"num": math.floor(diff / 60)}
    else:
        return _("very soon")


@register.simple_tag
def is_single_user_mode():
    return settings.SINGLE_USER_MODE


@register.simple_tag
def is_desktop_mode():
    return settings.DESKTOP_MODE


@register.simple_tag
def is_dev_mode():
    return settings.DEV


@register.simple_tag(takes_context=True)
def settings_image_url(context, image):
    settings_obj = _resolve_settings(context)
    if settings_obj is None:
        logger.warning("Cannot get SETTINGS object. Cannot resolve image URL.")
        return ''

    try:
        img_cache = getattr(settings_obj, image)
    except Exception as e:
        logger.warning("Cannot get %s from settings: %s" % (image, str(e)))
        return ''

    try:
        return "/media/" + img_cache.url
    except FileNotFoundError:
        logger.warning("Cannot get %s, this could mean the image was deleted." % image)
        return ''


@register.simple_tag(takes_context=True)
def get_footer(context):
    settings_obj = _resolve_settings(context)
    if settings_obj is None:
        logger.warning("Cannot get SETTINGS object. The footer will not be displayed.")
        return ""

    if settings_obj.theme is None or settings_obj.theme.html_footer == "":
        return ""

    organization = ""
    if settings_obj.organization_name != "" and settings_obj.organization_website != "":
        organization = "<a href='{}'>{}</a>".format(settings_obj.organization_website, settings_obj.organization_name)
    elif settings_obj.organization_name != "":
        organization = settings_obj.organization_name

    footer = settings_obj.theme.html_footer
    footer = footer.replace("{ORGANIZATION}", organization)
    footer = footer.replace("{YEAR}", str(datetime.datetime.now().year))

    return "<footer>" + footer + "</footer>"


@register.simple_tag(takes_context=True)
def theme(context, color):
    """Return a theme color from the currently selected theme"""
    settings_obj = _resolve_settings(context)
    if settings_obj is not None and settings_obj.theme is not None:
        try:
            value = getattr(settings_obj.theme, color)
            if value:
                return value
        except Exception as e:
            logger.warning("Cannot load configuration from theme(): " + str(e))

    value = getattr(_DEFAULT_THEME, color, None)
    if value:
        return value

    return "#1f2937"


@register.simple_tag
def complementary(hexcolor):
    """Returns complementary RGB color
    Example: complementaryColor('#FFFFFF') --> '#000000'
    """
    if hexcolor[0] == '#':
        hexcolor = hexcolor[1:]
    rgb = (hexcolor[0:2], hexcolor[2:4], hexcolor[4:6])
    comp = ['%02X' % (255 - int(a, 16)) for a in rgb]
    return '#' + ''.join(comp)


@register.simple_tag
def scaleby(hexcolor, scalefactor, ignore_value=False):
    """
    Scales a hex string by ``scalefactor``, but is color dependent, unless ignore_value is True
    scalefactor is now always between 0 and 1. A value of 0.8
    will cause bright colors to become darker and
    dark colors to become brigther by 20%
    """

    def calculate(hexcolor, scalefactor):
        """
        Scales a hex string by ``scalefactor``. Returns scaled hex string.
        To darken the color, use a float value between 0 and 1.
        To brighten the color, use a float value greater than 1.

        >>> colorscale("#DF3C3C", .5)
        #6F1E1E
        >>> colorscale("#52D24F", 1.6)
        #83FF7E
        >>> colorscale("#4F75D2", 1)
        #4F75D2
        """

        def clamp(val, minimum=0, maximum=255):
            if val < minimum:
                return minimum
            if val > maximum:
                return maximum
            return int(val)

        hexcolor = hexcolor.strip('#')

        if scalefactor < 0 or len(hexcolor) != 6:
            return hexcolor

        r, g, b = int(hexcolor[:2], 16), int(hexcolor[2:4], 16), int(hexcolor[4:], 16)

        r = clamp(r * scalefactor)
        g = clamp(g * scalefactor)
        b = clamp(b * scalefactor)

        return "#%02x%02x%02x" % (r, g, b)


    hexcolor = hexcolor.strip('#')
    scalefactor = abs(float(scalefactor))
    scalefactor = min(1.0, max(0, scalefactor))

    r, g, b = int(hexcolor[:2], 16), int(hexcolor[2:4], 16), int(hexcolor[4:], 16)
    value = max(r, g, b)

    return calculate(hexcolor, scalefactor if ignore_value or value >= 127 else 2 - scalefactor)


@register.simple_tag
def scalebyiv(hexcolor, scalefactor):
    return scaleby(hexcolor, scalefactor, True)
