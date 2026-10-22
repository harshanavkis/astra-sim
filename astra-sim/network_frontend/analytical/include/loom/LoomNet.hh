// LoomNet: analytical (closed-form, per put) model of the host interface and the network for Loom and for a
// GPU-initiated RDMA NIC. No packets, no chunks: every put (one software write of a message) gets its times from
// formulas over a few busy-until resources (Opus-style link reservation). Shared by the ASTRA-sim frontend
// (AstraSim_Analytical_Loom) and the validation replay tool (e8-astrasim/tools/an_replay.cc). Each stage of a put is
// a formula evaluated at the stage's own time (event order), so busy-until resources are taken in time order.
// Documentation, formulas and parameter sources: /scratch/harshanavkis/loom-proj/e8-astrasim/ANALYTICAL.md
//
// Inputs are the SAME files the ns-3 runs used (cluster rdma.txt / loom.txt and their TOPOLOGY_FILE), so every
// parameter is identical; only the keys listed in Config are read, the rest (ns-3 switch/PFC settings) are ignored.
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <deque>
#include <functional>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <queue>
#include <sstream>
#include <string>
#include <tuple>
#include <vector>

namespace LoomNet {

enum Ep { HOST = 0, GPU = 1, NIC = 2 };

struct Config {
    std::string topology_file;
    uint32_t gpus_per_server = 0;            // >0: GPUs of one server talk over NVLink (bandwidth only)
    double nvlink_gbps = 400, nvlink_lat_ns = 936.25;
    bool push = false;                       // NIC_PUSH 1 = Loom: the poster's stores carry the data
    bool bf = false;                         // NIC_BF 1: the WQE goes with the doorbell (no WQE fetch)
    uint64_t inline_max = 0;                 // payload <= this rides with the WQE (no payload read)
    uint32_t wqe_bytes = 64, wqe_fetch_max = 64, mrrs = 512, rd_inflight = 128, chunk = 4096;
    double nic_tx_ns = 0, nic_rx_ns = 0, rx_poll_ns = 0, cqe_poll_ns = 0;
    int sq_mem = GPU, buf_mem = GPU, cq_mem = GPU, rx_mem = GPU, poster = GPU;
    double pcie_gbps = 57.6;                 // GB/s = B/ns, per direction, payload
    double tx_buf = 0;                       // LOOM_TX_BUF_BYTES: Loom's transmit buffer per port (0 = unlimited); a
                                             // store is accepted once at most this many bytes wait ahead of it; sensitivity only
    double rd_gpu_ns = 1350, rd_host_ns = 680, wr_gpu_ns = 700, wr_host_ns = 340, db_gpu_ns = 700, db_host_ns = 340;
    uint32_t mtu = 1000, wire_bytes = 0;     // PACKET_PAYLOAD_SIZE, WIRE_BYTES_PER_PACKET
    uint32_t atomic_wire = 20;               // ATOMIC_WIRE: an atomic request's extra bytes on the wire (AtomicETH 28 B)
    uint64_t msg_split = 0;                  // MSG_SPLIT_BYTES: puts per message (0 = one put)
    int split_high_tag = -1;                 // MSG_SPLIT_HIGH_TAG <tag> <bytes>: messages with comm_tag >= tag are split at
    uint64_t split_high = 0;                 // <bytes> instead (MoE decode: dispatch 7 KiB and combine 14 KiB puts in one run)
    bool release_on_post = false;            // SENDER_RELEASE post
    std::map<int, int> node_host;            // NODE_HOST <node> <host>: the node's NIC sits on that host's PCIe

    static int ep(const std::string& s) { return s == "host" ? HOST : s == "nic" ? NIC : GPU; }

