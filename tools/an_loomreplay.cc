// an_loomreplay: replays one measured GPU-initiated dispatch/combine run (Section 2, steve: H200 + CX-7) on the LoomNet
// analytical model; the analytical counterpart of ns-3's scratch/loom-replay.cc (same run and out formats), so
// tools/val_dispatch.py compares it with the measurement unchanged. The sender's posts, doorbells and signals come from
// the run (GPU side measured); the NIC, PCIe and network are the model.
//   an_loomreplay <config> <run file> <out file>
// Run file (ns from the sender's first CTA start): path ordered|flush, nodes <src> <dst>, nqp <n>, reap 0|1,
//   msg <id> <post> <qp> <bytes> <ring>, ring <qp> <t> <n> (measured doorbell for the QP's first n WQEs),
//   atomic <qp> <t> <i> (signal i, an RDMA atomic, written on qp at t), drain <t> (ignored).
//   Only the measured-doorbell form (ring/atomic lines) is supported (val_dispatch/20261010_ring).
// Out file: "msg <id> <seen> <cqe>" per message, then
//   "sum <arr_first> <arr_last> <drain_end> <signal> <seen> <reaped> <sender_out>" (ns, -1 n/a).
// Build: tools/build_an_replay.sh
#include "LoomNet.hh"
#include <functional>

struct Ev { double t; uint64_t seq; std::function<void()> fn; };
struct EvCmp { bool operator()(const Ev& a, const Ev& b) const { return a.t > b.t || (a.t == b.t && a.seq > b.seq); } };
static std::priority_queue<Ev, std::vector<Ev>, EvCmp> q;
static uint64_t seqn = 0;
static double now = 0;
static void at(double t, std::function<void()> fn) { q.push(Ev{std::max(t, now), seqn++, std::move(fn)}); }

struct Msg { uint64_t id, post, qp, bytes; int ring; };
struct Ring { uint32_t qp; uint64_t t, n; };
struct Atom { uint32_t qp; uint64_t t, i; };

int main(int argc, char* argv[]) {
    if (argc != 4) { std::cerr << "usage: an_loomreplay <config> <run file> <out file>\n"; return 1; }
    std::string path; uint32_t src = 0, dst = 1, nqp = 0; bool reap = false;
    std::vector<Msg> msgs; std::vector<Ring> rings; std::vector<Atom> atoms;
    std::ifstream rf(argv[2]);
    std::string k;
    while (rf >> k) {
        if (k == "path") rf >> path;
        else if (k == "nodes") rf >> src >> dst;
        else if (k == "nqp") rf >> nqp;
        else if (k == "reap") rf >> reap;
        else if (k == "msg") { Msg m; rf >> m.id >> m.post >> m.qp >> m.bytes >> m.ring; msgs.push_back(m); }
        else if (k == "ring") { Ring r; rf >> r.qp >> r.t >> r.n; rings.push_back(r); }
        else if (k == "atomic") { Atom a; rf >> a.qp >> a.t >> a.i; atoms.push_back(a); }
        else if (k == "drain") { uint64_t t; rf >> t; }
        else if (k == "cta") { uint64_t t; rf >> t; }                         // with measured doorbells: unused (as loom-replay)
        else if (k == "signal") { std::string line; std::getline(rf, line); } // with measured doorbells: unused
        else if (k == "sigkind") { std::string v; rf >> v; if (v != "atomic") { std::cerr << "only atomic signals\n"; return 1; } }
        else { std::cerr << "an_loomreplay: unsupported run file key " << k << " (only the measured-doorbell form)\n"; return 1; }
    }
    if (rings.empty()) { std::cerr << "an_loomreplay: no ring lines (only the measured-doorbell form)\n"; return 1; }
    LoomNet::Model M;
    if (!M.init(argv[1])) return 1;
    M.schedule = [](double t, std::function<void()> fn) { at(t, std::move(fn)); };

    std::map<uint64_t, double> seen, cqe;
    std::vector<uint64_t> wqes(nqp, 0), data_wqes(nqp, 0), done(nqp, 0), data_done(nqp, 0);
    double drain = -1, signal = -1, reaped = -1, sender_out = -1;
    size_t atoms_posted = 0;
    const uint64_t SIG = 1000000000ull;
    auto check = [&]() {
        if (path == "flush" && drain < 0) {
            bool all = true;
            for (uint32_t x = 0; x < nqp; x++) all = all && data_done[x] >= data_wqes[x];
            if (all) drain = now;
        }
        if (reap && reaped < 0 && atoms_posted == atoms.size()) {
            bool all = true;
            for (uint32_t x = 0; x < nqp; x++) all = all && done[x] >= wqes[x];
            if (all) reaped = now;
        }
    };
    auto post = [&](uint32_t qp, uint64_t id, uint64_t bytes, bool atomic) {
        LoomNet::PutCallbacks cb;
        cb.out = [&](double t) { sender_out = std::max(sender_out, t); };
        cb.seen = [&, id](double) { seen[id] = now; };
        cb.cqe = [&, id, qp, atomic](double) {
            cqe[id] = now;
            done[qp]++;
            if (!atomic) data_done[qp]++;
            check();
        };
        wqes[qp]++;
        if (!atomic) data_wqes[qp]++;
        M.post_wqe(src, dst, qp, bytes, atomic, cb, now);
    };
    // events: posts (WQE writes) first at a given time, then atomics, then rings (as loom-replay schedules them)
    std::stable_sort(msgs.begin(), msgs.end(), [](const Msg& a, const Msg& b) { return a.post < b.post; });
    for (auto& m : msgs) at((double)m.post, [&, m]() { post(m.qp, m.id, m.bytes, false); });
    for (auto& a : atoms) at((double)a.t, [&, a]() {
        atoms_posted++;
        if (signal < 0 || (double)a.t < signal) signal = a.t;
        post(a.qp, SIG + a.i, 8, true);
    });
    for (auto& r : rings) at((double)r.t, [&, r]() { M.ring(src, dst, r.qp, r.n, now); });
    while (!q.empty()) {
        Ev e = q.top(); q.pop();
        now = e.t;
        e.fn();
    }
    FILE* out = fopen(argv[3], "w");
    auto ns = [](double t) { return t < 0 ? (long)-1 : (long)std::llround(t); };
    double first = -1, last = -1, sseen = -1;
    for (auto& m : msgs) {
        auto it = seen.find(m.id); auto c = cqe.find(m.id);
        const double t = it == seen.end() ? -1 : it->second;
        fprintf(out, "msg %lu %ld %ld\n", (unsigned long)m.id, ns(t), ns(c == cqe.end() ? -1 : c->second));
        if (t >= 0) { first = first < 0 ? t : std::min(first, t); last = std::max(last, t); }
    }
    bool all = true;
    for (auto& a : atoms) {
        auto it = seen.find(SIG + a.i);
        if (it == seen.end()) all = false; else sseen = std::max(sseen, it->second);
    }
    fprintf(out, "sum %ld %ld %ld %ld %ld %ld %ld\n", ns(first), ns(last), ns(drain), ns(signal), all ? ns(sseen) : -1L,
            ns(reaped), ns(sender_out));
    fclose(out);
    return 0;
}
