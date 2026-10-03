"""Development probes over the adoption benchmark (`benchmarks/adopt`), kept apart so that the
seal, which covers every module under `benchmarks/adopt/`, is never touched. The sealed modules
are imported as a library; nothing here writes under `adopt/runs` or `adopt/singles`."""
