"""Small string helpers. Pure functions, a few real edge cases to test."""


def shout(s):
    return s.upper()


def reverse(s):
    return s[::-1]


def slugify(s):
    """Lowercase, keep alphanumerics, join words with hyphens."""
    words = "".join(c if c.isalnum() else " " for c in s.lower()).split()
    return "-".join(words)


def truncate(s, n):
    """Return s unchanged if it fits in n chars, else cut to n with a '...'."""
    if n < 1:
        raise ValueError("truncate() needs n >= 1")
    return s if len(s) <= n else s[:n] + "..."
