import contextlib
import logging
from abc import ABC, abstractmethod
from functools import wraps
from types import TracebackType
from typing import Callable, Iterable, Iterator, Self, Type, cast


logger = logging.getLogger(__name__)


class Groupie[T: Exception](contextlib.suppress, ABC):
    """
    Similar to `contextlib.suppress`, but "handles" exception via the `handle_exception` method.

    The `handle_exception` method is abstract and must be implemented by subclasses.

    The
    """

    _exception_types_to_handle: tuple[Type[T], ...]

    def __init__(
        self,
        *exception_types_to_handle: Type[T],
        default=None,
    ):
        self._exception_types_to_handle = exception_types_to_handle
        self.default = default

    @abstractmethod
    def handle_exception(
        self,
        exc: T,
        original_exinfo: tuple[Type[T], T, TracebackType],
    ) -> bool | None:
        """
        Do something with the exception.
        Return True if the exception should be suppressed.
        """

    @classmethod
    def from_handler(
        cls,
        handler: Callable[[T, tuple[Type[T], T, TracebackType]], bool | None],
        *exception_types_to_handle: Type[T],
        default=None,
    ) -> "type[Groupie[T]]":
        class _Grouper(cls):
            def handle_exception(
                self,
                exc: T,
                original_exinfo: tuple[Type[T], T, TracebackType],
            ) -> bool | None:
                return handler(exc, original_exinfo)

        return _Grouper(*exception_types_to_handle, default=default)

    # The following method is copied and modified from contextlib.suppress
    # type errors are reproduced faithfully

    def _will_be__exit__(self, exctype, excinst, exctb):  # type: ignore  # Faithfully reproduce type error
        # Unlike isinstance and issubclass, CPython exception handling
        # currently only looks at the concrete type hierarchy (ignoring
        # the instance and subclass checking hooks). While Guido considers
        # that a bug rather than a feature, it's a fairly hard one to fix
        # due to various internal implementation details. suppress provides
        # the simpler issubclass based semantics, rather than trying to
        # exactly reproduce the limitations of the CPython interpreter.
        # See http://bugs.python.org/issue12029 for more details

        if exctype is None:
            return

        if issubclass(exctype, self._exception_types_to_handle):
            return self.handle_exception(excinst, (exctype, excinst, exctb))

        if issubclass(exctype, BaseExceptionGroup):
            excinst = cast(BaseExceptionGroup, excinst)
            match, rest = excinst.split(self._exception_types_to_handle)

            # If the handler returns False, the original exception group should be allowed to propagate
            # by the context manager's underlying __exit__ method, regardless of whether there are
            # additional unhandled exceptions in the group.
            if not self.handle_exception(match, (exctype, match, exctb)):
                return False

            # If we handled all the exceptions in the group, then we suppress the original exception set
            if rest is None:
                return True

            # If we didn't handle all the exceptions in the group, then we need to re-raise the remaining exceptions
            raise rest

        # If we didn't handle the exception, then let the original exception propagate
        return False

    # The following method is copied and modified from contextlib.ContextDecorator

    def _recreate_cm(self):
        """Return a recreated instance of self.

        Allows an otherwise one-shot context manager like
        _GeneratorContextManager to support use as
        a decorator via implicit recreation.

        This is a private interface just for _GeneratorContextManager.
        See issue https://github.com/python/cpython/issues/55856 for details.
        """
        return self

    def __call__(self, func):
        @wraps(func)
        def inner(*args, **kwds):
            with self._recreate_cm():
                return func(*args, **kwds)
            return self.default

        return inner


# HACK: this is attached outside the class definition because
# linters/type-checkers are typically smart enough to know about,
# contextlib.supress, but key off it's __exit__ method
# By attaching it here, we don't have static analysis complaining
# that code is unreachable when using Pacman and it's subclasses
# to downgrade exceptions
Groupie.__exit__ = Groupie._will_be__exit__  # type: ignore


