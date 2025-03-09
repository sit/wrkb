# Development Environment and Tools

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

We generally prefer technologies that can be run locally on macOS (e.g., MBP M1Pro)
with options to run in the cloud. If we build something to be deployed, we will use
GCP.