"""Read a complete bounded recovery delta without publishing derived state."""


class PreparationRequired(ValueError):
    """The authoritative change feed cannot prove an incremental continuation."""


def capture_changes(tracker, previous, read, *, limit=20000):
    """Return (watermark, detached after-images) only after capture succeeds.

    ``read(plan)`` runs under the existing recovery clock transaction. It must
    read canonical rows and return detached values, never mutate live derived
    state. The caller publishes those values under its existing application lock
    and retains its separate metadata/binding and response-end authority checks.
    No preparation, retry, journal, or mutation authority is introduced here.
    """
    with tracker.capture(previous, limit=limit) as plan:
        if plan is None or not plan.complete:
            raise PreparationRequired('Recovery change coverage requires explicit preparation')
        value=read(plan)
        plan.verify()
        watermark=plan.watermark
    if tracker.token()!=watermark:
        raise PreparationRequired('Recovery state changed after capture')
    return watermark,value
