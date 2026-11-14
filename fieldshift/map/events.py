"""Tiny callback list, so the abstraction does not depend on Qt signals."""


# list of callbacks fired together; used for every MapView notification
class Event:

    # ()
    # creates an event with no subscribers
    def __init__(self):
        self._callbacks = []

    # (callable callback)
    # registers a callback; returns it so it can be used as a decorator
    def connect(self, callback):
        self._callbacks.append(callback)
        return callback

    # (callable callback)
    # removes a callback registered with connect; unknown callbacks are ignored
    def disconnect(self, callback):
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    # (any *args, any **kwargs)
    # calls every subscriber with the given arguments, in subscription order
    def emit(self, *args, **kwargs):
        for callback in list(self._callbacks):
            callback(*args, **kwargs)
