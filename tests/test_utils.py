import logging

import pytest

from groupie import (
    accumulate,
    downgrade,
    iter_leaf_exceptions,
    iter_through_errors,
    suppress_after_count,
)


def test_accumulate():
    with pytest.raises(ValueError):
        with accumulate() as accumulator:
            with accumulator.collector:
                raise ValueError("test error")

            raise ValueError("test error 2")


def test_iter_through_errors():
    try:
        for cltr, i in iter_through_errors(range(4), ValueError):
            with cltr:
                if i == 1:
                    raise ValueError("test error")
                if i == 2:
                    raise ValueError("test error 2")

    except ExceptionGroup as ex:
        assert len(ex.exceptions) == 2
        ex_1, ex_2 = ex.exceptions
        assert str(ex_1) == "test error"
        assert str(ex_2) == "test error 2"

    else:
        raise AssertionError("Expected an ExceptionGroup to be raised")


def test_downgrade_context(caplog):
    with caplog.at_level(logging.WARNING, logger="groupie"):
        with downgrade(ValueError):
            raise ValueError()

        with pytest.raises(TypeError):
            with downgrade(ValueError):
                raise TypeError()

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "WARNING"


def test_downgrade_context_custom_exception(caplog):
    class CustomException(Exception):
        pass

    with caplog.at_level(logging.WARNING, logger="groupie"):
        with downgrade(CustomException):
            raise CustomException()

        with pytest.raises(Exception):
            with downgrade(CustomException):
                raise Exception()

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "WARNING"


def test_downgrade_context_multiple_exceptions(caplog):
    with caplog.at_level(logging.WARNING, logger="groupie"):
        with downgrade(ValueError, TypeError):
            raise ValueError()

        assert len(caplog.records) == 1

        with pytest.raises(Exception):
            with downgrade(ValueError, TypeError):
                raise Exception()

        assert len(caplog.records) == 1

        with downgrade(ValueError, TypeError):
            raise TypeError()

    assert len(caplog.records) == 2


def test_downgrade_decorator(caplog):
    with caplog.at_level(logging.WARNING, logger="groupie"):

        @downgrade(ValueError)
        def foo():
            raise ValueError()

        a = foo()
        assert a is None

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "WARNING"


def test_downgrade_decorator_with_default(caplog):
    with caplog.at_level(logging.WARNING, logger="groupie"):

        @downgrade(ValueError, default=2)
        def foo():
            raise ValueError()

        a = foo()
        assert a == 2

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "WARNING"


def test_suppress_after_count(caplog):
    with caplog.at_level(logging.WARNING, logger="groupie"):
        suppressor = suppress_after_count(3, ValueError, suppression_warning="test warning")
        for _ in range(3):
            with pytest.raises(ValueError), suppressor:
                raise ValueError()

        assert len(caplog.records) == 0

        with suppressor:
            raise ValueError()

    assert len(caplog.records) == 1
    assert "test warning" in caplog.text
    assert caplog.records[0].levelname == "WARNING"


def test_iter_leaf_exceptions():
    ex = ExceptionGroup(
        "test",
        [
            Exception("test 1"),
            ExceptionGroup("test 2", [Exception("test 2.1"), Exception("test 2.2")]),
        ],
    )
    assert [ex.args[0] for ex in iter_leaf_exceptions(ex)] == [
        "test 1",
        "test 2.1",
        "test 2.2",
    ]