    bool read(const std::string& path) {
        std::ifstream f(path);
        if (!f) { std::cerr << "LoomNet: cannot open " << path << "\n"; return false; }
        std::string line;
        while (std::getline(f, line)) {
            std::istringstream is(line);
            std::string k;
            if (!(is >> k) || k[0] == '#') continue;
            std::string s;
            if (k == "TOPOLOGY_FILE") is >> topology_file;
            else if (k == "GPUS_PER_SERVER") is >> gpus_per_server;
            else if (k == "NVLINK_GBPS") is >> nvlink_gbps;
            else if (k == "NVLINK_LAT_NS") is >> nvlink_lat_ns;
            else if (k == "NIC_PUSH") { int v; is >> v; push = v; }
            else if (k == "NIC_BF") { int v; is >> v; bf = v; }
            else if (k == "INLINE_MAX") is >> inline_max;
            else if (k == "WQE_BYTES") is >> wqe_bytes;
            else if (k == "WQE_FETCH_MAX") is >> wqe_fetch_max;
            else if (k == "PCIE_MRRS") is >> mrrs;
            else if (k == "PCIE_RD_INFLIGHT") is >> rd_inflight;
            else if (k == "HIF_CHUNK") is >> chunk;
            else if (k == "NIC_TX_NS") is >> nic_tx_ns;
            else if (k == "NIC_RX_NS") is >> nic_rx_ns;
            else if (k == "RX_POLL_NS") is >> rx_poll_ns;
            else if (k == "CQE_POLL_NS") is >> cqe_poll_ns;
            else if (k == "NIC_SQ_MEM") { is >> s; sq_mem = ep(s); }
            else if (k == "NIC_BUF_MEM") { is >> s; buf_mem = ep(s); }
            else if (k == "NIC_CQ_MEM") { is >> s; cq_mem = ep(s); }
            else if (k == "NIC_RX_MEM") { is >> s; rx_mem = ep(s); }
            else if (k == "NIC_POSTER") { is >> s; poster = ep(s); }
            else if (k == "PCIE_LINK_GBPS") is >> pcie_gbps;
            else if (k == "LOOM_TX_BUF_BYTES") is >> tx_buf;
            else if (k == "PCIE_RD_GPU_NS") is >> rd_gpu_ns;
            else if (k == "PCIE_RD_HOST_NS") is >> rd_host_ns;
            else if (k == "PCIE_WR_GPU_NS") is >> wr_gpu_ns;
            else if (k == "PCIE_WR_HOST_NS") is >> wr_host_ns;
            else if (k == "PCIE_DB_GPU_NS") is >> db_gpu_ns;
            else if (k == "PCIE_DB_HOST_NS") is >> db_host_ns;
            else if (k == "PACKET_PAYLOAD_SIZE") is >> mtu;
            else if (k == "WIRE_BYTES_PER_PACKET") is >> wire_bytes;
            else if (k == "MSG_SPLIT_BYTES") is >> msg_split;
            else if (k == "MSG_SPLIT_HIGH_TAG") is >> split_high_tag >> split_high;
            else if (k == "ATOMIC_WIRE") is >> atomic_wire;
            else if (k == "SENDER_RELEASE") { is >> s; release_on_post = (s == "post"); }
            else if (k == "NODE_HOST") { int a, b; is >> a >> b; node_host[a] = b; }
        }
        return true;
    }
    double rd_lat(int mem) const { return mem == GPU ? rd_gpu_ns : rd_host_ns; }
    double wr_lat(int mem) const { return mem == GPU ? wr_gpu_ns : wr_host_ns; }   // NIC -> memory, visible
    double db_lat(int from) const { return from == GPU ? db_gpu_ns : db_host_ns; } // store -> at the NIC
};

// The network between NICs: the ns-3 topology file (same format), every host link at the same rate.
// Per host pair: one-way propagation (sum of link delays) and the switches on the shortest path.
struct Topology {
    int nodes = 0;
    std::vector<bool> is_switch;
    std::vector<std::vector<std::pair<int, double>>> adj;   // (peer, delay ns)
    double link_gbps = 0;                                    // GB/s of the host links (B/ns)
    std::map<std::pair<int, int>, std::pair<double, int>> path_cache;
    std::map<std::pair<int, int>, int> link_id;              // directed link (u, v) -> resource index
    std::map<int, std::vector<double>> dist_cache;           // destination -> lowest delay from every node
    struct Hop { int link; double delay; };

