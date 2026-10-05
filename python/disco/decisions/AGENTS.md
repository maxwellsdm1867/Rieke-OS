# Authored decisions owners

Start with [the contract](CONTRACT.md). Import the individual substantive module
for annotations, author preferences, group commands, curation or tag exchange.
The package initializer is inert; it neither loads scientific dependencies nor
combines command authority. Existing public functions/classes/constants remain
available from their named modules. Existing internal helpers remain internal
implementation facts, not newly invented ports.

The [isolated receipt examples](../../tests/test_backend_decisions_public.py)
exercise receive/replay refusal without SQL, first delivery or export fixtures.
Use [adjacent decision owners](ADJACENT.md) for checkpoint/preparation, applied queries,
tag indexes, vocabulary and response-only undo. Cross-owner protocol-state proof
retains its flat owner.
