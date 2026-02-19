# Working in wr

## Philosophy

We prefer to use localized tools that are targeted into this repository as much
as possible. So using `dev` from https://pkgx.sh/ to load in the right versions
of things.

When writing Python code, we want to use `uv` to keep the right versions of
Python localized into the specific repositories. Python should be preferred for any
purpose specific tools (e.g., web crawling, data processing).

When writing front-end, we want to use https://astro.build/ with `pnpm` and Svelte.
We will write code in TypeScript.

If communication between Python and front-end is necessary, we should make
technology choices (e.g., for databases) that have well-supported language
bindings in both Python and Node.

If we build something to be deployed, we will use GCP.

## Coding Guidelines

Strive for maintainable code and appropriate abstractions.
TDD when possible.

Keep the following in mind
- Type hints: use type hints in Python and TS to provide static checking
- Comments: use comments to explain why and non-obvious information, otherwise omit them
- Docstrings: use docstrings to document public interfaces

When writing Python code:
- Environment and dependency management: you use uv to manage dependencies and
  run scripts: `uv run SCRIPT ARGS` and `uv add DEPENDENCY` instead of `python
  SCRIPT ARGS` and `pip install DEPENDENCY`.
- After completing all edits, use `uvx ruff check --fix` to fix any lint errors
  and `uvx ruff format` to reformat code.
- Testing: you write tests for your code, and use pytest to run them: `uv run
  pytest tests/TEST_FILE.py`.

When writing Typescript code:
- Environment and dependency management: you use pnpm to manage dependencies, not npm.
