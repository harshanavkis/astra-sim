# Loom prototype implementation plan (Coyote vFPGA + AstraSim)

> **Tracked copy (2026-08-03).** Copied verbatim (plus this banner) from
> `~/loom-paper/design-docs/implementation-plan.md`, which is untracked in
> any git repo — this copy makes the hardware plan survive machine
> migration alongside CHECKPOINT/HANDOFF. If the two ever diverge, the
> paper repo's design-docs version is authoritative until testbed work
> starts; after that, this one is.

> **UPDATE (2026-08-03, evening): testbed work STARTED — this copy is now
> authoritative.** The vFPGA prototype lives in
> `Coyote/examples/loom/` (own repo; see its README for status, run
> instructions, HW-DESIGN.md for the architecture, WORKFLOW.md for the
> worked example). Implemented and green in XSIM simulation: ctrl slave
> (CSR page + 15x4KB aperture + arrival-ordered FIFO), window table,
> engine (small stores <=8B + descriptor DMA with per-descriptor fence,
> local + rdma routes), rx forwarder, engine/rx arbiter; five block TBs,
> Coyote integration sim via the real cThread API, Python-framework RDMA
> TX test, and role-split software (OrchClient/orchestrator/XPU, 5.1a).
> Deployment decisions vs. the original text below: ONE vFPGA per host
> (multi-region rejected: splits the switch state), aperture ops <=8B via
> AXI-Lite only with bulk via DMA (no AXI4 bypass — shell stays stock),
> source identity by partition convention (no attacker model).
>
> **Descopes applied from the 2026-08 evaluation review**
> (`HANDOFF-EVAL-REVIEW.md` §4, owner decisions): the victim-flow/VOQ
> isolation experiment, failure containment (T7), and control-plane
> costs (T8) are PERMANENTLY DESCOPED — the paper makes no isolation
> claim, VOQ is standard switch art, and the 1-dim victim topology was
> structurally vacuous. Original Phase 4 below is therefore dead; the
> error containment unit and per-destination queues/scheduler will not
> be built. Reads (original Phase 5) are PLANNED, scoped to T6
> calibration: the sweep policy expects the read RTT to land as a
> MEASURED value (CHECKPOINT next-steps #9 lists T6 among the testbed
> deliverables, and the credit-sweep experiment is active in Phase A).
> Prototype scope: an aperture READ entry through the same order FIFO -
> local reads pull 8 B from the destination buffer under its pid and
> return it on the held-open AXI-Lite read channel (sim-testable via
> getCSR); remote read RTT via the shell's RDMA READ path is
> hardware-only (PCIe completion-timeout config watched, per the
> original Phase 5 text). The credit *model* stays sim-side
> (sweep_credits); AXI-Lite's single-outstanding read makes the
> hardware tracker trivially depth-1 - state this in the paper.
>
> **What the testbed still owes the simulation** (README "FPGA-owned"
> constants; measured, NOT swept, per decision #2): per-stage pipeline
> latencies via stage cycle counters (T3: t-lookup, t-translate,
> t-forward, t-encap, roce-stack; t-queue only if a queue stage exists),
> the coalescing/goodput curve with coalescer on/off (T2 — the TX
> coalescer is still needed in RTL for this), substrate floors (Phase 0
> baselines), and B2 rdma-init (CPU-verbs post+poll on the testbed
> hosts). B1 rdma-init is measured on a GPU+NIC box, not the FPGA
> testbed. Remaining prototype roadmap (Coyote README status table;
> reads moved up per owner direction 2026-08-03): 5.2 aperture reads,
> local path (sim-tested) -> 5.3 loomd split -> 5.4 hardware gates
> G1/G2/G4 -> 5.5 first hardware run + T3/T2/floor/local-read-RTT
> measurements -> 6.1/6.2 two-host RDMA (resolves G3; remote reads via
> shell RDMA READ, T6 remote RTT).

> **UPDATE (2026-07-07): binding-first addressing; no tokens, no tags, no
> sequence numbers.** The datapath keys on per-aperture binding entries (see
> "Datapath folding"); the GFA, capability token, read tag, and sequence
> number have all been fully removed from the paper. Coyote's stock RoCE
> stack provides the transport (reliable, in-order RC); the vFPGA user logic
> does only the translations. The wire carries `⟨offset · op · len⟩` on the
> binding's RC connection; the connection identifies the segment at the
> receiver; read responses match positionally; isolation = source validation
> + orchestrator-installed entries + bounds checks. The body below is swept
> to match.

Validated approach (2026-07): two hosts, each with a Coyote-managed FPGA; two
CPU threads per host emulate XPUs; the vFPGA implements the Loom switch
(per-host controller deployment option); Coyote's RoCE stack is the
scale-out route; AstraSim extrapolates to rack/cluster scale.

## Emulation model & fidelity claims

| Loom concept | Prototype realization | Fidelity note |
|---|---|---|
| XPU | CPU thread (2 per host) | stores + DMA-kick are the whole data-path contract |
| XPU memory | any user memory mapped in Coyote's MMU (getMem, or `malloc` memory registered eagerly / faulted in on demand) | "XPU memory" := what the MMU maps, exactly as a real CE reads what the GPU page tables map (`cudaHostRegister` analog). Perf note: pre-map source ranges on the measurement path so no driver fault services a transfer |
| Peer aperture | per-cThread AXI-Lite ctrl region, address space partitioned by user logic into per-binding ranges (WC mapping) | **trapped by construction**; stock Coyote has no large data window — the aperture lives *inside* the ctrl region: small (tens–hundreds KB per cThread), so fine-grained stores reach only a compact head-of-segment window (design-faithful: apertures are compact windows; bulk uses DMA with full offsets). Per-cThread mappings give host-MMU isolation + ctid = source identity. AXI4 bypass patch (Gate 2) buys capacity *and* throughput |
| VA → aperture (level 1) | CPU MMU via mmap | GPU-MMU claim rests on GPUDirect peer-mapping argument; state explicitly |
| Copy engine | vFPGA DMA engine, descriptor doorbell in aperture, payload pulled via Coyote host streams | |
| Loom ToR switch | vFPGA user logic | per-host controller variant, not ToR; say so in the paper |
| Scale-up route | FPGA writes into the *other thread's* pinned buffer (same host) | models in-rack through-switch forwarding |
| Scale-out route | encapsulate → Coyote RoCE RC → far vFPGA → translate → write | models cross-rack |
| Orchestrator | daemon on one host; programs both vFPGAs via AXI-Lite CSRs | |
| Agent | user-space library (alloc/pin/export/import/map) | |
| data-then-flag ordering | WC stores + `sfence` between data and flag | GPU analog: `__threadfence_system` |

## Translation mapping onto Coyote's MMU

Coyote's shell MMU/TLB translates (context, userspace VA) → host PA for all
user-logic host-memory access. This realizes Loom's translations directly:

- **Destination translation**: our table maps `segment → (dest Coyote
  context, dest VA base)`, the message offset added on top; the shell TLB
  does VA→PA, absorbing scattered pages — the design's "per-segment page
  table" is *realized by* Coyote's TLB, so the prototype entry is
  base+offset, not a page table.
- **DMA pull**: descriptors carry the source buffer VA; Coyote translates
  during the pull.
- **Not Coyote's job**: level-1 VA→aperture is the host MMU (mmap of the
  vFPGA window); aperture→binding→route is our user-logic tables.