    static double rate_gbps(const std::string& s) {         // "400Gbps" -> GB/s
        double v = std::stod(s);
        if (s.find("Gbps") != std::string::npos) return v / 8;
        if (s.find("Mbps") != std::string::npos) return v / 8000;
        return v / 8e9;
    }
    static double delay_ns(const std::string& s) {          // "0.000155ms" -> ns
        double v = std::stod(s);
        if (s.find("ms") != std::string::npos) return v * 1e6;
        if (s.find("us") != std::string::npos) return v * 1e3;
        if (s.find("ns") != std::string::npos) return v;
        return v * 1e9;
    }
    bool read(const std::string& path) {
        std::ifstream f(path);
        if (!f) { std::cerr << "LoomNet: cannot open topology " << path << "\n"; return false; }
        int sw, links;
        f >> nodes >> sw >> links;
        is_switch.assign(nodes, false);
        adj.assign(nodes, {});
        for (int i = 0; i < sw; i++) { int s; f >> s; is_switch[s] = true; }
        for (int i = 0; i < links; i++) {
            int a, b; std::string r, d; double err;
            f >> a >> b >> r >> d >> err;
            double dl = delay_ns(d);
            adj[a].push_back({b, dl});
            adj[b].push_back({a, dl});
            link_id[{a, b}] = (int)link_id.size();
            link_id[{b, a}] = (int)link_id.size();
            if (!is_switch[a] || !is_switch[b]) link_gbps = link_gbps > 0 ? std::min(link_gbps, rate_gbps(r)) : rate_gbps(r);
        }
        return true;
    }
    const std::vector<double>& dist_to(int dst) {
        auto it = dist_cache.find(dst);
        if (it != dist_cache.end()) return it->second;
        std::vector<double> d(nodes, 1e300);
        using QE = std::pair<double, int>;
        std::priority_queue<QE, std::vector<QE>, std::greater<QE>> q;
        d[dst] = 0; q.push({0, dst});
        while (!q.empty()) {
            auto [du, u] = q.top(); q.pop();
            if (du > d[u]) continue;
            if (u != dst && !is_switch[u]) continue;         // hosts do not forward
            for (auto [v, dl] : adj[u])
                if (du + dl < d[v]) { d[v] = du + dl; q.push({d[v], v}); }
        }
        return dist_cache[dst] = d;
    }
    // ECMP exactly as ns-3's switches (switch-node.cc GetOutDev / EcmpHash): next hops toward dst = the neighbours one
    // BFS hop closer (ns-3 CalculateRoute, in ascending node id = its node-map order), picked by murmur3-32 over
    // (src IP, dst IP, sport | dport << 16) seeded with the switch's node id; IP = 11.x.y.1 from the node id
    // (common.h node_id_to_ip); a NIC-mode queue pair uses sport 30000 + qp, dport 100 (rdma-hw.cc NicQp)
    static uint32_t ip_of(int id) { return 0x0b000001u + (uint32_t)(id / 256) * 0x00010000u + (uint32_t)(id % 256) * 0x00000100u; }
    static uint32_t ecmp_hash(const uint32_t* w, size_t n, uint32_t seed) {
        uint32_t h = seed;
        for (size_t i = 0; i < n; i++) {
            uint32_t k = w[i];
            k *= 0xcc9e2d51; k = (k << 15) | (k >> 17); k *= 0x1b873593;
            h ^= k; h = (h << 13) | (h >> 19); h += (h << 2) + 0xe6546b64;
        }
        h ^= (uint32_t)(n * 4);
        h ^= h >> 16; h *= 0x85ebca6b; h ^= h >> 13; h *= 0xc2b2ae35; h ^= h >> 16;
        return h;
    }
    std::map<int, std::vector<int>> hops_cache;               // destination -> BFS hop count from every node
    const std::vector<int>& hops_to(int dst) {
        auto it = hops_cache.find(dst);
        if (it != hops_cache.end()) return it->second;
        std::vector<int> d(nodes, -1);
        std::vector<int> q{dst};
        d[dst] = 0;
        for (size_t i = 0; i < q.size(); i++) {
            const int u = q[i];
            if (u != dst && !is_switch[u]) continue;
            for (auto [v, dl] : adj[u])
                if (d[v] < 0) { d[v] = d[u] + 1; q.push_back(v); }
        }
        return hops_cache[dst] = d;
    }
    std::vector<Hop> route(int src, int dst, int qp) {
        const auto& d = hops_to(dst);
        const uint32_t key[3] = {ip_of(src), ip_of(dst), (uint32_t)(30000 + qp) | (100u << 16)};
        std::vector<Hop> r;
        int u = src;
        while (u != dst) {
            std::vector<std::pair<int, double>> nh;
            for (auto [v, dl] : adj[u])
                if ((v == dst || is_switch[v]) && d[v] == d[u] - 1) nh.push_back({v, dl});
            if (nh.empty()) { std::cerr << "LoomNet: no route " << src << " -> " << dst << "\n"; std::exit(1); }
            std::sort(nh.begin(), nh.end());
            static const uint32_t salt = getenv("LOOMNET_ECMP_SALT") ? (uint32_t)atoi(getenv("LOOMNET_ECMP_SALT")) : 0;
            const size_t i = nh.size() == 1 ? 0 : ecmp_hash(key, 3, (uint32_t)u + salt * 7919u) % nh.size();   // salt: sensitivity only
            r.push_back({link_id[{u, nh[i].first}], nh[i].second});
            u = nh[i].first;
        }
        return r;
    }
    // (propagation ns, switches on the path) of the lowest-delay path
    std::pair<double, int> path(int a, int b) {
        auto key = std::make_pair(std::min(a, b), std::max(a, b));
        auto it = path_cache.find(key);
        if (it != path_cache.end()) return it->second;
        std::vector<double> dist(nodes, 1e300);
        std::vector<int> hops(nodes, 0);
        using QE = std::pair<double, int>;
        std::priority_queue<QE, std::vector<QE>, std::greater<QE>> q;
        dist[a] = 0; q.push({0, a});
        while (!q.empty()) {
            auto [d, u] = q.top(); q.pop();
            if (d > dist[u]) continue;
            if (u != a && !is_switch[u]) continue;           // hosts do not forward
            for (auto [v, dl] : adj[u])
                if (d + dl < dist[v]) { dist[v] = d + dl; hops[v] = hops[u] + (is_switch[v] ? 1 : 0); q.push({dist[v], v}); }
        }
        auto r = std::make_pair(dist[b], hops[b]);
        path_cache[key] = r;
        return r;
    }
};

// What the caller learns about one put (absolute ns, the model's own double-precision time)
struct PutCallbacks {
    std::function<void(double)> out;    // the poster's last store / doorbell left it over PCIe (Loom: source reusable)
    std::function<void(double)> seen;   // the receiver sees the data in its memory
    std::function<void(double)> cqe;    // RDMA: the poster sees the completion (never called for Loom)
};

// The model. Every put moves through stages; each stage's time is a formula (latency + bytes / rate) over busy-until
// resources, evaluated when the stage happens, so resources are taken in time order (as Opus's link model and
// ns-3's PcieFabric). Puts are whole and first come, first served on every resource (as Opus). Formulas:
// ANALYTICAL.md section 2.
//   Loom: STORES -> WIRE -> RX
//   RDMA: DOORBELL -> (WQE FETCH) -> PAYLOAD READ -> WIRE -> RX -> ACK + CQE
class Model {
  public:
    Config cfg;
    Topology topo;
    // the caller's scheduler: run fn at absolute time t (ns, >= the current time)
    std::function<void(double, std::function<void()>)> schedule;
    int trace_src = getenv("LOOMNET_TRACE") ? atoi(getenv("LOOMNET_TRACE")) : -1;   // per-put stage times to stderr

