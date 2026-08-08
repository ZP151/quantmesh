# Tests are a package so helper modules (moomoo_wire, research_fixtures,
# ...) import as `from tests.<module> import ...`. Without this marker the
# imports only resolve under `python -m pytest` (which puts the repo root
# on sys.path) and fail under the bare `pytest` CI invocation.
