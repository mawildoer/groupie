from unittest.mock import MagicMock

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


def test_downgrade_context():
    logger = MagicMock()
    with downgrade(ValueError, logger=logger):
        raise ValueError()

    with pytest.raises(TypeError):
        with downgrade(ValueError, logger=logger):
            raise TypeError()

    logger.log.assert_called_once()


def test_downgrade_context_custom_exception():
    logger = MagicMock()

    class CustomException(Exception):
        pass

    with downgrade(CustomException, logger=logger):
        raise CustomException()

    with pytest.raises(Exception):
        with downgrade(CustomException, logger=logger):
            raise Exception()

    logger.log.assert_called_once()


def test_downgrade_context_multiple_exceptions():
    logger = MagicMock()
    with downgrade(ValueError, TypeError, logger=logger):
        raise ValueError()

    logger.log.assert_called_once()

    with pytest.raises(Exception):
        with downgrade(ValueError, TypeError, logger=logger):
            raise Exception()

    logger.log.assert_called_once()

    with downgrade(ValueError, TypeError, logger=logger):
        raise TypeError()


def test_downgrade_decorator():
    logger = MagicMock()

    @downgrade(ValueError, logger=logger)
    def foo():
        raise ValueError()

    a = foo()
    assert a is None
    logger.log.assert_called_once()


def test_downgrade_decorator_with_default():
    logger = MagicMock()

    @downgrade(ValueError, default=2, logger=logger)
    def foo():
        raise ValueError()

    a = foo()
    assert a == 2
    logger.log.assert_called_once()


def test_suppress_after_count():
    logger = MagicMock()
    suppressor = suppress_after_count(
        3, ValueError, suppression_warning="test warning", logger=logger
    )
    for _ in range(3):
        with pytest.raises(ValueError), suppressor:
            raise ValueError()

    logger.warning.assert_not_called()

    with suppressor:
        raise ValueError()

    logger.warning.assert_called_once()


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
