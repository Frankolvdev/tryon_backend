from functools import wraps
from threading import Lock

_generation_lock = Lock()
_ERROR = "No es posible ejecutar dos generaciones de Body Proportions/Bubble Butt al mismo tiempo."


def single_body_proportion_generation(function):
    """Non-blocking process-local guard shared by Body Proportions and Bubble Butt."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        if not _generation_lock.acquire(blocking=False):
            raise ValueError(_ERROR)
        try:
            return function(*args, **kwargs)
        finally:
            _generation_lock.release()
    return wrapped
