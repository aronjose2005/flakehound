"""Pretend application code — the kind of module a real test imports."""
import random


def get_recommendation(user):
    # BUG: non-deterministic — sometimes returns a blocked item
    options = ["video_a", "video_b", "blocked_item"]
    return random.choice(options)