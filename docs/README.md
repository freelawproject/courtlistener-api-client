# Developer Documentation

## Install

```sh
uv sync --extra dev
```

## Lint

```sh
uv run pre-commit run --all-files
```

## Type check

```sh
uv run mypy
```

## Test

```sh
uv run tox
```

With integration tests (hits the live API; needs `COURTLISTENER_API_TOKEN`):

```sh
uv run tox -- --run-integration
```
