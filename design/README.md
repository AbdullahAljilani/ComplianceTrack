# design/

* `architecture.dot` / `architecture.png`
  Layered system architecture showing the presentation, application/module, shared services, and data layers.

* `erd.dot` / `erd.png`
  Entity-relationship diagram for the core database schema in `database/schema.sql`.

The diagrams are generated using Graphviz:

`dot -Tpng architecture.dot -o architecture.png`

This allows the diagrams to be regenerated from the source files when changes are made.