def iter_leaf_exceptions[T: Exception](ex: T | BaseExceptionGroup[T]) -> Iterable[T]:
    """Iter through all the non-group exceptions as a dfs pre-order"""
    if isinstance(ex, ExceptionGroup):
        for e in ex.exceptions:
            yield from iter_leaf_exceptions(e)
    else:
        yield cast(T, ex)


class Collector[T: Exception](Groupie[T]):
    """
    Collect a group of exceptions and only raise  at the end of execution.
    """

    def __init__(
        self,
        *exception_types: Type[T],
    ) -> None:
        super().__init__(*exception_types)
        self.collected: list[T] = []

        # Set default values for the arguments
        # NOTE: we don't do this in the function signature because
        # we want the defaults to be the same here as in the iter_through_errors
        # function below

    def handle_exception(self, exc: T | BaseExceptionGroup[T], original_exinfo) -> None:
        self.collected.extend(iter_leaf_exceptions(exc))
        return True

    def __iter__(self) -> Iterator[T]:
        return iter(self.collected)


class accumulate[T: Exception]:
    """
    Collect a group of exceptions and only raise  at the end of execution.
    """

    def __init__(
        self,
        *exception_types: Type[T],
        group_message: str | None = None,
    ) -> None:
        self.collector = Collector(*exception_types)
        self.group_message = group_message or ""

    def get_exception_group(self) -> BaseExceptionGroup[T] | None:
        """
        Return an ExceptionGroup of the collected exceptions,
        or None if there are no exceptions.

        Exceptions within the group are considered an ordered set,
        and so are deduplicated.
        """
        if not self.collector.collected:
            return None

        if len(self.collector.collected) == 1:
            return self.collector.collected[0]

        # Use a dict because it's practically an ordered set
        deduped = {ex: None for ex in self.collector.collected}
        return ExceptionGroup(self.group_message, list(deduped.keys()))

    def raise_all(self):
        """
        Raise the collected errors as an exception group.
        """
        if ex := self.get_exception_group():
            raise ex

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args):
        self.raise_all()


class downgrade[T: Exception](Groupie):
    """
    Similar to `contextlib.suppress`, but logs the exception instead.
    Can be used both as a context manager and as a function decorator.
    """

    def __init__(
        self,
        *exception_types: Type[T],
        default=None,
        to_level: int = logging.WARNING,
        logger: logging.Logger = logger,
    ):
        super().__init__(*exception_types, default=default)
        self.to_level = to_level
        self.logger = logger

    def handle_exception(self, exc: T, original_exinfo):
        if isinstance(exc, ExceptionGroup):
            exceptions = exc.exceptions
        else:
            exceptions = [exc]

        for ex in exceptions:
            self.logger.log(self.to_level, str(ex), exc_info=ex)

        return True


class suppress_after_count[T: Exception](Groupie):
    def __init__(
        self,
        limit: int,
        *exception_types: Type[T],
        default=False,
        suppression_warning: str | None = None,
        logger: logging.Logger = logger,
    ):
        super().__init__(*exception_types, default=default)
        self.limit = limit
        self.counter = 0
        self.supression_warning = suppression_warning
        self.logger = logger

    def handle_exception(self, exc: T, original_exinfo):
        self.counter += 1

        if self.counter == self.limit + 1 and self.supression_warning is not None:
            self.logger.warning(self.supression_warning)

        if self.counter <= self.limit:
            return False

        return True


def iter_through_errors[T](
    gen: Iterable[T],
    *accumulate_types: Type,
    group_message: str | None = None,
) -> Iterable[tuple[Callable[[], Collector[T]], T]]:
    """
    Wraps an iterable and yields:
    - a context manager that collects any ato errors
        raised while processing the iterable
    - the item from the iterable
    """

    with accumulate(*accumulate_types, group_message=group_message) as accumulator:
        for item in gen:
            # NOTE: we don't create a single context manager for the whole generator
            # because generator context managers are a bit special
            yield accumulator.collector, item
