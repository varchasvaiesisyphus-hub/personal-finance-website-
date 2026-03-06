import logging
import threading

from django.db import close_old_connections
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.models import Transaction

logger = logging.getLogger(__name__)


def _run_pipeline(user_id: int) -> None:
    close_old_connections()   # SQLite: each thread needs its own connection
    try:
        from ai_pipeline.insights import generate_insights_for_user
        result = generate_insights_for_user(user_id)
        logger.info("AI pipeline result for user %s: %s", user_id, result)
    except Exception:
        logger.exception("AI pipeline failed for user %s", user_id)
    finally:
        close_old_connections()


@receiver(post_save, sender=Transaction)
def transaction_saved(sender, instance, **kwargs):
    threading.Thread(
        target=_run_pipeline, args=(instance.user_id,), daemon=True
    ).start()


@receiver(post_delete, sender=Transaction)
def transaction_deleted(sender, instance, **kwargs):
    threading.Thread(
        target=_run_pipeline, args=(instance.user_id,), daemon=True
    ).start()