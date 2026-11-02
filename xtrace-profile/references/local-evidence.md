# Local evidence and provenance

These are pointers to archived work. Read exact reports before quoting numbers.
Do not treat historical jobs, containers or permission to use an idle allocation
as reusable authorization. Recheck current ownership/availability if GPU work
is part of the user's present task. Creating/using this skill alone requires no
GPU job, package upgrade, allocation mutation or message to another person.

Historical archive root: `MegaMoe/02_experiments/` in the original research workspace.
These archives are optional provenance and are not included or required to run this skill.
A portable historical summary is included as [validation-summary.json](validation-summary.json).

## Original-package FA3 comparison

`xtrace_fidelity_20261015/README.md`

- `reports/FA3_XTRACE_VS_CLOCK_CN.md`, `reports/summary.json`:
  two independent builds, same executable `.text`, three K lengths, extra seed
  at longest K; 1024 timed exact-output checks and 32 raw buffers.
- `scripts/splice_native.py`: original `TraceInstrumenter_SASS`; default mode
  and separately labeled greedy-INIT / optimal-RECORD configuration.
- `scripts/bench_fa3.py`, `run_fa3_campaign.py`: same launcher, state/protocol,
  materialized binaries, raw traces and per-method ABBA.
- `scripts/map_regions.py`, `audit_native.py`, `finalize_fa3.py`: inline source
  mapping, retained original instructions and independent evidence replay.
- `scripts/run_pc.py`: separate NCU diagnostics, not wall timing.
- `evidence/package_identity.json`: package/native hash and compiler/tool versions.

Scope: upstream FA3 commit `1fc0221183e799363001394a12dd9e78e15f5dda`,
H200 FP16 D128/H4/Q4224, tile128×176×128, ClusterM1, 132×384 launch.
Only the steady-state math-loop three-point group was accepted. The initial
masked prologue rejected a site with all predicate registers live. It is not a
full reproduction of the paper's benchmark suite or a phase-error bound.

At the longest tested K, source clocks added approximately 10.6–10.9% while the
original package configurations added approximately 2.0–2.2%. This measured
scope is the only context for those ranges. The original loop interleaved
43/44 P-convert instructions before Softmax finished; source probes reduced it
to 0/44. Native insertion preserved 2583/2600 original instruction bytes.
A 2026-10-21 byte-level re-audit corrected the old classification: the other
17 changes comprise 12 branch-target relocations and 5 scoreboard wait-mask
adjustments, not 17 branch relocations. The old `audit_native.py` normalizes
instruction text and can misclassify control-bit-only changes; use
`MegaMoe/00_report/xtrace_profile_20261021/binary_reaudit.json`
and its `build_report.py` for this corrected check, preserving old sealed reports.
None of this proves zero runtime
distortion or that every dense trace enjoys the same advantage.

## Original-package MegaMoE usage and clock control

`xtrace_h200_20261015/`: original wheel under `deps/gwatch`, audited cubins,
site configurations and original usage diagnostics.

`xtrace_core_repro_20261015/reports/CLOCK64_COMPARISON_CN.md`:
original-package Xtrace versus minimal source clock64/clock32 at coarse M1/M64
boundaries. Both had small end-to-end perturbation; that did not establish equal
local accuracy. The same directory also contains independent-reproduction
research; do not confuse those artifacts with the original-package comparator.

`xtrace_sm90_backend_20261015/` is the independent SM90 implementation. It is
**not** the user's default profiler and not the source of the FA3 native result.

## PR6517 default-plan and density controls (2026-10-21)

`xtrace_pr6517_large_20261021/REPORT_CN.md`: frozen PR6517 head
`dc0ab8aea44f8b884de0d9f830c0d95ea33df16d`, M256 default BM64 fused and
M1024 default split L1/L2, 8 H200. The sparse campaign includes all-rank and
single-target rank0/rank7 comparisons, 4608 operator calls.

`xtrace_pr6517_large_20261021/ablation/REPORT_CN.md`: 4096 additional operator
calls, two routing seeds and A/B process repeats; fixed sparse versus append
sparse versus dense first-QGMMA-per-BK128, same 8192-record capacity/stride.
Dense clock64 paired-median overhead ranges: fused 2.08–2.32%, split 1.27–1.49%;
original Xtrace: fused 1.03–1.37%, split −0.03–0.19%. These are four-run point
estimate ranges, not confidence intervals or universal guarantees. Some
individual-case CIs cross zero; long-tail samples were retained.

- `ablation/scripts/bench.py`: pre-captured Graph replay, fixed default plans,
  actual loaded binary SHA, distinct source symbols and native graph-buffer
  effects; all ranks participate. Warm the exact timing path before samples.
- `ablation/scripts/validate.py`, `analyze.py`: raw integrity, modulo-clock bounds,
  per-rank/site count equality, plus independent route-derived math-work counts.
  Do not require each persistent CTA to receive identical tasks across methods.
- `ablation/reports/SITE_CODE.md`: the dense source clock32 sites compiled to
  S2UR, while the sparse source used CS2R.32. Width alone does not predict cost.
  Source branch/reconvergence and volatile stores differ from native elected-lane
  predicated stores. This is an end-to-end recorder comparison, not pure timer latency.
- `ablation/reports/BUILD_VERIFY.json`, `static.json`: source/binary/launch identity,
  exact serialized-byte preservation audit and role-specific register limits.

No extra static local spills or resource changes explain this observed gap.
FA3 still has its separately verified Softmax/P-convert interleaving loss.
Compare absolute microseconds as well as percentages; FA3 used CUDA13.0 and the
new MegaMoE used CUDA13.4, so cross-kernel causal claims remain conditional.

## Local kernel-generic adapter (2026-10-23)

`xtrace_generic_20261023/` is the regression archive for the installed local
adapter. The reusable implementation lives in this skill's `scripts/xtrace_local/`,
called by `scripts/splice_cubin.py`; it has no workload name/hash allowlist.

The MiMo regression covers MoE, SWA mega, Full QKV-only (FA1) and Full tail (FA2).
SWA/FA1 share one entry with different runtime modes. MoE/SWA replay genuine
captured inputs; FA1/FA2 use bounded Pro-shaped inputs, real TP8 IPC destinations
and an FA1-to-FA2 PDL chain. Resource counts come from each original ELF and role
path, not constants96/139/168. Read `REGRESSION_SUMMARY.json` for actual completion
and measurements; do not infer a GPU pass from an emitted artifact alone.

The division fixture supplies no manual R2 exclusion: the call-aware overlay
must infer it. It checks signed zero, subnormals, infinities and NaNs, verifies
that the slow helper actually executed, and runs Compute Sanitizer memcheck.

`xtrace_kda_fix_20261023/` is the earlier hash-pinned MoE repair and manual caller
register regression. Preserve it as historical evidence; do not use its
kernel-specific adapter as the current general method.

## External primary references

- [Xtrace paper](https://arxiv.org/html/2609.28769v1): binary splicing, liveness,
  hazards, trace types and the paper's own workload-specific evaluation.
- [Pinned FA3 source](https://github.com/Dao-AILab/flash-attention/tree/1fc0221183e799363001394a12dd9e78e15f5dda/hopper).

When explaining a current installed API or recommending a different package
version, inspect that environment and verify current primary documentation;
the archived 0.0.35 behavior is not a promise about later releases.
