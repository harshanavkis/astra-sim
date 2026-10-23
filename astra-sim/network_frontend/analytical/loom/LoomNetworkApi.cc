// ASTRA-sim network API on the LoomNet analytical model (e8-astrasim/ANALYTICAL.md).
// A message between two GPUs of one server: NVLink by its bandwidth only (size / NVLINK_GBPS, arriving
// NVLINK_LAT_NS later; identical for both systems, as the ns-3 frontend's local_send). A message between servers:
// its puts (MSG_SPLIT_BYTES each, 0 = one put; MSG_SPLIT_HIGH_TAG: other size from a tag on) and then an 8 B signal put on the pair's queue pair; the receiver has
// the message when it sees the signal; the sender is released when it may reuse its buffer: Loom once its stores
// (the signal's last) have left the GPU, RDMA at the signal's CQE (SENDER_RELEASE post: at once). The sends a GPU
// issues at the same time are posted interleaved, one put of each in turn (as the ns-3 frontend's nic_flush).
#include "loom/LoomNetworkApi.hh"
#include <cassert>
#include <cstdio>
#include <map>

using namespace AstraSim;
using namespace AstraSimAnalytical;
using namespace AstraSimAnalyticalLoom;
using namespace NetworkAnalytical;

std::shared_ptr<LoomNet::Model> LoomNetworkApi::model;

