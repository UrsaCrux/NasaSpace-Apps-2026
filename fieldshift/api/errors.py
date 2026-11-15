"""Why data could not be downloaded, in words the UI can show.

    try:
        ...
    except Exception as exc:
        raise classify(exc, "NASA POWER") from exc

The UI shows tr(f"errors.{error.kind}", detail=error.detail) and lets the
user try again; it never shows made-up numbers instead.
"""

# kinds of failure
NO_CONNECTION = "no_connection"     # no internet / the server cannot be reached
TIMEOUT = "timeout"                 # the server took too long
FAILED = "failed"                   # the server answered with an error
NO_DATA = "no_data"                 # the server has nothing for this place / time
OFFLINE = "offline"                 # the app runs with FIELDSHIFT_OFFLINE=1


# a failed download: kind (one of the above), the source ("NASA POWER") and
# a short detail ("HTTP 503")
class DataError(Exception):

    # (str kind, str source = "", str detail = "")
    def __init__(self, kind, source="", detail=""):
        super().__init__(f"{source}: {kind} {detail}".strip())
        self.kind = kind
        self.source = source
        self.detail = detail


# (Exception exc, str source = "")
# the DataError that explains exc (a DataError is returned as it is, with
# its source filled in when it had none)
def classify(exc, source=""):
    if isinstance(exc, DataError):
        if not exc.source and source:
            exc.source = source
        return exc
    try:
        import requests
    except ImportError:                  # pragma: no cover - requests is a dependency
        requests = None
    if requests is not None:
        if isinstance(exc, requests.Timeout):
            return DataError(TIMEOUT, source)
        if isinstance(exc, requests.ConnectionError):
            return DataError(NO_CONNECTION, source)
        if isinstance(exc, requests.HTTPError):
            code = exc.response.status_code if exc.response is not None else ""
            return DataError(FAILED, source, f"HTTP {code}".strip())
    if isinstance(exc, TimeoutError):
        return DataError(TIMEOUT, source)
    if isinstance(exc, (ConnectionError, OSError)):
        return DataError(NO_CONNECTION, source)
    if type(exc).__name__ == "NoData":
        return DataError(NO_DATA, source)
    return DataError(FAILED, source, type(exc).__name__)
