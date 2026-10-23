// an_replay: the prototype's microbenchmark / dispatch / collective patterns on the LoomNet analytical model
// (astra-sim-fresh .../include/loom/LoomNet.hh, the model the ASTRA-sim frontend uses). Same run-file and out-file
// format as val_model's proto-replay (ns-3), so ~/loom-experiments/val_model/run_val.py can drive either.
//   an_replay <config> <run file> <out file>
// Run file, one flow per line (times in ns):
//   flow <id> <src> <dst> <qp> <n> <bytes> <signal 0|1> <flush 0|1> <sq> start <t>
//   flow <id> <src> <dst> <qp> <n> <bytes> <signal 0|1> <flush 0|1> <sq> after <flow id>
// A flow posts n writes of <bytes> back to back (posting costs nothing), then (signal 1) an 8 B write behind them:
// at once, or (flush 1) once every data write has completed. sq > 0: a post waits while sq writes are outstanding
// (a completion frees a slot). "after F": starts when F is done at its receiver (its signal seen, or its last write).
// Out file: flow <id> <start> <posted> <last_data_seen> <signal_seen> <all_completions> <sender_out>  (ns, -1 n/a)
// Build: e8-astrasim/tools/build_an_replay.sh
#include "LoomNet.hh"
#include <functional>

struct Flow {
    int id, src, dst, qp, sq;
    uint64_t n, bytes;
    bool signal, flush;
    double t0 = -1;
    int after = -1;
    uint64_t posted = 0, cqes = 0, seen = 0;
    bool sig_posted = false, started = false, done = false;
    double t_start = -1, t_posted = -1, t_last = -1, t_sig = -1, t_cqe = -1, t_out = -1;
};

struct Ev { double t; uint64_t seq; std::function<void()> fn; };
struct EvCmp { bool operator()(const Ev& a, const Ev& b) const { return a.t > b.t || (a.t == b.t && a.seq > b.seq); } };
static std::priority_queue<Ev, std::vector<Ev>, EvCmp> q;
static uint64_t seqn = 0;
static double now = 0;
static void at(double t, std::function<void()> fn) { q.push(Ev{std::max(t, now), seqn++, std::move(fn)}); }

static LoomNet::Model M;
static std::vector<Flow> F;
static void start(Flow& f);

static void done(Flow& f) {
    if (f.done) return;
    f.done = true;
    for (auto& g : F)
        if (g.after == f.id && !g.started) start(g);
}

static void pump(Flow& f) {
    if (!f.started) return;
    auto room = [&f]() { return f.sq == 0 || f.posted + f.sig_posted - f.cqes < (uint64_t)f.sq; };
    auto post = [&f](uint64_t bytes, bool sig) {
        Flow* fp = &f;
        LoomNet::PutCallbacks cb;
        cb.out = [fp](double t) { fp->t_out = std::max(fp->t_out, t); };
        cb.seen = [fp, sig](double) {
            if (sig) { fp->t_sig = now; done(*fp); }
            else {
                fp->seen++;
                fp->t_last = std::max(fp->t_last, now);
                if (!fp->signal && fp->seen == fp->n) done(*fp);
            }
        };
        cb.cqe = [fp](double) {
            fp->cqes++;
            if (fp->cqes == fp->n + (fp->signal ? 1 : 0)) fp->t_cqe = now;
            pump(*fp);
        };
        M.put(f.src, f.dst, f.qp, bytes, now, cb);
    };
    while (f.posted < f.n && room()) {
        post(f.bytes, false);
        f.posted++;
        if (f.posted == f.n && !f.signal) f.t_posted = now;
    }
    if (f.posted == f.n && f.signal && !f.sig_posted && room() && (!f.flush || f.cqes >= f.n)) {
        post(8, true);
        f.sig_posted = true;
        f.t_posted = now;
    }
}

static void start(Flow& f) {
    f.started = true;
    f.t_start = now;
    pump(f);
}

int main(int argc, char* argv[]) {
    if (argc != 4) { std::cerr << "usage: an_replay <config> <run file> <out file>\n"; return 1; }
    std::ifstream rf(argv[2]);
    std::string line;
    while (std::getline(rf, line)) {
        std::istringstream is(line);
        std::string k, when;
        if (!(is >> k) || k[0] == '#') continue;
        if (k != "flow") { std::cerr << "bad run file key " << k << "\n"; return 1; }
        Flow f;
        int sig, fl;
        is >> f.id >> f.src >> f.dst >> f.qp >> f.n >> f.bytes >> sig >> fl >> f.sq >> when;
        f.signal = sig; f.flush = fl;
        if (when == "start") is >> f.t0;
        else if (when == "after") is >> f.after;
        else { std::cerr << "bad flow line: " << line << "\n"; return 1; }
        F.push_back(f);
    }
    if (!M.init(argv[1])) return 1;
    M.schedule = [](double t, std::function<void()> fn) { at(t, std::move(fn)); };
    for (size_t i = 0; i < F.size(); i++)
        if (F[i].after < 0) { Flow* fp = &F[i]; at(fp->t0, [fp]() { start(*fp); }); }
    while (!q.empty()) {
        Ev e = q.top(); q.pop();
        now = e.t;
        e.fn();
    }
    std::ofstream of(argv[3]);
    auto ns = [](double t) { return t < 0 ? (long long)-1 : (long long)std::llround(t); };
    for (auto& f : F)
        of << "flow " << f.id << " " << ns(f.t_start) << " " << ns(f.t_posted) << " " << ns(f.t_last) << " "
           << ns(f.t_sig) << " " << ns(f.t_cqe) << " " << ns(f.t_out) << "\n";
    return 0;
}