namespace {
struct Pending {
    int dst, tag;
    uint64_t size, chunk_id;
    void (*handler)(void*);
    void* arg;
};
std::map<int, std::vector<Pending>> pending;               // src -> sends issued at this time
std::map<int, uint64_t> last_release, last_recv;           // per rank, ns (loom_rank line)
std::map<int, double> stage_busy;                          // STAGE_COPY: a GPU's staging copies, busy until (ns)
int finished_ranks = 0;
std::shared_ptr<LoomNet::Model> g_model;

void noop(void*) {}

struct Arrival { int tag, src, dst; uint64_t count; int chunk_id; };
void do_arrival(void* p);

double now_ns(EventQueue* q) { return (double)q->get_current_time(); }

EventQueue* g_eq = nullptr;

void at(double t, void (*fn)(void*), void* arg) {
    const auto now = g_eq->get_current_time();
    EventTime e = (EventTime)std::ceil(t);
    if (e < now) e = now;
    g_eq->schedule_event(e, fn, arg);
}

void release_at(int src, double t, void (*h)(void*), void* a) {
    struct R { int src; void (*h)(void*); void* a; };
    auto* r = new R{src, h, a};
    at(t, [](void* p) {
        auto* r = static_cast<R*>(p);
        last_release[r->src] = g_eq->get_current_time();
        r->h(r->a);
        delete r;
    }, r);
}

void arrival_at(double t, int tag, int src, int dst, uint64_t count, int chunk_id) {
    at(t, do_arrival, new Arrival{tag, src, dst, count, chunk_id});
}

// a send's class: 1 from MSG_SPLIT_HIGH_TAG on (MoE decode: combine), else 0 (dispatch)
int tag_class(const LoomNet::Config& c, int tag) {
    return c.split_high_tag >= 0 && tag >= c.split_high_tag;
}

// STAGE_COPY applies to this send: RDMA, a copy rate set, and no measured send loop for its class (which contains the copy)
bool staged(const LoomNet::Config& c, int tag) {
    return !c.push && c.stage_gbps > 0 && c.loop_ns[tag_class(c, tag)] <= 0;
}

// one put of a GPU's send loop at its post time: Loom stores it; RDMA writes its WQE and rings the queue pair if
// `ring` (DOORBELL_BATCH; a signal always rings)
void loop_put(int src, int dst, uint64_t b, bool ring, LoomNet::PutCallbacks cb) {
    LoomNet::Model& m = *g_model;
    const double t = now_ns(g_eq);
    if (m.cfg.push) {
        m.put(src, dst, 0, b, t, std::move(cb));
        return;
    }
    const uint64_t n = m.post_wqe(src, dst, 0, b, false, std::move(cb), t);
    if (ring) m.ring(src, dst, 0, n, t, true);
}

// the receiver side of CommonNetworkApi::process_chunk_arrival (the send handler registered there is a no-op;
// the real sender release is its own event)
void do_arrival(void* p) {
    auto* a = static_cast<Arrival*>(p);
    last_recv[a->dst] = g_eq->get_current_time();
    auto& tracker = CommonNetworkApi::get_callback_tracker();
    const auto entry = tracker.search_entry(a->tag, a->src, a->dst, a->count, a->chunk_id);
    assert(entry.has_value());
    if (entry.value()->both_callbacks_registered()) {
        entry.value()->invoke_send_handler();
        entry.value()->invoke_recv_handler();
        tracker.pop_entry(a->tag, a->src, a->dst, a->count, a->chunk_id);
    } else {
        entry.value()->invoke_send_handler();
        entry.value()->set_transmission_finished();
    }
    delete a;
}

void flush(void* p) {
    const int src = (int)(intptr_t)p;
    std::vector<Pending> v;
    v.swap(pending[src]);
    LoomNet::Model& m = *g_model;
    const double t = now_ns(g_eq);
    const uint64_t split = m.cfg.msg_split;
    // the puts in posting order: one put of each send in turn, a send's signal right after its last put
    struct Post { size_t i; uint64_t b; bool sig; };
    std::vector<Post> seq;
    std::vector<uint64_t> off(v.size(), 0);
    std::vector<bool> done(v.size(), false);
    for (bool more = true; more;) {
        more = false;
        for (size_t i = 0; i < v.size(); i++) {
            if (done[i]) continue;
            auto& s = v[i];
            if (off[i] < s.size) {
                const uint64_t sp = tag_class(m.cfg, s.tag) ? m.cfg.split_high : split;
                const uint64_t b = std::min<uint64_t>(sp ? sp : s.size, s.size - off[i]);
                if (staged(m.cfg, s.tag) && m.cfg.stage_chunk) {
                    // STAGE_COPY chunks: the turn's put goes out as consecutive chunks (posting order as without staging;
                    // chunks of different sends are not interleaved, owner 2026-10-21: whole puts FIFO in both systems)
                    for (uint64_t o = 0; o < b; o += m.cfg.stage_chunk)
                        seq.push_back(Post{i, std::min<uint64_t>(m.cfg.stage_chunk, b - o), false});
                } else {
                    seq.push_back(Post{i, b, false});
                }
                off[i] += b;
            }
            if (off[i] >= s.size) {
                seq.push_back(Post{i, 8, true});
                done[i] = true;
            } else {
                more = true;
            }
        }
    }
    // without a send loop every put is posted now; with one (POST_LOOP_NS) the k-th of a class's N puts at
    // t + L (first + (last - first) k / (N - 1)), the signals at t + L
    uint64_t nd[2] = {0, 0}, kd[2] = {0, 0};
    for (const auto& p : seq)
        if (!p.sig) nd[tag_class(m.cfg, v[p.i].tag)]++;
    std::map<int, uint64_t> per_dst;   // puts per destination in this loop (doorbell batching)
    std::vector<double> last_post(v.size(), t);   // STAGE_COPY: a send's last copied put (its signal follows)
    for (const auto& p : seq) {
        const auto& s = v[p.i];
        const int c = tag_class(m.cfg, s.tag);
        const double L = m.cfg.loop_ns[c];
        const bool st = staged(m.cfg, s.tag);
        double tp = t;
        bool ring = true;
        if (st) {
            if (p.sig) {
                tp = last_post[p.i];
            } else {
                double& busy = stage_busy[src];
                busy = std::max(busy, t) + (double)p.b / m.cfg.stage_gbps;
                tp = last_post[p.i] = busy + m.cfg.stage_ns;
            }
        } else if (L > 0) {
            if (p.sig) {
                tp = t + L;
            } else {
                const double f0 = m.cfg.loop_first[c], f1 = m.cfg.loop_last[c];
                tp = t + L * (f0 + (f1 - f0) * (nd[c] > 1 ? (double)kd[c] / (double)(nd[c] - 1) : 1.0));
                kd[c]++;
                const uint64_t q = ++per_dst[s.dst];
                ring = m.cfg.db_batch && q % m.cfg.db_batch == 0;
            }
        }
        LoomNet::PutCallbacks cb;
        if (p.sig) {
            // the signal, behind the data: the receiver has the message when it sees it; the sender is
            // released when its stores are out (Loom) or at the signal's CQE (RDMA; SENDER_RELEASE post: now)
            const int tag = s.tag, dst = s.dst; const uint64_t size = s.size; const int cid = (int)s.chunk_id;
            auto h = s.handler; auto a = s.arg;
            cb.seen = [tag, src, dst, size, cid](double t) { arrival_at(t, tag, src, dst, size, cid); };
            if (m.cfg.push) cb.out = [src, h, a](double t) { release_at(src, t, h, a); };
            else if (!m.cfg.release_on_post) cb.cqe = [src, h, a](double t) { release_at(src, t, h, a); };
            else release_at(src, tp, h, a);
        }
        if (L <= 0 && !st) {
            m.put(src, s.dst, 0, p.b, t, std::move(cb));
            continue;
        }
        const int dst = s.dst; const uint64_t b = p.b;
        m.schedule(tp, [src, dst, b, ring, cb]() { loop_put(src, dst, b, ring, cb); });
    }
}
}  // namespace

