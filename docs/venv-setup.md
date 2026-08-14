# Virtual Environment Setup

Everything Python in this project runs out of `venv/` at the repository root. The
Makefile calls `venv/bin/pip` and `venv/bin/python` by name rather than relying on
an activated shell, so a bare `pip install` in the wrong environment cannot leave
the venv half-populated.

**Python 3.10 or newer is required** — `fastmcp` 3 does not install on anything
older, and pip's failure says nothing about the Python version when it happens.
Development and CI both run 3.14.

## Create it

```bash
make install   # venv/ plus the server dependencies
make setup     # the same, plus the test dependencies and the test import symlinks
```

Both create `venv/` if it is missing. To build it against a specific interpreter,
pass one: `make setup PYTHON=python3.12`.

The equivalent by hand:

```bash
python3 -m venv venv
venv/bin/pip install -r server/requirements.txt
venv/bin/pip install -r tests/requirements.txt   # only if you are running the suite
```

## What gets installed

| Package | From | Why |
|---|---|---|
| websockets | server | The socket between server and extension |
| fastmcp | server | Serves the MCP tools |
| uvicorn | server | HTTP transport under FastMCP |
| pydantic | server | Tool argument models |
| pytest, pytest-asyncio, pytest-mock, pytest-cov | tests | The suite |
| coverage | tests | Coverage reports in `tests/htmlcov/` |
| aiohttp | tests | HTTP client the request-monitoring tests drive traffic with |

Versions in the project venv, verified 2026-08-12: websockets 17.0.1, fastmcp
3.4.7, pytest 9.1.1, pytest-asyncio 1.4.0, pytest-mock 3.15.1, pytest-cov 7.1.0,
coverage 7.15.4, aiohttp 3.14.3.

## Use it

```bash
venv/bin/python server/server.py          # start the server
cd tests && ../venv/bin/python run_tests.py   # run the suite, as make test does
```

Activating the venv (`source venv/bin/activate`) works too and is what
`start-foxmcp.sh` does, but nothing in the repository depends on it.

## Check it

```bash
venv/bin/python -c "import fastmcp, websockets, uvicorn, pydantic; print('server deps ok')"
venv/bin/python -m pytest --version
```

If a test run reports `No module named pytest`, the venv has the server
dependencies but not the test ones: run `make setup`. If imports fail inside
`tests/unit/` or `tests/integration/`, the symlinks are missing: run
`make setup-test-imports`.
