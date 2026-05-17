import logging


logger = logging.getLogger('app.logger')


def log_feature_validation_change(feature, user=None, previous_status=None):
    username = getattr(user, 'username', None) or 'system'
    if previous_status and previous_status != feature.status:
        logger.info(
            "Feature validation changed: key=%s status=%s previous_status=%s user=%s",
            feature.key,
            feature.status,
            previous_status,
            username,
        )
    else:
        logger.info(
            "Feature validation recorded: key=%s status=%s user=%s",
            feature.key,
            feature.status,
            username,
        )
