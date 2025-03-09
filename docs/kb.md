# WR KB Storage and Access

The main goal of our KB format is to enable the most flexible use
of knowledge.

Knowledge about core game data such as champions, items and runes need
to be stored so that we can expose it to LLMs in a structured way.
Information about tactics, strategies, concepts, mindsets, etc may have
some basic metadata (e.g., level of skill, prereqs, source) but are
not as structured as champion data (e.g., who all have abilities with cost,
cooldowns, etc).

Knowledge items are stored in Markdown format with structured metadata in
front matter. Metadata is structured so that it can be easily consumed
by tools such as https://markdowndb.com/ or exposed using Astro Content
Collections (zod). Markdown makes it easy to manage in source control
systems and ramp up collaborators who are only moderately technical.

We may index or build other secondary storage formats for this data
to support various use cases (e.g., a embeddings stored in a vector database).