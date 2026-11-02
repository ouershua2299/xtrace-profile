# Execution and interpretation checks

## Single GPU versus communicating kernels

High-level `do_trace` is convenient for an isolated kernel when context creation,
module capture, input reset and stream synchronization are controlled. Establish
ProfileContext before `cuLibraryLoadData` module loading. Keep JIT compilation,
capture, splicing and warmup outside wall measurements.

For MegaMoE/EP kernels, all ranks must participate in every communicating launch.
Do not scout/profile one rank while peers wait in a different launch or collective.
Use matched input/workspace reset, shapes and image/ABI per rank. Preserve timeout
logs and terminate only processes/resources owned by this experiment.

The validated local route was:

1. Original-package offline SASS insertion through the local general adapter,
   with emission, call/return and role-cap checks. Raw upstream output is a
   separate diagnostic path, not an automatic fallback.
2. Append the trace pointer through the package's emitted parameter ABI.
3. An observation-only host launcher selects the traced CUfunction and forwards
   the original arguments plus pointer; match dynamic shared-memory attributes.
4. Run all ranks consistently with an unmeasured queued GPU launch gate before
   timing; preserve rank durations, reduce each call by MAX, then summarize.

This route compares kernel-only observer effect without launch-hook interference.
It does not measure the high-level package's setup/capture/export overhead and
does not assert that Xtrace categorically cannot profile communication.

## What to check

- **Identity:** source/workload, package/native version, actual loaded architecture
  image, mangled entry, grid/block/shared, original/instrumented hashes, sites
  and schema. Check uniqueness: high-level name matching can otherwise select
  an unintended matching specialization. A separately compiled convenience
  image is not proof of the actual JIT image.
- **Correctness:** repeated finite outputs; exact OFF/ON equality for insertion
  that preserves arithmetic. For a recompiled source comparator, establish its
  numeric contract and report any exact mismatch rather than hiding it.
- **Static preservation:** remove declared probe PCs and compare original
  instruction order/bytes. Inspect branch-target relocation separately; a
  string match alone does not prove preserved control bits. Check registers,
  stack, spill advisories, static/dynamic shared and launch topology.
- **Raw integrity:** actual schema, selected-role counts, repeated event sequence,
  task associations, capacity/headroom, contiguous writes, valid site IDs,
  expected payload and zero padding, per-CTA SM consistency, same-launch wrap
  proof. Untraced roles may legitimately contain zero events. A ring overwrite
  or missing K/task history is a rejected trace, not a usable truncated mean.
- **Perturbation:** alternating OFF/ON or ABBA, equal inputs/recording workload,
  declared cache policy, warm binaries, same launch protocol. For distributed
  cases take rank MAX per call before medians/paired comparisons. Predeclare
  an overhead limit appropriate to the question; do not invent a universal 1%
  threshold or interpret a small negative delta as profiler acceleration.

For an absolute phase magnitude that will drive optimization, add suitable
same-observer calibration/empty controls and independently materialized repeats.
Do not subtract a mismatched empty control, or mistake resource parity and low
wall overhead for proof of phase accuracy. Use the available cycle-critical-path
measurement guidance when such a calibrated claim is actually needed.

## Comparison and escalation

For Xtrace versus clock64, use the same elected-lane workload and event meanings.
Keep clock32 as a width control when useful. Report original-binary preservation
in addition to wall overhead: recompilation may preserve outputs/resources yet
change overlap. Do not engineer a deliberately poor atomic baseline or claim
the sparse MegaMoE result must generalize to a dense FA3 inner loop.

If PC sampling is needed to distinguish a remaining dependency hypothesis,
collect it as a separate diagnostic, document clock/cache/replay settings and
retain source/SASS-level samples. Never use NCU-profiled duration in the ordinary
OFF/ON wall table. A single uncontrolled-clock sample is qualitative corroboration.

## Failure response

| Symptom | First discriminating check |
|---|---|
| Kernel not captured | Context existed before module load; correct architecture/name |
| No feasible schedule | Rejected PC; live predicates/GPRs, async owners, role cap |
| Budget rises on no-probe round-trip | Compare original entry metadata with serialized resources; do not confuse it with dynamic role caps |
| CALL-containing kernel | Audit call targets, return literals and RET bases together; inspect inferred caller-live protection |
| Illegal instruction / out-of-range | Preserve image and error PC; role-specific budgets and encoding |
| Multi-rank hang | Matching scout/traced epochs, reset, arguments and launch participation |
| Wrong/missing timestamps | Schema width, budget/overwrite, site bias, selected roles, wrap bound |
| Plausible chart, inconsistent phase | Inline source stack, hoisting/interleaving, task/K association |
| Huge first measurement | Lazy compilation/capture/splicing inside events, host enqueue skew |

An unresolved correctness, mapping or record-integrity failure blocks a pipeline
claim for that trace. Continue unaffected inspection; do not describe static
insertion success as completed GPU validation.
