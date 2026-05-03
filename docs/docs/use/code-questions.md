# Ask code questions

Start with a symbol, file, repository, or phrase. PCG works best when the
question names the thing you want to inspect.

## CLI examples

```bash
pcg analyze callers process_payment
pcg analyze calls process_payment
pcg analyze dead-code
pcg stats
```

These commands call the API. If you are running locally, start Docker Compose
or another API process first. The local Compose API defaults to
`http://localhost:8080`.

## MCP examples

Ask your assistant questions like:

- "Find `process_payment` and show me where it is defined."
- "Who calls this function across indexed repos?"
- "Show the shortest call chain from `main` to this handler."
- "Find dead code candidates in this repository."
- "Which files import this package?"
- "What is the blast radius if this module changes?"

Ask for evidence when you need to make a decision:

> Use PCG. Search the indexed repos, show the files and symbols involved, and
> explain what evidence supports the answer.

## When to use reference

Use [CLI Reference](../reference/cli-reference.md) when you know the command and
need flags or exact syntax. Use this page when you are still figuring out what
to ask.
