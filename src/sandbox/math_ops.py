"""Small numeric helpers. Pure functions, a few real edge cases to test."""


def add(a, b):
    return a + b


def mul(a, b):
    return a * b


def mean(xs):
    """Arithmetic mean of a non-empty list. Raises on empty input."""
    if not xs:
        raise ValueError("mean() needs at least one value")
    return sum(xs) / len(xs)


def clamp(x, lo, hi):
    """Clamp x into the closed range [lo, hi]."""
    return max(lo, min(x, hi))
