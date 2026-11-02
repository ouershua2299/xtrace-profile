# K-stage selection and interpretation

## Scope the observation

Keep the full production kernel and its launch context running. Instrument only
the original PCs for the relevant K-stage operations; do not extract/skip the
rest of a communicating or pipelined kernel and call it the same measurement.
FA3 already demonstrated this: three steady-state points, 31 loop iterations,
93 records per traced math warp. PR6517 MegaMoE now also has validated dense
first-QGMMA-per-BK128 traces on default fused and split plans (see local-evidence).
Those measure issue cadence, not a complete TMA/dequant/MMA completion breakdown.

`SassTraceSite` in the tested wheel has no generic `cta_id`, `warp_id`, `k==7`
or sampling-period argument. A role-specific PC naturally records only warps
that execute that path. Selecting an ordinary CTA or iteration in postprocessing
changes the analysis scope, not the runtime recording workload. Runtime selective
recording needs a supported conditional/custom probe or an existing compiled
path; do not invent a filter keyword or modify production source silently.

## Choose a small causal event group

| Role / boundaries | What the interval means |
|---|---|
| Producer empty-slot wait, before/after | Exposed wait until the slot can be reused |
| TMA issue, before/after | Enqueue/setup cost, not DMA completion |
| Consumer full-barrier wait, before/after | Remaining data-readiness wait |
| Dequant arithmetic, begin/end | Observed dequant code span, including scheduling delays |
| WGMMA issue through commit | Submission cost, not Tensor Core completion |
| Existing WGMMA wait/drain, before/after | Exposed wait for the guarded group(s) |
| Empty-slot release | Handoff allowing the producer to reuse this generation |

Do not insert a new drain solely to make a region look synchronous; that changes
the pipeline. Initially split full-wait/dequant and MMA/drain/release into separate
small groups, measure their perturbation, then combine if justified. Producer
and consumer regions can overlap, so their durations are not additive.

## Map real machine boundaries

Read `nvdisasm -gi` output or equivalent full inline stacks. Caller line numbers
alone can name a preloaded constant, a hoisted operation or several interleaved
regions. Distinguish the first arithmetic instruction from its setup loads.
Record each event's original PC, semantic meaning and binary SHA.

Loop unrolling and peeled first/tail iterations can produce multiple PCs for one
source operation. Cover and label the actual paths. In FA3, most P-convert
instructions lay inside the original Softmax envelope. A tiny post-Softmax tail
was not the cost of all conversion instructions; source probes serialized those
regions. Do not interpret the ratio of differently scoped tails as instruction
latency or an absolute accuracy result.

## Associate visits with work

Preserve `(launch, rank, linear CTA, local warp, record ordinal, site_id, smid)`.
Attach task/work-item ID, K index, ring slot and phase when available and verified.
The nth group of records is not necessarily logical K=n in a persistent kernel:
there may be several experts/tasks, skipped work, a peeled prologue and tails.
Derive any ordinal-to-K rule from CFG plus workload counts, then check it.

The original API can request a physical register value, but its GPR/UR class,
width, liveness and meaning must be audited on this binary. Do not copy a register
number from another specialization. A representative elected-lane value is a
warp value only if that field is uniform across the executing lanes. See the
version-specific UR warning in package-api.md.

## Size and interpret the trace

Budget per warp across the **whole launch**:

`records > sum(events_per_iteration * iterations_per_task) + other_recorded_visits`

Six events ×64 K iterations already uses 384 slots before other tasks/paths;
choose headroom from a proven bound, not the first observed count. All sites in
warp mode share a record run. Compute allocation from schema record width and
padding, not from a hardcoded slab size. The compact tested timestamp/RZ layout
uses 8-byte header, 8-byte records and 32-byte slab alignment.

SM clock records are local cycles. Do not align absolute clocks across different
SMs. The tested compact layout has 26 effective timestamp bits; retain a bound
from the same trace-producing launch. `anchor`/global-time correlation is an
additional path that needs independent validation, not a drop-in assumption.

If a site cannot fit, inspect the first rejected PC. Exhausted predicates are
different from insufficient GPRs or scoreboards. The masked FA3 prologue failed
while its steady-state points succeeded. A shifted point measures a different
boundary and must be labeled that way. Do not bypass the failure with blanket
fences or an unvalidated register-budget override.