- **Per-process pointer fidelity**: `loom_import()` returns an mmap'd
  pointer, exactly as `cudaIpcOpenMemHandle` returns a fresh per-process
  mapping — the design's "single VA" property is per-process (one ordinary
  pointer names the peer buffer, identical for local and remote
  destinations), never a global VA, and the prototype preserves it:
  VA → host MMU → aperture PA → binding → dest PA is stage-for-stage the
  design's chain. **Requires emulated XPUs to be separate processes** so
  per-process page tables play the GPU MMU's isolation role (two tenants,
  same numeric VA, different bindings). Note: the "threads of one process"
  fallback under cross-context writes sacrifices this level-1 isolation
  demo — prefer the shared-registration-context fallback instead.

Verify early (Phase 0/1 gate):
1. **Cross-context writes** — user-logic-initiated host writes tagged with
   another attached cThread's context translate through that context's TLB.
   Fallback if not: register destination buffers in a shared context, or run
   both emulated XPUs as threads of one process.
2. **TLB pre-population** — register/attach buffers at export time so no
   page fault ever services the data path (faithful: design pins at
   registration).
3. **Hugepage-backed buffers** to keep TLB pressure trivial.

## The `loom_*` API is the vendor-API stand-in (no app-change contradiction)

The prototype has no CUDA runtime to interpose beneath, so the agent
library presents the vendor API surface directly; benchmarks call it as
real apps call CUDA. Mapping (state in the paper's methodology):
`loom_alloc` ≙ `cudaMalloc`; `loom_export` ≙ `cudaIpcGetMemHandle`;
`loom_import` ≙ `cudaIpcOpenMemHandle` + `cudaDeviceEnablePeerAccess`;
`loom_memcpy` ≙ `cudaMemcpy`; stores through `P_A` ≙ kernel stores through
the imported pointer. Each is signature- and semantics-equivalent (opaque
handle in, plain pointer out; no addresses, keys, or QPs visible), so in a
real deployment the agent hooks the vendor calls instead of exposing its
own. The prototype *demonstrates* the data/control path beneath this
surface; that the surface splices beneath real vendor calls is *argued*
from mechanism identity (pinning, dma-buf, peer mappings, handle exchange).

Optional transparency demo (no FPGA, one dual-GPU box): `LD_PRELOAD` shim
interposing `cudaDeviceCanAccessPeer`/IPC calls; show unmodified NCCL
selecting the peer path under our discovery answers.

## End-to-end walkthrough: both paths, allocation to execution

Actors: processes A, B (XPUs, host 1, vFPGA-1); process C (XPU, host 2,
vFPGA-2).

**Setup (shared):**
1. C (remote peer): `loom_alloc` → pinned buffer, C's plain pointer `VA_C`;
   Coyote TLB holds (C-ctx, `VA_C`) → PA. Export → orchestrator records
   segment `seg5`, programs vFPGA-2 translation `seg5 → (C-ctx, VA_C)` with
   bounds/perms; opaque handle `H_C` to A.
2. B (local peer, same host as A): `loom_alloc` → pinned buffer `VA_B`;
   export → segment `seg3`, programs **vFPGA-1** translation
   `seg3 → (B-ctx, VA_B)` with bounds/perms; handle `H_B` to A.
3. A imports both: agent resolves each handle, mmaps two slices of
   vFPGA-1's window → pointers `P_C` (BAR offset `0x30000`) and `P_B`
   (offset `0x20000`); orchestrator programs vFPGA-1 binding entries:
   `0x30000 → {remote: QP7 (identifies seg5 at the receiver)}` and
   `0x20000 → {local: seg3}`; permitted source=A on both.
   A never sees segments/QPs/`VA_B`/`VA_C` — two ordinary pointers,
   indistinguishable in type and use.

**Path 1 — small store:**
- *Local (A→B, no network):* `*P_B = x` → host MMU (level 1): `P_B` → BAR
  offset `0x20000` → AXI capture → level 2: binding entry → **local**
  (seg3), bounds check → translation `seg3 → (B-ctx, VA_B)` + offset →
  Coyote TLB → host-memory write into B's pinned buffer, same host. B polls
  its own `VA_B`. Everything happens inside vFPGA-1.
- *Remote (A→C):* `*P_C = x` → identical through capture and lookup →
  binding entry → **remote**, encap `⟨offset·W·len⟩` → QP7 → vFPGA-2: the
  connection identifies seg5, bounds check, translation
  `seg5 → (C-ctx, VA_C)` + offset, Coyote TLB → write. C polls `VA_C`.
- Same instruction, same code; divergence only at the binding-entry decode.

**Path 2 — DMA:** (`loom_memcpy` is *not* Coyote's stock `invoke()` between
two TLB-mapped local buffers — the peer buffer has no local VA on the
source host; the aperture pointer is its only local name, and the switch's
translation table, not the descriptor, holds the peer-side address.)
- *Local (A→B):* `loom_memcpy(P_B+off, VA_S, len)` → agent computes
  aperture offset from `P_B`'s mmap base (level 1, software, per
  descriptor) → descriptor `{0x20000+off, VA_S, len}` via doorbell →
  vFPGA-1 DMA pulls (A-ctx, `VA_S`) via host streams → injects at the same
  pipeline entry as captured stores → binding entry (local) → translation → Coyote write
  into B's buffer: a host-memory-to-host-memory copy through the switch,
  no network.