    bool init(const std::string& config_path) {
        if (!cfg.read(config_path)) return false;
        if (!topo.read(cfg.topology_file)) return false;
        link_busy.assign(topo.link_id.size(), 0);
        link_bytes.assign(topo.link_id.size(), 0);
        return true;
    }
    bool same_server(int a, int b) const {
        return cfg.gpus_per_server > 0 && a / (int)cfg.gpus_per_server == b / (int)cfg.gpus_per_server;
    }

    // a put of `bytes` from src to dst on queue pair qp, posted at time t (calls in non-decreasing t): the WQE and its
    // doorbell at once (RDMA), or the stores (Loom)
    void put(int src, int dst, int qp, uint64_t bytes, double t, PutCallbacks cb) {
        if (cfg.push) {
            stores(make_put(src, dst, qp, bytes, false, std::move(cb), t), t);
            return;
        }
        const uint64_t n = post_wqe(src, dst, qp, bytes, false, std::move(cb), t);
        ring(src, dst, qp, n, t, true);
    }
    // RDMA with separate doorbells (replays of measured GPU runs): write a WQE (no cost, as the GPU's posting is not
    // modelled) and return how many WQEs the queue pair has; ring() makes the first `upto` WQEs known to the NIC.
    // atomic = an RDMA atomic (8 B operand in the WQE; the responder reads the old value, answers, then writes)
    uint64_t post_wqe(int src, int dst, int qp, uint64_t bytes, bool atomic, PutCallbacks cb, double t) {
        Qp& q = qps[std::make_tuple(src, dst, qp)];
        q.posted.push_back(make_put(src, dst, qp, atomic ? 8 : bytes, atomic, std::move(cb), t));
        return q.posted.size();
    }
    // the poster's doorbell for the queue pair's first `upto` WQEs (BlueFlame: the WQEs with it); `bf_inline` lets a
    // BlueFlame doorbell carry an inline payload (put()); lands DB latency later
    void ring(int src, int dst, int qp, uint64_t upto, double t, bool bf_inline = false) {
        const Config& c = cfg;
        Qp& q = qps[std::make_tuple(src, dst, qp)];
        upto = std::min<uint64_t>(upto, q.posted.size());
        if (upto <= q.rung_n) return;
        std::vector<PutP> v(q.posted.begin() + q.rung_n, q.posted.begin() + upto);
        q.rung_n = upto;
        uint64_t db = 8;
        if (c.bf) {
            db = 0;
            for (auto& p : v) db += c.wqe_bytes + (bf_inline && p->bytes <= c.inline_max ? p->bytes : 0);
        }
        const double e = ctrl(pcie(src), db, t);
        for (auto& p : v) emit(p->cb.out, e);
        at(e + c.db_lat(c.poster), [this, v](double td) {
            for (auto& p : v) doorbell(p, td);
        });
    }

