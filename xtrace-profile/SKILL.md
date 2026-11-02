---
name: xtrace-profile
description: "Profile GPU kernels with original gwatch/Xtrace probes and the local audited SASS compatibility adapter. Use for warp traces, K-stage analysis, Xtrace versus clock64 comparisons, and communication-aware GPU profiling."
---

# Xtrace profiling

Use the **local general adapter around the installed original gwatch package**
as the default on the validated H200/SM90 path. The original native library still
allocates and schedules probes. The local layer preserves entry register budgets,
relocates direct call/return addresses, and adds conservative call-aware register
protection. Label these results **local Xtrace compatibility**, not untouched
upstream output or the independent SM90 reproduction.

The adapter selects a kernel and sites from an input manifest; it has no MoE
name/hash allowlist and no hardcoded register count or launch shape. Its backend
is currently version-pinned to gwatch 0.0.35, SM90/SM90a and CUDA ELF ABI8.
Kernel-generic does not mean every architecture, calling convention or point
is supported. Unsupported cases are rejected, not silently recompiled through PTX.

## Installation and troubleshooting

For a new machine or colleague handoff, start with [README.md](README.md).
Run `scripts/doctor.py` to report backend identity and import failures without launching a GPU kernel.
Read [troubleshooting.md](references/troubleshooting.md) when a check or launch fails.
The shareable package includes a historical validation summary, not private workloads or a universal launcher.

## Choose the reference

- Read [local-general.md](references/local-general.md) for the default command,
  manifest, compatibility checks, automatic caller-live protection and limits.
- Read [package-api.md](references/package-api.md) for environment setup, original
  high-level APIs, the emitted argument ABI and raw decoding. Direct upstream
  `do_trace` does **not** automatically apply this local adapter.
- Read [k-stage.md](references/k-stage.md) for TMA/dequant/MMA event meanings and
  repeated dynamic visits. Post-filtering does not reduce recording overhead.
- Read [validation.md](references/validation.md) for quantitative comparisons or
  multi-GPU kernels. Every communicating rank must execute matched launches.
- Read [local-evidence.md](references/local-evidence.md) for runnable regressions
  and archived results; old job/container IDs are not future authorization.

## Workflow

1. Freeze the actual loaded cubin, entry, architecture, source/options, shape,
   grid/block/cluster/shared memory and initial state. Keep original capture
   distinct from rebuilt emission; `serialize()` is not a neutral file copy.
2. Resolve original PCs using full inline DWARF **and SASS**. Inspect hoisting,
   unrolling and asynchronous ownership; a source line is not a phase boundary.
3. Run `scripts/splice_cubin.py` with a fresh output and SHA-bound manifest.
   Begin with a small warp-level SM-clock/RZ group and `first_feasible`. Budget
   records for every task/loop visit in the warp's entire launch.
4. Inspect the proof: selected symbol, original/emitted/repaired resources,
   call/return mapping, inferred exclusions, INIT dominance and per-role caps.
   Do not suppress a rejection or bypass allocation retry guards. A register
   declared in a dynamic role is not necessarily available at kernel entry.
5. Forward **all** original arguments plus the appended trace pointer using
   the verified ABI and launch attributes. Validate outputs, event coverage,
   guards/capacity, clocks and paired OFF/ON wall time before interpreting phases.
6. Treat issue/commit as submission, not async completion; waits are exposed
   remainder, not total service time. Never subtract absolute clocks across SMs.

The output status is static verification only. New workload/mode/site choices
still need runtime checks even if another kernel passed. Conservative extra
liveness can leave no feasible probe; choosing a different point changes the
measured boundary and must be labeled accordingly.

## Helpers

- `scripts/splice_cubin.py`: stable CLI/import entry for `scripts/xtrace_local/`.
  CPU only; keeps the raw upstream image explicitly marked unvalidated, and
  emits the repaired cubin only after its static gates pass.
- `scripts/validate_warp_trace.py`: read-only checker for the tested 8-byte,
  26-bit SM-clock warp layout. Format validity alone does not prove workload
  event coverage or low perturbation.

Report the backend/version, original and emitted identities, sites/roles/visits,
resource and instruction changes, correctness, trace integrity and paired wall
overhead. Small total overhead is not proof of absolute local-phase accuracy.