- *Remote (A→C):* `loom_memcpy(P_C+off, VA_S, len)` → identical until the
  binding-entry decode → encap → QP7 → vFPGA-2 translation → C's buffer.
- Descriptor retires on acceptance in both cases (posted completion).

**Equivalence statement:** the paths differ only in who produces the
(aperture offset, data) stream — MMU-translated PCIe capture vs.
descriptor-fed DMA engine — converging before translation; the same
relationship a warp store and a copy engine have in a real GPU.
App-visible shape is identical to CUDA: one pointer, one mapping;
dereference it or pass it to the copy API; doorbell/descriptor mechanics
hidden in the library exactly as CE programming is hidden in
`cudaMemcpy`. Fidelity deltas (state in paper):
1. Real copy engines share the GPU MMU; the prototype derives the DMA
   destination from `P_A` in the agent helper (software, descriptor time)
   rather than an MMU (hardware, per transaction). Same input, same
   mapping, same result.
2. Push vs. pull: a real CE *pushes* posted writes through the same fabric
   port as small stores; the vFPGA DMA *pulls* the payload via Coyote host
   streams and injects it at the same pipeline entry point. Same bytes,
   ordering point, and posted-completion rule; the switch ingress sees a
   pulled stream rather than pushed writes (as RDMA NICs do today).

