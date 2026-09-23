# design/

- `architecture.dot` / `architecture.png` — layered system architecture
  (presentation, application/module, shared services, data layers).
- `erd.dot` / `erd.png` — entity-relationship diagram for the core schema in
  `database/schema.sql`.

Diagrams are generated with Graphviz (`dot -Tpng architecture.dot -o
architecture.png`) so they stay reproducible from source rather than being
hand-edited images.
