# Performance Notes

## `/v1/targets?board_id=...`

`tw-tx8w` removed the current N+1 query on target list responses caused by
per-target confidence-chain projection.

Measured locally on 2026-06-05 with in-memory SQLite and 100 targets, each with
one observation:

| Path | SELECT count | Elapsed |
| --- | ---: | ---: |
| `list_targets_on_board` after batching | 2 | 49.31 ms |

The regression test
`tests/unit/test_db_repositories.py::TestTarget::test_list_targets_on_board_batches_confidence_chains`
captures the prior failure mode: 5 targets produced 6 SELECTs. The expected
shape is now one target-list query plus one batched observation-chain query.
