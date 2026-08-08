"""Small list helpers. Pure functions, a few real edge cases to test."""


def head(xs):
    return xs[0]


def tail(xs):
    return xs[1:]


def chunk(xs, size):
    """Split xs into lists of at most `size`. Raises if size < 1."""
    if size < 1:
        raise ValueError("chunk() needs size >= 1")
    return [xs[i:i + size] for i in range(0, len(xs), size)]


def dedupe(xs):
    """Drop duplicates, keeping first-seen order."""
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
