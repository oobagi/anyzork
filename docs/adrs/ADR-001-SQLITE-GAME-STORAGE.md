# ADR-001: SQLite as Game Storage Format

> **Status: Superseded.** As of the game projects refactor, `.zork` files are zip archives
> containing `manifest.toml` + `.zorkscript` source files. SQLite is now used internally
> as a compilation cache (`~/.anyzork/cache/*.db`) and for save files (`~/.anyzork/saves/`).

## Status

Accepted (see superseded notice above)

## Context

AnyZork compiles LLM-authored ZorkScript into complete text adventure games and then runs them with a deterministic engine. We need a storage format for the compiled game world -- rooms, exits, items, NPCs, commands (DSL rules), quests, triggers, and mutable player state.

The storage format affects nearly every part of the system:

- **Import/validation**: compiling authored ZorkScript must be able to create the full world safely, and validation needs to inspect the entire world for cross-referential integrity.
- **Game engine**: reads room data, items, and DSL commands on every player turn. Writes player state (position, inventory, flags, score) after every command.
- **Distribution**: generated games should be shareable. A player should be able to receive a game file and play it without setup.
- **Save/load**: players expect to save progress and resume later.

Constraints:
- Python 3.11+ (so anything in the standard library is effectively free)
- Games are single-player, local-only
- Game worlds are small-to-medium data (hundreds of rows, not millions)
- The `.zork` file format is a defining feature of the product -- it should feel simple and portable

## Alternatives Considered

### JSON Files

Store each game as a single JSON file (or a directory of JSON files, one per entity type).

