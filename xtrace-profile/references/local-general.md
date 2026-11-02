# Local kernel-generic SM90 Xtrace

## Default use

In an environment where the pinned original wheel imports:

```bash
python /path/to/xtrace-profile/scripts/splice_cubin.py \
  --cubin original.cubin --config sites.json --output traced.cubin
```

The config supplies `original_sha256`, an unambiguous `kernel_name_pattern`,
`arch` (`90`/`90a`), three-dimensional `grid` and `block`, `records`, and `sites`.
Each site has an original `insert_index`; optional `label`, `warp_level: true`
and `value_reg: 255` document the tested timestamp/RZ layout. The original SHA
is an identity check, not a built-in kernel allowlist. Re-map PCs after any
binary change. Multiple entries in the input ELF are supported; only the selected
entry is emitted. Referenced constant data must survive emission.

Optional `init_insert_index` defaults to 1. A later INIT must dominate every
selected site, be outside repeated execution cycles, and have a valid role budget. In particular, a TRY_ALLOC instruction
can fail and retry: a point before its success check cannot assume the higher cap.
The adapter recognizes the checked direct-uniform and predicate-conversion retry
forms. `init_scope` and `notes` are annotations, not runtime filters.

Optional `excluded_registers` maps `general`, `predicate`, `uniform_general` or
`uniform_predicate` to physical registers withheld by an external calling
convention. Usually leave it empty: the direct-call overlay automatically protects
caller values, including the division regression's R2. Exclusions are applied
**after** the upstream argument append/reparse, so they are not lost.

`expected_by_warp`, when supplied, is a later validation contract, not a runtime
selection filter. For CTA-dependent coverage (e.g. SWA attention vs other CTAs),
use an application-specific checker in addition to the generic raw checker.

## What is generalized

- Kernel name, source hash, entry register count, dimensions, budget, sites,
  argument sizes/offsets, number of calls and number of returns are input-derived.
- EIATTR_REGCOUNT is selected by the target symbol in the original ELF. Restore
  that entry budget only after all probe GPRs fit the original role caps; never
  clamp registers while leaving probes outside their available budget.
- Direct CALL.REL targets, recognized compiler return-address MOVs and RET.REL
  bases move together through the original-to-new PC map. The selected return
  definition must be unambiguous on a predecessor chain; unknown ABI is rejected.
- A call/return CFG overlay propagates caller-live values through callees. Its
  exclusions are unioned with upstream async-aware liveness, never subtracted.
  It is conservative and can over-reserve registers; it is not a complete new
  compiler or a proof for arbitrary hand-written SASS.
- PREEXIT is a dependent-task-launch hint, not program termination. The local
  overlay restores its fallthrough. The original instruction is unchanged.
  See [NVIDIA instruction reference](https://docs.nvidia.com/cuda/cuda-binary-utilities/).
- Persistent trace UR pairs come from registers unused by the original program,
  including callees. A separate upstream planning definition selects them, so
  this restriction does not unnecessarily exclude dead short-lived scratch URs.
  RECORD writes are checked against the reserved cursor; GPR fallback for a
  warp pointer is not silently accepted.

The backend does not raise role caps, spill original values, insert blanket
fences, reorder original arithmetic, or change the native `.so`. It does rewrite
selected serialized metadata and address fields. Do not call it pure upstream
output when comparing tools or reporting preservation percentages.

## Proof and runtime

`traced.upstream-unvalidated.cubin` is the raw emitted image; **do not launch it**
merely because a file exists. `traced.cubin` plus `traced.json` appear after static
checks. `static_verified_runtime_validation_required` is not GPU validation.
The proof records the adapter sources, native SHA, ABI, original/repaired budget,
branch/call/return audit, inferred exclusions, allocation guards and probe PCs.

Keep the application launch boundary intact. Append the trace pointer according
to `parameter_abi`; parameter 0 need not start at offset 0, and not every kernel
has one aggregate argument. Check the Driver API layout against the original.
Preserve dynamic shared memory, cluster attributes, stream/PDL dependencies and
state resets. Multi-rank communication requires all peers to participate.

The accepted layout is warp-level `sm/plain`, 32-bit GPR payload (RZ by default),
8-byte records and a 26-bit effective timestamp. A nonzero payload needs its own
value check. Uniform/wide payloads, global-clock/anchor layouts and runtime
CTA/warp/iteration filters are not implemented by this adapter.

## Supported boundary

Validated backend: gwatch 0.0.35, original native SHA documented in package-api,
SM90/SM90a, CUDA ELF ABI8. Indirect/unresolved control flow, recursive calls,
unrecognized software-return conventions, nonempty text relocations, device
functions changing register budgets and unsupported allocation retry forms fail
closed. Other architectures need their own reviewed encoding/backend; do not
remove the architecture gate to make an input pass.

Each new binary still requires correctness, trace coverage and perturbation
checks. The four MiMo paths are regressions, not an allowlist or proof that every
other kernel is safe. SWA and FA1 share an entry but execute different modes.

Historical evidence (not bundled): `MegaMoe/02_experiments/xtrace_generic_20261023/`.
Portable summary: [validation-summary.json](validation-summary.json).
MoE/SWA use genuine captured TP8 inputs; FA1/FA2 use bounded Pro-shaped synthetic
inputs with real IPC and a PDL chain. The division fixture exercises slow calls
with IEEE edge cases and automatic exclusions, without a manual R2 hint.
