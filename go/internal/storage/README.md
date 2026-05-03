# Storage

`storage` contains the concrete persistence adapters for PCG.

Postgres stores facts, queue state, content, status, and recovery data. Cypher
packages define backend-neutral graph write contracts. Neo4j and NornicDB
compatibility must stay behind documented graph ports and dialect seams.
