"""Stable persistence errors exposed to services and API translation."""


class PersistenceError(RuntimeError):
    """Base class for failures independent of a storage vendor."""


class NotFoundError(PersistenceError):
    pass


class ConflictError(PersistenceError):
    pass


class ValidationError(PersistenceError):
    pass


class ThrottledError(PersistenceError):
    pass


class UnavailableError(PersistenceError):
    pass