## Address allocation & trapping (the resolved worry)

- **Trapping:** none needed. The aperture is FPGA-backed address space; the
  vFPGA sees address+data of every store. This is the whole point of
  backing the aperture with the switch.
- **Datapath folding (do this):** the source vFPGA keys directly on the
  aperture range with a precomputed entry `{local: (ctx, VA base) | remote:
  QP}` — segment resolution and route selection are composed at install
  time by the orchestrator. Segment IDs are control-plane state (what
  handles resolve to, what entries are compiled from); they never appear on
  the wire — the header is `⟨offset · op · len⟩` and the binding's RC
  connection identifies the segment at the receiver. (If a debug build ever
  carries a segment field, exclude it from goodput calibration.)
- **Flat window, not a mailbox:** the aperture must be a flat
  memory-mapped window where the AXI *address* alone carries the
  destination (offset → route via the folded entry) — never a
  destination/data/go CSR interface.
- **Window layout (Coyote reality):** the aperture is carved from each
  cThread's AXI-Lite ctrl region — user logic decodes (ctid, address) into
  (source, binding range, offset); translation is
  `offset = addr − range.base`; the binding entry supplies the rest. Ranges are sized to the
  ctrl-region budget (e.g., 4–64 KB per binding), not to full segments:
  fine-grained stores cover the window; DMA descriptors cover the whole
  segment. Guards: per-cThread mapping bounds at the host MMU (process
  granularity) + switch range/bounds checks (binding granularity).
  With the AXI4 bypass patch, ranges can grow toward full segment sizes.
