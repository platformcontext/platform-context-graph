# Cypher Storage

`storage/cypher` owns backend-neutral graph write contracts, canonical writers,
edge helpers, statement metadata, and write instrumentation.

Dialect-specific behavior should stay narrow and explicit. Do not spread
`neo4j` or `nornicdb` conditionals through caller packages when a schema adapter,
writer option, or query builder can own the difference.