    // LOOMNET_LINKSTATS=1: the busiest links (by final busy-until) with their bytes and utilisation
    void report() const {
        if (!getenv("LOOMNET_LINKSTATS")) return;
        std::vector<std::tuple<double, int, int, double>> v;   // busy, u, v, bytes
        for (const auto& [uv, id] : topo.link_id) v.push_back({link_busy[id], uv.first, uv.second, link_bytes[id]});
        std::sort(v.rbegin(), v.rend());
        for (size_t i = 0; i < std::min<size_t>(12, v.size()); i++) {
            auto [b, u, w, by] = v[i];
            fprintf(stderr, "loomnet_link %d -> %d%s busy_until %.0f ns bytes %.0f (%.1f us at line rate)\n", u, w,
                    topo.is_switch[u] && topo.is_switch[w] ? " (fabric)" : "", b, by, by / topo.link_gbps / 1e3);
        }
    }

  private:
    struct Put {
        int src, dst, qp;
        uint64_t bytes;
        bool atomic = false;
        uint64_t idx = 0;            // its WQE index on the queue pair (the order of the QP's byte stream)
        uint64_t seq = 0;            // global posting order
        PutCallbacks cb;
        double t_post = 0, t_wqe = -1, t_wire0 = -1, t_wire1 = -1, t_out = -1;
        double data_last = 0;        // all its bytes in the sending NIC / Loom
        uint64_t first_pkt(const Config& c) const { return std::min<uint64_t>(bytes, c.mtu); }
    };
    using PutP = std::shared_ptr<Put>;
    struct Pcie {   // one host's PCIe: busy-until per endpoint and direction; host memory never the bottleneck
        double out[3] = {0, 0, 0}, in[3] = {0, 0, 0};
        double gbps = 1;
        double start(int from, int to, double ready) const {
            double s = ready;
            if (from != HOST) s = std::max(s, out[from]);
            if (to != HOST) s = std::max(s, in[to]);
            return s;
        }
        double hold(int from, int to, double bytes, double ready) {
            const double e = start(from, to, ready) + bytes / gbps;
            if (from != HOST) out[from] = e;
            if (to != HOST) in[to] = e;
            return e;
        }
    };
    struct Qp {
        std::vector<PutP> posted;   // RDMA: WQEs written; the first rung_n are rung
        uint64_t rung_n = 0;
        std::deque<PutP> rung;      // WQEs whose doorbell landed, waiting for a fetch (one fetch at a time)
        bool fetching = false;
        uint64_t nput = 0;          // puts made on this QP (WQE indices handed out)
        uint64_t next_wire = 0;     // the put that may enter the wire next (in-order RC byte stream)
        std::map<uint64_t, PutP> parked;   // puts ready before their turn
    };
    using QpKey = std::tuple<int, int, int>;
    struct Reads {                  // the NIC's payload reads: in posting order, PCIE_RD_INFLIGHT x MRRS in flight
        std::map<uint64_t, PutP> queue;   // posting order -> put whose WQE is in
        double outstanding = 0;
    };
    std::map<int, Pcie> hosts;
    std::map<QpKey, Qp> qps;
    std::map<int, Reads> reads;
    uint64_t next_seq = 0;
    std::vector<double> link_busy;   // every directed network link: busy until (ns)
    std::vector<double> link_bytes;  // wire bytes per link (report)
    std::map<QpKey, std::vector<Topology::Hop>> routes;
    std::map<int, double> port_end;  // Loom with a finite transmit buffer: its port's link busy until (stores())

