# Performance Smoke Test

Use this after changing tapelib FUSE behavior or deploying a new build to the
tape host.

```bash
tapelib filesystem-smoke-test
tapelib filesystem-smoke-test --fail-slow
```

The default test walks side-effect-free filesystem operations:

- root stat/list/readme
- shallow `browse`, `readable`, `jobs`, `system`, `thumbnails`, and `write`
  stat/list operations
- tape-root list/readme operations
- static JSON and README stat/read operations
- compact job summary JSON reads
- drive JSON reads

It deliberately avoids:

- opening readable archived files, because that queues retrieve jobs
- writing into `/write/inbox-cached`, because that queues ingest jobs
- reading `/system/inventory.json`, because that calls live changer inventory

To include the hardware observation path:

```bash
tapelib filesystem-smoke-test --include-hardware
```

Budgets:

- virtual-only operations default to `250 ms`
- hardware observation defaults to `5000 ms`

Override the virtual budget while investigating:

```bash
tapelib filesystem-smoke-test --fast-budget-ms 100 --fail-slow
```

Expected live shape on `desktoptoodle` after the shallow-navigation fix:

```text
eza /home/example/tapelib          # a few milliseconds
eza /home/example/tapelib/system   # a few milliseconds
eza /home/example/tapelib/browse   # tens of milliseconds for tape root names
stat /home/example/tapelib/system/inventory.json  # a few milliseconds, no mtx
```

If a shallow operation is slow, check for accidental calls to:

- full catalog tree construction in `TapelibFuse._tree()`
- `db.list_files()` or `db.list_bundle_members()` from top-level/shallow paths
- `hardware.read_changer_inventory()` during `getattr` or `readdir`

Deep `browse` and `readable` archive paths should also avoid full tree/file-map
construction now. They should use `parent_path`/`name` catalog lookups for
directory reads and exact path lookups for file metadata. Live changer inventory
is acceptable only when reading the live inventory file.
