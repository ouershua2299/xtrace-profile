# Package API and CPU tools

The default local path is described in [local-general.md](local-general.md).
It uses original upstream probes plus locally audited emission/liveness checks.
Direct upstream `do_trace` below bypasses those fixes; use it only as an explicit
upstream comparison or after independently validating that path for the binary.


## Environment and identity

Use an isolated existing environment or project-local package install. Do not
replace the user's global PyTorch/CUDA installation merely to import gwatch.
Inspect the installed `_runner.py`, `_schema.py` and native-library metadata;
Python forwarding methods have sometimes been absent from the native wheel.
Do not assume methods named by documentation are callable without checking.

The local tested wheel is `gwatch==0.0.35`, with
`libgwatch_dark_cuda128_x86_64.so` SHA256
`c19c621b83404861acb55ac455c58c6afa206f4ec2d6b2a8cebda4f024788dfe`.
The archived CPU environment used CUDA12 runtime/CUPTI libraries for this wheel
alongside a CUDA13 compiler; copy that setup only if needed for the same wheel.
The native library and machine-description assets must remain unchanged.
Save the unmodified image using vendor extraction or a checked unmodified
`dump()`; `serialize()` rebuilds it and is not a neutral capture. Conversely,
`dump()`/cloning a modified image may omit live probe edits: check emitted bytes.
For SASS argument metadata use the reversed size/offset arrays sorted together
by offset; the unsuffixed size list can be empty in this wheel.

## Single-GPU high-level use

This is an API skeleton, not a runnable example with universal PCs:

```python
import re
from gwatch.cuda.profile import ProfileContext
from gwatch.cuda.xtrace import do_trace, SassTraceSite

ctx = ProfileContext()  # before loading the target module, especially cuLibraryLoadData
# Load/warm the target, save its original cubin, resolve its original PCs here.
sites = [SassTraceSite(insert_index=pc // 16, warp_level=True, value_reg=255)
         for pc in selected_original_pcs]
result = do_trace(
    fn=launch_with_reset,
    kernel_name_pattern="^" + re.escape(mangled_entry) + "$",
    instrumentation_tier="sass", sass_arch="90a",
    clock_type="sm", sass_trace_sites=sites,
    sass_per_thread_records=record_budget,
    sass_splice_mode="plain", sass_schedule_mode="first_feasible",
    profile_context=ctx, profile_stream=stream,
)
```

- `insert_index` indexes the original instruction stream, not a source line.
  On SM90, `pc = insert_index * 16`. Index 0 precedes INIT and is invalid here.
- `fn` runs for the scout and traced execution. The library does not checkpoint
  mutable inputs/workspace; restore state for both and synchronize correctly.
- Save `GWATCH_TRACE_KEEP_CUBIN` to retain the image used by high-level tracing.
  An empty result is not success. `oe_results` is not an observer-effect proof.
- In 0.0.35, explicitly recording RZ (`value_reg=255`, 32 bits) gives the audited
  timestamp + zero-payload 8-byte warp records. Do not assume `None` has that
  layout; query schema and validate raw bytes.
- `first_feasible` tries a greedy order first. `least_makespan` also searches
  INIT and may be slow; bound static attempts and preserve timeout evidence.
  The FA3 experiment separately labeled greedy-INIT/optimal-RECORD using the
  original per-context API. Do not call it full-configuration optimal.
- The `split`/`auto` APIs do not imply that warp-mode stores are sunk in this
  wheel. The inspected 0.0.35 warp path emits plain records; inspect current
  code and per-site reports before claiming a different mode was used.

## Default local offline adapter

Run `scripts/splice_cubin.py` in an environment where the original wheel imports:

```bash
python scripts/splice_cubin.py --cubin original.cubin --config sites.json --output traced.cubin
```

Example `sites.json` structure (indices must be replaced with audited real ones):

```json
{
  "original_sha256": "digest of the exact original cubin",
  "kernel_name_pattern": "^exact_mangled_entry$",
  "arch": "90a",
  "grid": [132, 1, 1],
  "block": [384, 1, 1],
  "records": 512,
  "sites": [
    {"insert_index": 1074, "label": "softmax_begin", "warp_level": true, "value_reg": 255},
    {"insert_index": 1565, "label": "softmax_end", "warp_level": true, "value_reg": 255}
  ]
}
```

The numbers above came from one FA3 binary and are **not portable**.
The local adapter derives register budgets and call mappings from the input;
it does not assume those FA3 sites or any MoE-specific counts. The adapter
requires the input digest, one unambiguous entry and complete 32-thread warps.
The native 0.0.35 metadata reports `90` for an SM90a image, so the adapter checks
the family (accepting `90`, `90a`, `sm_90a`) and records that limitation. Verify
the actual feature-qualified image separately with vendor tools; family matching
alone is not an `sm_90a` image-selection proof.
It defaults to `sm/plain/first_feasible`; optional configuration `schedule`
accepts `least_makespan`, but external CPU time limits remain the caller's job.
No GPU/Slurm/Docker action is performed. Existing output/proof paths are refused.

The adapter supports the tested 32-bit GPR payload layout. Actual value capture
needs an independent value check; only RZ timestamp capture was validated across
both large kernels. In the inspected 0.0.35 warp instrumenter,
`value_is_uniform` is not forwarded to the RECORD operator: do not trust UR
capture through that field without verifying/fixing that version-specific path.
The adapter rejects it, SM-id-as-payload and wider payloads. Warp SM id is already
in the header. Keep new-schema work separate from a validated timestamp run.

## Raw validation

The adapter's `.json` proof includes a `schema` object consumable by:

```bash
python scripts/validate_warp_trace.py --raw trace.npy --schema traced.json \
  --launch-us 76.0 --max-sm-clock-khz 3000000 --output raw-check.json
```

`launch-us` must be a conservative elapsed upper bound covering the actual
launch that wrote this buffer; for distributed runs retain all rank events and
use the per-call maximum. The clock ceiling is explicit, positive and justified
for the target GPU. The validator computes `ceil(us * kHz / 1000)` and requires
it below half the 26-bit clock period; observed modular deltas are not a bound.

Accepted `.npy` arrays are flat/reshapable uint8 bytes, uint32 words or uint64
records with exact byte length. Zero-initialize the trace buffer before the
trace-producing launch; the validator treats unused records/padding as guards.
A standalone schema JSON can contain:

```json
{
  "grid": [132, 1, 1], "block": [384, 1, 1],
  "records": 512, "slab_bytes": 4128, "header_bytes": 8,
  "record_bytes": 8, "timestamp_bits": 26, "site_id_bits": 6,
  "site_count": 3, "clock": "sm", "zero_payload": true,
  "expected_by_warp": {"0": [], "1": [], "2": [], "3": [], "4": [0, 1, 2]}
}
```

`expected_by_warp` keys are local warp indices within each CTA and values are
their full expected dynamic site sequences, not one loop pattern. Omitted keys
do not impose sequence/count expectations. Use `[]` for an intentionally untraced
role. For data-dependent schedules, derive expected sequences/task associations
in a workload-specific analyzer rather than fabricating a fixed count.

A pass checks structure, optional sequence expectations, payload/padding,
SM consistency and bounded per-warp deltas. It does **not** prove correct
stage labeling, completeness without expectations, output correctness, or low
observer effect. It also cannot authenticate a supplied launch duration: bind
that number to the trace-producing launch in the harness/evidence record.
Other layouts must use their own verified decoder.