    PutP make_put(int src, int dst, int qp, uint64_t bytes, bool atomic, PutCallbacks cb, double t) {
        auto p = std::make_shared<Put>();
        p->src = src; p->dst = dst; p->qp = qp; p->bytes = bytes; p->atomic = atomic; p->cb = std::move(cb);
        p->t_post = t;
        p->idx = qps[std::make_tuple(src, dst, qp)].nput++;
        p->seq = next_seq++;
        return p;
    }
    // a doorbell (posted write of a few bytes from the poster) may pass read completions on the poster's link (PCIe
    // ordering: posted requests may pass completions), so it does not queue behind payload reads and does not book
    // the link; WQE fetches (read completions) and CQEs (posted writes behind received data) book it in order
    static double ctrl(Pcie& p, double bytes, double t) {
        return t + bytes / p.gbps;
    }
    void at(double t, std::function<void(double)> fn) {
        schedule(t, [fn, t]() { fn(t); });
    }
    void emit(const std::function<void(double)>& f, double t) {
        if (f) at(t, f);
    }
    Pcie& pcie(int node) {
        auto it = cfg.node_host.find(node);
        Pcie& p = hosts[it == cfg.node_host.end() ? node : it->second];
        p.gbps = cfg.pcie_gbps;
        return p;
    }

    // Loom, posted writes: the GPU's stores (payload only: Loom has no work request, WQE_BYTES does not apply) cross
    // its PCIe link; Loom has each piece as it lands and forwards per packet. Sender released when its last store has
    // left the GPU.
    void stores(const PutP& p, double t) {
        const Config& c = cfg;
        Pcie& ps = pcie(p->src);
        const double s0 = ps.start(c.poster, NIC, t);
        const double s1 = ps.hold(c.poster, NIC, p->bytes, t);
        p->data_last = s1 + c.db_lat(c.poster);
        p->t_out = s1;
        if (c.tx_buf <= 0) emit(p->cb.out, s1);
        else {
            // finite transmit buffer: the last store is accepted once at most tx_buf bytes wait ahead of it on Loom's port
            // (the Loom -> switch link carries only this GPU's puts, FIFO, so its end is known now, as send() computes it)
            const double N = topo.link_gbps, L = c.db_lat(c.poster) + c.nic_tx_ns;
            const uint64_t npkt = p->bytes ? (p->bytes + c.mtu - 1) / c.mtu : 1;
            const double wire_b = p->bytes + (double)npkt * c.wire_bytes;
            const double w_last = (p->bytes ? p->bytes - (npkt - 1) * c.mtu : 0) + c.wire_bytes;
            double& port = port_end[p->src];
            const double e0 = std::max(std::max(s0 + p->first_pkt(c) / c.pcie_gbps + L, port) + wire_b / N, s1 + L + w_last / N);
            port = e0;
            emit(p->cb.out, std::max(s1, e0 - c.tx_buf / N));
        }
        at(s0 + p->first_pkt(c) / c.pcie_gbps + c.db_lat(c.poster) + c.nic_tx_ns,
           [this, p](double tw) { wire(p, tw); });
    }