- **No unified VA region — by design:** local buffers (RAM) and peer
  pointers (ctrl-region mapping) are separate mappings, exactly as
  `cudaMalloc` and IPC-imported pointers are on a real GPU (HBM PTEs vs.
  peer-BAR PTEs). What is unified: local-vs-remote peers (`P_B` ≍ `P_C`),
  one name per peer buffer across both paths (stores and `loom_memcpy`
  take the same pointer), plain-pointer interface. One artifact of the
  small window: `P_C` is *dereferenceable* over the aperture slice but
  *nameable* over the whole segment for DMA (pointer arithmetic, no
  dereference); disappears with the AXI4 patch. A mailbox would deviate from the
  design (commands instead of memory accesses), serialize concurrent
  bindings, and break the address-based-routing equivalence. The only
  registers are control-plane CSRs (orchestrator) and the DMA doorbell
  (inside `loom_memcpy`); the app touches neither.
- **Allocation:** agent library calls `loom_alloc/export` → pins via Coyote,
  gets DMA address, registers {host, buffer, len} with orchestrator →
  orchestrator assigns an internal segment ID, programs the destination
  vFPGA translation (`segment → Coyote buffer address`, bounds, perms) and,
  on import, the source vFPGA binding entry (`aperture range → {local:
  segment | remote: QP}`, permitted source-thread ID).

## Phases

### Phase 0 — Environment (1–2 wk)
Coyote v2 on both hosts (AMD Alveo U280, 100G link, direct or via
Ethernet switch). Reproduce stock examples: host↔vFPGA mmap store latency,
host-stream DMA bandwidth, two-host RoCE RC ping-pong. These numbers are the
substrate baselines everything is judged against.
Gate: confirm the three Coyote-MMU assumptions above (cross-context writes,
pre-population, hugepages) with a minimal two-process test.
Gate 2: determine the aperture interface — prefer a full AXI4
(burst-capable) host-mapped window (XDMA bypass-BAR class) for the data
path, AXI-Lite for CSRs/tables only. Rationale: PCIe pipelines posted 64B
TLPs at GB/s; the AXI-Lite bridge drains them beat-by-beat
(~100--200~MB/s) — the bottleneck is the bridge, not the link, so it is an
artificial floor a real aperture does not have. Either way, map the
aperture WC and issue AVX-512 (64B) stores so clean full-size TLPs arrive.
If only AXI-Lite is available: per-store latency measurements remain
representative (posted writes), relative comparisons survive if the
baseline rides the same substrate, but small-message bandwidth and
coalescing-benefit curves are substrate-floored — report them as such and
carry corrected rates into AstraSim.

### Phase 1 — Aperture + tables + local route (2–3 wk, single host)
vFPGA: AXI-Lite CSR block (table programming, status); aperture capture on
the AXI window; tables in BRAM (aperture range → binding entry
`{local: segment | remote: QP}`, segment → (bounds, perms), segment →
buffer base); source validation (thread/binding ID carried in aperture
offset partition to start); local forward engine writing destination
thread's pinned buffer.
Software: agent library + orchestrator daemon (TCP/gRPC).
Milestone: thread A → thread B data-then-flag through the vFPGA with
translation + bounds check. Measure: small-store latency vs. raw shared
memory; table-lookup pipeline cost.

### Phase 2 — Scale-out route (3–4 wk, two hosts)
TX encapsulator (Loom hdr: offset·op·len), coalescer (merge
consecutive small stores of a binding) / segmenter (MTU); QP router: one RC
per binding on Coyote's RoCE; RX decapsulator → bounds/permission check → translation →
write. Orchestrator programs both FPGAs; connection setup out of band.
Milestone: A(host1) → C(host2) same data-then-flag code as Phase 1.
Measure: small-write latency, streaming bandwidth vs. message size,
coalescing on/off, vs. CPU-verbs RDMA baseline (the "library" stand-in).

### Phase 3 — DMA path (2 wk)
Descriptor doorbell in aperture; vFPGA pulls payload from source buffer via
host streams; same routing/encap; completion = descriptor retired when data
accepted (posted semantics). Milestone: large transfers saturate link on
both routes; crossover point small-store vs. DMA measured.

