# Evidence ledger

Put one completed trial per JSON file in this directory. The directory is empty
on purpose: the E0 heuristic and synthetic test fixtures are not real-world
evidence. Only add a record after its referenced artifacts, evaluator results,
skill digest, immutable tested-stack releases, supervision, errors, and recovery
data exist. Qualifying receipts must expose public bytes that the validator
recomputes from a repository-relative file or bounded `data:` URI. Bare digests,
remote URLs, private-store claims, and sensitive/non-public embedded bytes do not
qualify.

Use a stable filename such as:

```text
<task-slug>/<YYYY-MM-DD>-<trial-id>.json
```

The validator scans subdirectories recursively and selects the exact immutable
schema/policy versions named inside each record. Never edit or delete a valid
historical record; supersede it with a new append-only record.