    void doorbell(const PutP& p, double t) {
        if (cfg.bf) { wqe(p, t); return; }
        Qp& q = qps[std::make_tuple(p->src, p->dst, p->qp)];
        q.rung.push_back(p);
        if (!q.fetching) fetch(q, t);
    }
    // WQE fetch: one read of up to WQE_FETCH_MAX WQEs; the data comes one read latency later
    void fetch(Qp& q, double t) {
        const uint32_t n = (uint32_t)std::min<size_t>(q.rung.size(), cfg.wqe_fetch_max);
        if (n == 0) { q.fetching = false; return; }
        q.fetching = true;
        std::vector<PutP> batch(q.rung.begin(), q.rung.begin() + n);
        q.rung.erase(q.rung.begin(), q.rung.begin() + n);
        Qp* qp = &q;
        const int src = batch[0]->src;
        at(t + cfg.rd_lat(cfg.sq_mem), [this, qp, batch, n, src](double tr) {
            // a read completion: behind the completions of reads issued before it
            const double e = pcie(src).hold(cfg.sq_mem, NIC, (double)n * cfg.wqe_bytes, tr);
            at(e, [this, qp, batch](double tw) {
                for (auto& p : batch) wqe(p, tw);
                fetch(*qp, tw);
            });
        });
    }
    // the NIC has the WQE: an inline payload / atomic operand is there; otherwise the payload is read
    void wqe(const PutP& p, double t) {
        p->t_wqe = t;
        if (p->atomic || p->bytes <= cfg.inline_max) {
            p->data_last = t;
            at(t + cfg.nic_tx_ns, [this, p](double tw) { wire(p, tw); });
            return;
        }
        reads[p->src].queue[p->seq] = p;
        read_pump(p->src, t);
    }
    // payload reads in the order the GPU posted the puts (among those whose WQE is in; a WQE fetch brings up to 64 of
    // one queue pair at once, which must not make the NIC read one destination after another), at most PCIE_RD_INFLIGHT x MRRS bytes outstanding; a read's data comes
    // one read latency after its request, then holds the PCIe link at its rate; its credit frees one read latency
    // before its data is in (the NIC requests MRRS pieces as credit frees, so reads stream without gaps)
    void read_pump(int node, double t) {
        const Config& c = cfg;
        Reads& r = reads[node];
        const double cap = (double)c.rd_inflight * c.mrrs;
        while (!r.queue.empty()) {
            PutP p = r.queue.begin()->second;
            if (r.outstanding > 0 && r.outstanding + p->bytes > cap) return;   // a completion pumps again
            r.queue.erase(r.queue.begin());
            r.outstanding += p->bytes;
            at(t + c.rd_lat(c.buf_mem), [this, p, node](double tr) {
                const Config& c = cfg;
                Pcie& ps = pcie(node);
                const double s0 = ps.start(c.buf_mem, NIC, tr);
                const double s1 = ps.hold(c.buf_mem, NIC, p->bytes, tr);
                p->data_last = s1;
                at(s0 + p->first_pkt(c) / c.pcie_gbps + c.nic_tx_ns, [this, p](double tw) { wire(p, tw); });
                at(std::max(s0, s1 - c.rd_lat(c.buf_mem)), [this, p, node](double td) {
                    reads[node].outstanding -= p->bytes;
                    read_pump(node, td);
                });
            });
        }
    }
    // a queue pair's byte stream leaves in WQE order (reliable connection): a put ready before the QP's earlier WQEs
    // are on the wire (e.g. an atomic behind payload still being read) waits for them
    void wire(const PutP& p, double t) {
        Qp& q = qps[std::make_tuple(p->src, p->dst, p->qp)];
        if (p->idx != q.next_wire) { q.parked[p->idx] = p; return; }
        send(p, t);
        q.next_wire++;
        for (auto it = q.parked.find(q.next_wire); it != q.parked.end(); it = q.parked.find(q.next_wire)) {
            PutP x = it->second;
            q.parked.erase(it);
            send(x, t);
            q.next_wire++;
        }
    }
    // the wire: RoCE packets of MTU payload + WIRE_BYTES over the put's ECMP path. Every link is a busy-until resource
    // with the next switch's buffer in front of it (as ASTRA-sim's congestion-aware links): a put passes link by link,
    // cut-through, its first packet one packet time after it was fully in the switch (store-and-forward per packet),
    // its last no earlier than the previous link's last + delay; a busy link delays it, not the links before
    void send(const PutP& p, double t) {
        const Config& c = cfg;
        const double N = topo.link_gbps;
        const uint64_t npkt = p->bytes ? (p->bytes + c.mtu - 1) / c.mtu : 1;
        const double wire_b = p->bytes + (double)npkt * c.wire_bytes + (p->atomic ? c.atomic_wire : 0);
        const double w_first = p->first_pkt(c) + c.wire_bytes;
        const double last_pay = p->bytes ? p->bytes - (npkt - 1) * c.mtu : 0;
        const double w_last = last_pay + c.wire_bytes;
        auto key = std::make_tuple(p->src, p->dst, p->qp);
        auto rit = routes.find(key);
        if (rit == routes.end()) rit = routes.emplace(key, topo.route(p->src, p->dst, p->qp)).first;
        const auto& hops = rit->second;
        const double s0 = std::max(t, link_busy[hops[0].link]);                       // first link: the sender's
        const double e0 = std::max(s0 + wire_b / N, p->data_last + c.nic_tx_ns + w_last / N);
        link_busy[hops[0].link] = e0;
        link_bytes[hops[0].link] += wire_b;
        p->t_wire0 = s0;
        p->t_wire1 = e0;
        hop(p, &hops, 1, s0, e0, hops[0].delay, wire_b, w_first, w_last, last_pay);
    }
    // the put reaches the next switch: it books link j when it gets there (event at its arrival time, as Opus
    // forwards a chunk when it arrives at a device), so every link is booked in time order
    void hop(const PutP& p, const std::vector<Topology::Hop>* hops, size_t j, double s, double e, double prop,
             double wire_b, double w_first, double w_last, double last_pay) {
        const double N = topo.link_gbps;
        const double d = (*hops)[j - 1].delay;
        if (j == hops->size()) {
            const double a0 = s + d + w_first / N;     // first packet in the receiving NIC
            const double a1 = e + d;                   // last packet in the receiving NIC
            const int nsw = (int)hops->size() - 1;
            at(a0 + cfg.nic_rx_ns, [this, p, a1, last_pay, prop, nsw](double tr) { rx(p, tr, a1, last_pay, prop, nsw); });
            return;
        }
        at(s + d + w_first / N, [=](double ready) {
            const int l = (*hops)[j].link;
            const double sj = std::max(ready, link_busy[l]);
            const double ej = std::max(sj + wire_b / N, e + d + w_last / N);
            link_busy[l] = ej;
            link_bytes[l] += wire_b;
            hop(p, hops, j + 1, sj, ej, prop + (*hops)[j].delay, wire_b, w_first, w_last, last_pay);
        });
    }
    // the receiving NIC / Loom writes the data into memory (the last packet's write ends no earlier than its
    // arrival + its bytes at the PCIe rate; posted writes stay in order, so the link is busy until that last write
    // ends and the next put, e.g. the signal behind the data, cannot land first); RDMA: the last packet's ACK returns
    // and the NIC writes a 64 B CQE
    void rx(const PutP& p, double t, double a1, double last_pay, double prop, int nsw) {
        const Config& c = cfg;
        const double B = c.pcie_gbps, N = topo.link_gbps;
        if (p->atomic) {
            // responder: read the 8 B word (one read latency, then its bytes), answer (the ACK carries the old value),
            // then write the new value; the requester's CQE follows the answer
            at(t + c.rd_lat(c.rx_mem), [this, p, prop, nsw](double tr) {
                const Config& c = cfg;
                const double r1 = pcie(p->dst).hold(c.rx_mem, NIC, 8, tr);
                const double w1 = pcie(p->dst).hold(NIC, c.rx_mem, 8, r1);
                emit(p->cb.seen, w1 + c.wr_lat(c.rx_mem) + c.rx_poll_ns);
                const double ack = r1 + prop + (nsw + 1) * (8.0 + c.wire_bytes) / topo.link_gbps;
                at(ack, [this, p](double ta) {
                    const double q1 = pcie(p->src).hold(NIC, cfg.cq_mem, 64, ta);
                    emit(p->cb.cqe, q1 + cfg.wr_lat(cfg.cq_mem) + cfg.cqe_poll_ns);
                });
            });
            return;
        }
        Pcie& pd = pcie(p->dst);
        const double i1 = std::max(pd.hold(NIC, c.rx_mem, p->bytes, t), a1 + c.nic_rx_ns + last_pay / B);
        pd.out[NIC] = std::max(pd.out[NIC], i1);
        if (c.rx_mem != HOST) pd.in[c.rx_mem] = std::max(pd.in[c.rx_mem], i1);
        const double seen = i1 + c.wr_lat(c.rx_mem) + c.rx_poll_ns;
        emit(p->cb.seen, seen);
        if (trace_src == p->src)
            fprintf(stderr, "loomnet_put src %d dst %d bytes %lu post %.0f wqe %.0f data1 %.0f wire0 %.0f wire1 %.0f "
                    "a1 %.0f seen %.0f\n", p->src, p->dst, (unsigned long)p->bytes, p->t_post, p->t_wqe, p->data_last,
                    p->t_wire0, p->t_wire1, a1, seen);
        if (c.push) return;
        const double ack = a1 + c.nic_rx_ns + prop + (nsw + 1) * c.wire_bytes / N;
        at(ack, [this, p](double ta) {
            // a posted write: behind the NIC's earlier posted writes (received data) into memory
            const double q1 = pcie(p->src).hold(NIC, cfg.cq_mem, 64, ta);
            emit(p->cb.cqe, q1 + cfg.wr_lat(cfg.cq_mem) + cfg.cqe_poll_ns);
        });
    }
};

}  // namespace LoomNet
