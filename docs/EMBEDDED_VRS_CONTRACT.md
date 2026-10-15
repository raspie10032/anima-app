# Embedded image retrieval and SWEGCA contract

## Scope and definitions

The goal is a standalone Anima installation: the shipped package owns the image
encoder implementation and the SWEGCA evidence core. No sibling checkout,
external Python executable, compiler, or environment variable is required.
Model weights are prepared explicitly through the app. Existing originals,
metadata, evaluations and vector rows remain unchanged.

An image observation is decoded RGB pixels. An encoder contract identifies
weights, preprocessing, quantization and pooling. Retrieval score is the dot
product of normalized pixel-derived vectors; metadata is joined after ranking.
A hypothesis is relevance of one candidate pixel identity to one query pixel
identity for a specified dimension (visual similarity or prompt reuse).
An explicit local-user evaluation is observational evidence about that
hypothesis. A model score, a metadata tag and a relative A/B preference are not
independent evidence that the input was made by an artist.

## Formula and invariants

For nonzero finite vectors, s(q,x)=<q/||q||, x/||x||>. Only vectors with the same
encoder contract can be compared. Exact pixel duplicates are excluded.
SWEGCA's original EvidenceAccumulatorConfig and assess/update algorithms are
preserved. Source families and producer identities reflect their actual origin;
repeated queries never manufacture independent producers or causal axes.
For each (query pixels, candidate pixels, evaluation dimension), only the most
recent explicit evaluation is replayed. Zero means insufficient. Similarity
scores are never converted to support observations.

The authoritative decision gates promotion to trusted evidence. An abstention
keeps the case as a similarity suggestion, with original metadata accessible.
Core thresholds and encoder weights remain unchanged. Personal ordering is a
separate policy: the latest visual rating contributes 0.01 times its value;
the mean of the latest active preferences for distinct candidate pairs
contributes at most 0.005 in either direction. The total adjustment is bounded
by 0.015. It applies only to identical query pixels and the same encoder
contract. Reuse ratings never change visual ordering. Visual and reuse updates
have separate timestamps so editing one cannot revive an older judgment of the
other. The original cosine score and SWEGCA abstention remain visible.

The optional diverse order uses only pixel vectors: it keeps the highest
adjusted candidate, then greedily maximizes adjusted similarity minus 0.2 times
maximum similarity to an already selected candidate. Its pool is the first
max(4 * limit, 100) adjusted neighbors within 0.04 of the best raw score;
remaining neighbors fill a small pool. Artist labels do not select candidates.

## Reasoning

Equal RGB content gives equal preprocessing input independently of PNG metadata.
Contract equality is necessary for vector reuse; a changed implementation cannot
silently inherit a vector space. Legacy reuse requires the exact old source,
weight provenance and preprocessing hashes and a measured embedding check.
Replacing source paths alone does not alter the numerical recipe.

Replaying only the latest evaluation removes superseded observations. The core
receives the one real local-user producer and only the observational axis, so
repeated clicks cannot satisfy its independent-producer or causal-axis guards.
Missing evidence therefore remains an abstention by the unchanged core rules.
This establishes the integration boundary, not retrieval quality or causality.

## Algorithm

1. Prepare pinned vision weights atomically; validate all expected file hashes.
2. Encode in an app-owned worker with offline model loading and generation lock.
3. Retrieve matching-contract vectors, exclude duplicate pixels, apply explicit
   personal ordering and optional diversity, then join records.
4. Replay applicable explicit evaluations through the bundled SWEGCA accumulator.
5. Return decision and observation trace with cases. Save receipts with evaluation
   writes in the same SQLite transaction; restore by replay after restart.
6. Package source, provenance manifests and licenses in wheel/source ZIP; test
   import, encoder preparation, retrieval and assessment without sibling paths.

Validation: corruption, cancellation, cold installation, no GPU, no token,
metadata independence, old vector compatibility, repeated/revised evaluations,
three locales, narrow layouts and unchanged generation payloads across views.

## Runtime reuse

The numerical encoder recipe is unchanged. Corpus matrices live in process
memory; SQLite triggers invalidate them on asset or vector mutation, including
writes from another connection. Queries and evaluations do not invalidate them.
Each search reads revision, rows and vectors from one SQLite snapshot, ending
the read transaction before its query receipt is written.

The encoder worker can remain available for 60 idle seconds. Index sessions,
errors, cancellation, shutdown and the idle timer close it. Another app GPU
task first acquires the shared lock, then closes the idle encoder before doing
GPU work. This lifetime wrapper is outside the numerical encoder fingerprint;
existing vectors require no reindex solely for this optimization.

## User enable setting

The library persists `vrs_enabled` separately from vector contracts. Disabling
rejects VRS search (including cached queries), index jobs and preparation, closes
the idle encoder under the shared GPU lock, and clears in-memory corpus matrices.
It does not delete images, vectors, records or feedback. Basic CPU retrieval and
its evidence handling stay available. Search/index operations and setting writes
share a lock; disabling during work fails without changing state. Index cancellation
remains available. Re-enabling reuses matching vectors without changing the recipe.