### Phase 4 — Performance isolation + failure (3 wk) — **DESCOPED (2026-08 eval review §4: no isolation claim; VOQ = standard switch art; victim topology vacuous; T7/T8 dropped)**
Per-destination transmit queues (BRAM, DRAM spill if needed) + round-robin
scheduler; error containment unit (binding error CSR: drop writes, poison
reads, eventfd to agent).
Milestones: **victim-flow experiment** — A→X (congested/paused remote) and
A→Y (healthy) with/without per-destination queues; **failure experiment** —
kill remote host mid-stream, measure detection→containment time, show other
bindings unaffected.

### Phase 5 — Reads (2 wk) — **PLANNED, scoped to T6 calibration (read RTT lands as a measured value per the sweep policy; credit MODEL stays sim-side in sweep_credits; hardware tracker is trivially depth-1 under AXI-Lite's single-outstanding reads)**
Non-posted aperture reads with read-credit tracker (per-binding pending-read FIFO,
credits, completion held open across RTT). Watch PCIe completion timeout
config on the hosts. Measure local vs. remote read latency/outstanding
scaling. If timeouts prove hostile, document and restrict to DMA reads.

### Phase 6 — AstraSim scale-out (3–4 wk, overlaps 4–5) — **Tier 1 BUILT AND RUNNING (this repo, examples/loom); remaining input = the FPGA-owned constants above**
Principle: most of the Loom switch is *constants*, not behavior —
translation/bounds/encap = per-hop latency adder + goodput factor, both
measured on the prototype. Only congestion is behavioral, and the VOQ claim
is demonstrated on the prototype, not in simulation.

**Tier 1 — analytical backend (headline results, no ns-3):**
- Topology: N racks × M XPUs, Loom ToR per rack, Ethernet between racks.
- Link goodput = line rate × measured efficiency (Loom hdr bytes,
  coalescing); per-hop latency += measured switch pipeline.
- Loom vs. baseline lives in the *system-layer cost model*: Loom = zero
  XPU-side comm compute + source-local completion; GPU-initiated-RDMA
  baseline = measured SM/proxy overheads (§2 numbers) + completion RTTs.
- Workloads via Chakra traces (MoE all-to-all, DeepEP-like dispatch);
  sweep racks, XPUs/rack, message sizes.

**Tier 2 — thin ns-3 extension (only if congestion fidelity demanded):**
not a switch design — one custom QueueDisc (per-destination queues +
round-robin scheduler) installed on ToR ports, plus per-flow header
overhead for encapsulated bindings. Tables/translation never appear
in ns-3; they remain constants.

**Calibration inputs (from Phases 1–4):** switch pipeline latency,
per-message encap overhead, per-binding goodput vs. transfer size,
scheduler quantum, small-store issue rate (or its AXI-Lite-corrected
estimate per Phase 0 Gate 2).

## Risks & mitigations

- **WC ordering:** aperture stores may merge/reorder → `sfence` discipline
  in the agent's store helpers; document as the GPU-fence analog.
- **PCIe read timeouts:** phase-gated; write-only first; extend/relax
  completion timeout where BIOS allows.
- **Small-packet rate:** FPGA clock vs. 100G line rate for 64B stores → the
  coalescer is load-bearing; measure with/without.
- **QP scaling:** one RC per binding; 4 XPUs → ≤12 bindings, trivial;
  cluster-scale QP counts are an AstraSim parameter, discuss in paper
  (fix: `connection-scaling.md`).
- **Coyote version drift:** pin to a release; Jigsaw's fork is the fallback.

## Paper mapping (post-descope)

Phase 1–3 → implementation §7 + microbenchmarks; Phase 6 → end-to-end
evaluation; substrate baselines → overhead attribution (Loom vs. Coyote
floor). Dead after the 2026-08 eval review: the victim-flow "money plot"
(§6.4/§6.5) and the failure experiment; reads (§6.3) are argued from the
design + sim credit model, with optional testbed calibration.
