"""Pipeline live visualization components."""

from rich.progress import Progress


def get_pipeline_progress() -> Progress:
    return Progress()
