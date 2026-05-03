# Parser

`parser` owns language adapters, parser registration, SCIP reduction support, and
source-level entity extraction.

Parser changes must preserve fact truth. When a parser emits a new entity,
relationship, or metadata field, update the relevant fixtures, fact contracts,
and downstream docs in the same branch.
