# `groupie` is a module for useful `ExceptionGroup`s

Exceptions in Python can be a very neat way of controling program flow. ExceptionGroups (with an assist from groupie) simplify more complex control flow.

It's features include:
- Collect exceptions using a context, like `contextlib.suppress` - but collect them up
- `accumulate` exceptions into one big `ExceptionGroup` to be raised at once
- `downgrade` exceptions to warnings presented via `logging`
- Static analysis (eg. `ruff`) compatability notices when you're supressing errors

Think of using this when:
- Parsing configuration files / objects
- Parsing code
- Building a bunch of targets


## Useful Patterns

### Surface as many user-facing issues as possible at once

It's super annoying as a user to get drip-fed one issue at a time, especially when there's some intensive process leading up to the failure (imagine if `pytest` stopped at the first failed test each time it was run).

Raise these exceptions for any branch of logic that will individually stop execution, but accumulating these before raising them means that all possible branches are explored as deeply as possible before surfacing the issue.

eg.
```python
time_consuming_setup()

with accumulate(ValueError) as accumulator:
    with accumulator.collector:
        do_one()  # <-- say this fails, we'd usually never know if two and three were going to work!
    with accumulator.collector:
        do_two()
    with accumulator.collector:
        do_three()  # <-- this fails as well!
```

This will yield an `ExceptionGroup` showing both `do_one` and `do_three` failed at the same time!


### Accumulating exceptions in a loop

Because it's so common, there are special methods to condense the boilerplate of accumulating exceptions in a loop.

```python
for collector, item in accumulate(range(10), ValueError):
    with collector:
        do_something(item)
```

Then the exception group will contain all the exceptions raised in the loop.

### `downgrade`ing Exceptions

Say you've deprecated something, but you want to surface it as a warning, later to be promoted to an error:

```python
def do_something():
    with downgrade(DeprecationException):
        raise DeprecationException("This is deprecated - to the other thing.")

    # but, for now, do it anyway...
```

### Attempting to do something a few ways, failing only if none succeed

A common pattern for a user-facing application is to attempt to do something - perhaps load a configuration file - a few different ways, and only fail if none succeed.

Say you allow the configuration file for a tool to exist in a few places.

```python
def load_config():
    possible_locations = [
        "~/.config/my-tool/config.json",
        "./config.json",
        "/etc/my-tool/config.json",
    ]
    collector = Collector(FileNotFoundError)
    for location in possible_locations:
        with collector:
            return load_config_from_file(location)

    # If we haven't already returned, raise an exception describing
    # all the failures we encountered while trying.
    collector.raise_all()
```

NOTE: the difference `accumulate` and `Collector`:
- `accumulate` is a context manager that accumulates the exceptions into a single one, and then raises it when exiting the context. It's useful to ensure you definately raise the exception and makes it really hard to miss a check on whether there were any.
- The `Collector` is a context manager that collects the exceptions, but it's up to you to handle them (possibly raise them) when you're done with it.


### Custom `UserException` tree

One very useful pattern is to create a tree of `Exception` types under the standard included types and use them to represent user-facing issues.

```python
class UserException(Exception):
    """Represents a user-facing exception"""

class UserResourceException(UserException):
    """You have a file missing!"""

# etc...
```

This is particulaly useful because you can pass the `UserException` type to all the `accumulate` calls around your code.

You can also add pretty printing to these exceptions (check out [`rich`](https://github.com/Textualize/rich)!) with something like:

```python
class UserException(Exception):
    """Represents a user-facing exception"""

    def __str__(self):
        return f"{self.__class__.__name__}: {self.__doc__}"
```

## Attribution

These utils and patternsstarted life as part of [`atopile`](https://github.com/atopile/atopile), a compiler to design PCBAs with code