void LoomNetworkApi::set_model(std::shared_ptr<LoomNet::Model> m) noexcept {
    model = m;
    g_model = m;
    m->schedule = [](double t, std::function<void()> fn) {
        auto* f = new std::function<void()>(std::move(fn));
        at(t, [](void* p) {
            auto* f = static_cast<std::function<void()>*>(p);
            (*f)();
            delete f;
        }, f);
    };
}

LoomNetworkApi::LoomNetworkApi(const int rank) noexcept : CommonNetworkApi(rank) {
    g_eq = event_queue.get();
}

int LoomNetworkApi::sim_send(void* const, const uint64_t count, const int, const int dst, const int tag,
                             sim_request* const, void (*msg_handler)(void*), void* const fun_arg) {
    const int src = sim_comm_get_rank();
    const auto chunk_id = chunk_id_generator.create_send_chunk_id(tag, src, dst, count);
    const auto entry = callback_tracker.search_entry(tag, src, dst, count, chunk_id);
    auto* e = entry.has_value() ? entry.value() : callback_tracker.create_new_entry(tag, src, dst, count, chunk_id);
    e->register_send_callback(noop, nullptr);
    if (model->same_server(src, dst)) {
        // NVLink, identical for both systems; with a send loop (POST_LOOP_NS) its signal too waits for the loop's end
        const double t = now_ns(g_eq);
        const double d = std::max(count / model->cfg.nvlink_gbps, model->cfg.loop_ns[tag_class(model->cfg, tag)]);
        release_at(src, t + d, msg_handler, fun_arg);
        arrival_at(t + d + model->cfg.nvlink_lat_ns, tag, src, dst, count, (int)chunk_id);
        return 0;
    }
    auto& v = pending[src];
    if (v.empty()) g_eq->schedule_event(g_eq->get_current_time(), flush, (void*)(intptr_t)src);
    v.push_back(Pending{dst, tag, count, (uint64_t)chunk_id, msg_handler, fun_arg});
    return 0;
}

void LoomNetworkApi::sim_notify_finished() {
    const int r = sim_comm_get_rank();
    finished_ranks++;
    printf("loom_rank %d sends_released_ns %lu last_recv_ns %lu finished_ns %lu\n", r,
           (unsigned long)last_release[r], (unsigned long)last_recv[r], (unsigned long)g_eq->get_current_time());
    fflush(stdout);
}

int LoomNetworkApi::finished() noexcept {
    return finished_ranks;
}

double LoomNetworkApi::get_BW_at_dimension(const int) {
    return model->topo.link_gbps;
}