**Pros:**
- Human-readable, easy to inspect and debug
- No dependencies (Python's `json` module is built-in)
- Simple to serialize/deserialize
- Easy to diff and version control

**Cons:**
- No transactional writes. If import crashes mid-compile, the file may be partially written and corrupt. We'd need to implement write-ahead logging or temp-file-swap ourselves.
- No referential integrity. Nothing prevents an exit from pointing to a nonexistent room except our own validation code. The storage format doesn't help us.
- Mutable player state mixed with immutable world data. Either we modify the same file (risking corruption of world data during play) or split into two files (complicating the "one file = one game" model).
- No indexing. Finding "all items in room X" requires scanning the entire items array. Fine for small games, but unnecessarily slow and inelegant.
- Concurrent reads during narrator mode require file locking or accepting stale reads.
- Loading an entire game into memory on startup, even if the player only visits a fraction of rooms.

### PostgreSQL / External Database

Run a PostgreSQL (or MySQL) server and store games as rows in shared tables.

**Pros:**
- Full relational database with strong integrity guarantees
- Excellent tooling, query capabilities, and indexing
- Could support multiplayer or online features in the future
- Battle-tested concurrency model

**Cons:**
- Requires a running database server. This is a CLI tool for generating and playing text adventures -- requiring `docker-compose up` or a managed database is a massive usability barrier.
- Games are not portable. You can't email someone a game. You'd need export/import tooling that essentially recreates the "single file" experience anyway.
- Overkill for the data volume. A text adventure has hundreds of rows across a handful of tables. PostgreSQL's overhead (connection pooling, authentication, WAL management) buys nothing at this scale.
- Deployment complexity contradicts the product's simplicity goals.

### Custom Binary Format

Design a bespoke binary format (e.g., a header + packed records, or a FlatBuffers/MessagePack structure).

**Pros:**
- Maximum control over the format
- Potentially the most compact representation
- Could be optimized for the exact access patterns we need

**Cons:**
- Significant development cost for format design, serialization, deserialization, and versioning
- No query capability -- every access pattern must be hand-coded
- No transactional writes without implementing our own journaling
- No tooling -- no way to inspect game files without building a custom viewer
- Schema migration is entirely manual
- We'd be maintaining a file format instead of building a game engine

## Decision

Use **SQLite** as the game storage format. Each generated game is a single `.zork` file, which is a SQLite database.

SQLite is included in Python's standard library (`sqlite3` module) -- zero additional dependencies. A `.zork` file is a single regular file that can be copied, moved, emailed, or put on a USB stick.

Specifically:

- **One file = one game.** The `.zork` extension is just convention; the file is a standard SQLite database that any SQLite client can open.
- **Schema enforced by SQLite.** Tables, column types, NOT NULL constraints, and FOREIGN KEY constraints are declared in SQL and enforced by the database engine. An exit cannot reference a nonexistent room.
- **Transactions for import.** Compilation and validation can run inside transactions. If import fails, `ROLLBACK` restores the database to a clean state. No custom crash-recovery logic needed.
- **Journal mode for narrator.** During play with narrator mode enabled, the engine writes player state while the narrator reads world data. The database uses DELETE journal mode (not WAL) to keep `.zork` files self-contained without sidecar files. SQLite's locking still allows safe concurrent access for the single-player, single-writer workload.
- **Indexed access.** We create indexes on the columns we query most: items by room, commands by verb, exits by source room. Lookups are O(log n) via B-tree, not O(n) via scan.
- **Player state in the same file.** The runtime tables (`player`, `score_entries`, `visited_rooms`, and execution flags on commands/triggers) live alongside the world data. "Saving" is free -- state is persisted after every command. "Loading a save" is copying a file.
- **Inspectable.** Developers and curious players can open a `.zork` file with `sqlite3` or any database browser and see the entire game world. This is valuable for debugging generation issues and for community modding.

## Consequences

### What becomes easier

- **Portability is solved by default.** A `.zork` file is a single file. Share it however you want. No server, no connection string, no setup on the recipient's end.
- **Save/load is trivial.** Copy the file to save. Replace it to load. Multiple save slots are multiple copies.
- **Import reliability.** Transaction rollback means we never keep a half-written, inconsistent game file.
- **Referential integrity is enforced, not hoped for.** Foreign keys mean validation is catching logical errors (unsolvable puzzles), not structural ones (dangling references). SQLite handles the structural correctness.
- **Querying during validation.** The importer and validator can use SQL to check invariants: "SELECT exits WHERE target_room NOT IN (SELECT id FROM rooms)" instantly finds broken exits. This is far more reliable than scanning nested text structures in Python.
- **Future schema evolution.** SQLite supports `ALTER TABLE` for additive changes. The `metadata` table stores a schema version. Migration logic can upgrade older `.zork` files to newer schemas.

### What becomes harder

- **Human editing of game files.** JSON is easier to edit by hand than SQL inserts. Players who want to mod a game need SQLite tooling (though tools like DB Browser for SQLite are free and widely available). We could mitigate this with an `anyzork export --format json` command if demand exists.
- **Diffing game files.** Binary files don't diff well in git. This matters for development (comparing two generations of the same prompt) but not for end users. We could add a text dump command for development use.
- **Very large games.** SQLite handles databases up to 281 TB, so this is not a real concern for text adventures, but it's worth noting that SQLite is single-writer. If we ever supported real-time multiplayer (multiple writers), we'd need to revisit this decision. We do not plan to support multiplayer.
- **Testing.** Tests that touch the database need to create and tear down `.zork` files. Using `:memory:` SQLite databases for tests mitigates this -- same schema, no file I/O, automatic cleanup.

### Risks

- **SQLite version skew.** Different Python installations ship different SQLite versions. We should declare a minimum SQLite version (3.35+ for `RETURNING` clause support, or avoid version-specific features) and check at startup.
- **File locking on network drives.** SQLite's locking doesn't work reliably on NFS or SMB mounts. This is a known SQLite limitation. We should document that `.zork` files should be on local storage during play.
- **Schema lock-in.** Once we ship `.zork` files, the schema is a public API. Changes must be backward-compatible or versioned with migration support. We accept this trade-off -- the schema stability is also a benefit for the community.
