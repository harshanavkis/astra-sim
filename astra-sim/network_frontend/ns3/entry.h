#undef PGO_TRAINING
#define PATH_TO_PGO_CONFIG "path_to_pgo_config"

#include "common.h"
#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/error-model.h"
#include "ns3/global-route-manager.h"
#include "ns3/internet-module.h"
#include "ns3/ipv4-static-routing-helper.h"
#include "ns3/packet.h"
#include "ns3/point-to-point-helper.h"
#include "ns3/qbb-helper.h"
#include <fstream>
#include <iostream>
#include <queue>
#include <ns3/rdma-client-helper.h>
#include <ns3/rdma-client.h>
#include <ns3/rdma-driver.h>
#include <ns3/rdma.h>
#include <ns3/sim-setting.h>
#include <ns3/switch-node.h>
#include <time.h>
#include <unordered_map>

using namespace ns3;
using namespace std;

/*
 * This file defines the interaction between the System layer and the NS3
 * simulator (Network layer). The system layer issues send/receive events, and
 * waits until the ns3 simulates the conclusion of these events to issue the
 * next collective communication. When ns3 simulates the conclusion of an event,
 * it will call qp_finish to lookup the maps in this file and call the callback
 * handlers. Refer to below comments for further detail.
 */

// MsgEvent represents a single send or receive event, issued by the system
// layer. The system layer will wait for the ns3 backend to simulate the event
// finishing (i.e. node 0 finishes sending message, or node 1 finishes receiving
// the message) The callback handler 'msg_handler' signals the System layer that
// the event has finished in ns3.
class MsgEvent {
public:
  int src_id;
  int dst_id;
  int type;
  // Indicates the number of bytes remaining to be sent or received.
  // Initialized with the original size of the message, and
  // incremented/decremented depending on how many bytes were sent/received.
  // Eventually, this value will reach 0 when the event has completed.
  int remaining_msg_bytes;
  void *fun_arg;
  void (*msg_handler)(void *fun_arg);

  MsgEvent(int _src_id, int _dst_id, int _type, int _remaining_msg_bytes,
           void *_fun_arg, void (*_msg_handler)(void *fun_arg))
      : src_id(_src_id), dst_id(_dst_id), type(_type),
        remaining_msg_bytes(_remaining_msg_bytes), fun_arg(_fun_arg),
        msg_handler(_msg_handler) {}

  // Default constructor to prevent compile errors. When looking up MsgEvents
  // from maps such as sim_send_waiting_hash, we should always check that a MsgEvent exists
  // for the given key. (i.e. this default constructor should not be called in
  // runtime.)
  MsgEvent()
      : src_id(0), dst_id(0), type(0), remaining_msg_bytes(0), fun_arg(nullptr),
        msg_handler(nullptr) {}

  // CallHandler will call the callback handler associated with this MsgEvent.
  void callHandler() {
    msg_handler(fun_arg);
    return;
  }
};

// MsgEventKey is a key to uniquely identify each MsgEvent.
//  - Pair <Tag, Pair <src_id, dst_id>>
typedef pair<int, pair<int, int>> MsgEventKey;

// The ns3 RdmaClient structure cannot hold the 'tag' information, which is a
// Astra-sim specific implementation. We use a mapping with the source port
// number (another unique value) to hold tag information.
//   - key: Pair <port_id, Pair <src_id, dst_id>>
//   - value: tag
// TODO: It seems we *can* obtain the tag through q->GetTag() at qp_finish.
// Verify & Simplify.
map<pair<int, pair<int, int>>, int> sender_src_port_map;

// NodeHash is used to count how many bytes were sent/received by this node.
// Refer to sim_finish().
//   - key: Pair <node_id, send/receive>. Where 'send/receive' indicates if the
//   value is for send or receive
//   - value: Number of bytes this node has sent (if send/receive is 0) and
//   received (if send/receive is 1)
map<pair<int, int>, int> node_to_bytes_sent_map;

// SentHash stores a MsgEvent for sim_send events and its callback handler.
//   - key: A pair of <MsgEventKey, port_id>. 
//          A single collective phase can be split into multiple sim_send messages, which all have the same MsgEventKey. 
//          TODO: Adding port_id as key is a hacky solution. The real solution would be to split this map, similar to sim_recv_waiting_hash and received_msg_standby_hash.
//   - value: A MsgEvent instance that indicates that Sys layer is waiting for a
//   send event to finish
map<pair<MsgEventKey, int>, MsgEvent> sim_send_waiting_hash;

// While ns3 cannot send packets before System layer calls sim_send, it
// is possible for ns3 to simulate Incoming messages before System layer calls
// sim_recv to 'reap' the messages. Therefore, we maintain two maps:
//   - sim_recv_waiting_hash holds messages where sim_recv has been called but
//   ns3 has not yet simulated the message arriving,
//   - received_msg_standby_hash holds messages which ns3 has simulated the
//   arrival, but sim_recv has not yet been called.

//   - key: A MsgEventKey instance.
//   - value: A queue of MsgEvent instances that the Sys layer is waiting for.
//   Multiple receive events may share the same key, so each callback must be
//   retained until its corresponding bytes arrive.
map<MsgEventKey, queue<MsgEvent>> sim_recv_waiting_hash;

//   - key: A MsgEventKey isntance.
//   - value: The number of bytes that ns3 has simulated completed, but the
//   System layer has not yet called sim_recv
map<MsgEventKey, int> received_msg_standby_hash;

// loom branch: with a host interface, sender release, receiver delivery and the
// end of the qp (last ACK) happen at different times; forget a flow after all three
struct FlowState {
  bool snd = false, rcv = false, qp = false;
};
map<pair<int, pair<int, int>>, FlowState> flow_state;
void flow_maybe_done(pair<int, pair<int, int>> key) {
  auto it = flow_state.find(key);
  if (it != flow_state.end() && it->second.snd && it->second.rcv && it->second.qp) {
    flow_state.erase(it);
    sender_src_port_map.erase(key);
  }
}

// send_flow commands the ns3 simulator to schedule a RDMA message to be sent
// between two pair of nodes. send_flow is triggered by sim_send.
void send_flow(int src_id, int dst, int maxPacketCount,
               void (*msg_handler)(void *fun_arg), void *fun_arg, int tag) {
  // Get a new port number.
  uint32_t port = portNumber[src_id][dst]++;
  sender_src_port_map[make_pair(port, make_pair(src_id, dst))] = tag;
  flow_state[make_pair(port, make_pair(src_id, dst))] = FlowState();
  int pg = 3, dport = 100;
  flow_input.idx++;

  // Create a MsgEvent instance and register callback function.
  MsgEvent send_event =
      MsgEvent(src_id, dst, 0, maxPacketCount, fun_arg, msg_handler);
  pair<MsgEventKey, int> send_event_key =
      make_pair(make_pair(tag, make_pair(send_event.src_id, send_event.dst_id)),port) ;
  sim_send_waiting_hash[send_event_key] = send_event;

  // Create a queue pair and schedule within the ns3 simulator.
  RdmaClientHelper clientHelper(
      pg, serverAddress[src_id], serverAddress[dst], port, dport,
      maxPacketCount,
      has_win ? (global_t == 1 ? maxBdp : pairBdp[n.Get(src_id)][n.Get(dst)])
              : 0,
      global_t == 1 ? maxRtt : pairRtt[src_id][dst], msg_handler, fun_arg, tag,
      src_id, dst);
  ApplicationContainer appCon = clientHelper.Install(n.Get(src_id));
  appCon.Start(Time(0));
}

// notify_receiver_receive_data looks at whether the System layer has issued
// sim_recv for this message. If the system layer is waiting for this message,
// call the callback handler for the MsgEvent. If the system layer is not *yet*
// waiting for this message, register that this message has arrived,
// so that the system layer can later call the callback handler when sim_recv
// is called.
void notify_receiver_receive_data(int src_id,
                                  int dst_id,
                                  int message_size,
                                  int tag) {

    MsgEventKey recv_expect_event_key =
        make_pair(tag, make_pair(src_id, dst_id));

    int remaining_bytes = message_size;
    auto waiting_it = sim_recv_waiting_hash.find(recv_expect_event_key);
    if (waiting_it != sim_recv_waiting_hash.end()) {
        // Consume the received bytes against pending receive events in FIFO
        // order.
        queue<MsgEvent>& waiting_events = waiting_it->second;
        while (!waiting_events.empty()) {
            MsgEvent& recv_expect_event = waiting_events.front();
            if (remaining_bytes < recv_expect_event.remaining_msg_bytes) {
                recv_expect_event.remaining_msg_bytes -= remaining_bytes;
                remaining_bytes = 0;
                break;
            } else {
                remaining_bytes -= recv_expect_event.remaining_msg_bytes;
                MsgEvent completed_event = recv_expect_event;
                waiting_events.pop();
                completed_event.callHandler();
            }
        }

        if (waiting_events.empty()) {
            sim_recv_waiting_hash.erase(waiting_it);
        }
    }

    if (remaining_bytes > 0) {
        // The Sys object is not yet waiting for all of the received bytes.
        received_msg_standby_hash[recv_expect_event_key] += remaining_bytes;
    }

    // Add to the number of total bytes received.
    if (node_to_bytes_sent_map.find(make_pair(dst_id, 1)) ==
        node_to_bytes_sent_map.end()) {
        node_to_bytes_sent_map[make_pair(dst_id, 1)] = message_size;
    } else {
        node_to_bytes_sent_map[make_pair(dst_id, 1)] += message_size;
    }
}

void notify_sender_sending_finished(int src_id, int dst_id, int message_size,
                                    int tag, int src_port) {
  // Lookup the send_event registered at send_flow().
  pair<MsgEventKey, int> send_event_key = make_pair(make_pair(tag, make_pair(src_id, dst_id)), src_port);
  if (sim_send_waiting_hash.find(send_event_key) == sim_send_waiting_hash.end()) {
    cerr << "Cannot find send_event in sent_hash. Something is wrong."
         << "tag, src_id, dst_id: " << tag << " " << src_id << " " << dst_id
         << "\n";
    exit(1);
  }

  // Verify that the (ns3 identified) sent message size matches what was
  // expected by the system layer.
  MsgEvent send_event = sim_send_waiting_hash[send_event_key];
  if (send_event.remaining_msg_bytes != message_size) {
    cerr << "The message size does not match what is expected. Something is "
            "wrong."
         << "tag, src_id, dst_id, expected msg_bytes, actual msg_bytes: " << tag
         << " " << src_id << " " << dst_id << " "
         << send_event.remaining_msg_bytes << " " << message_size << "\n";
    exit(1);
  }
  sim_send_waiting_hash.erase(send_event_key);

  // Add to the number of total bytes sent.
  if (node_to_bytes_sent_map.find(make_pair(src_id, 0)) == node_to_bytes_sent_map.end()) {
    node_to_bytes_sent_map[make_pair(src_id, 0)] = message_size;
  } else {
    node_to_bytes_sent_map[make_pair(src_id, 0)] += message_size;
  }
  send_event.callHandler();
}

void qp_finish_print_log(FILE *fout, Ptr<RdmaQueuePair> q) {
  uint32_t sid = ip_to_node_id(q->sip), did = ip_to_node_id(q->dip);
  uint64_t base_rtt = pairRtt[sid][did], b = pairBw[sid][did];
  uint32_t total_bytes =
      q->m_size +
      ((q->m_size - 1) / packet_payload_size + 1) *
          (CustomHeader::GetStaticWholeHeaderSize() -
           IntHeader::GetStaticSize()); // translate to the minimum bytes
                                        // required (with header but no INT)
  uint64_t standalone_fct = base_rtt + total_bytes * 8000000000lu / b;
  // sip, dip, sport, dport, size (B), start_time, fct (ns), standalone_fct (ns)
  fprintf(fout, "%08x %08x %u %u %lu %lu %lu %lu\n", q->sip.Get(), q->dip.Get(),
          q->sport, q->dport, q->m_size, q->startTime.GetTimeStep(),
          (Simulator::Now() - q->startTime).GetTimeStep(), standalone_fct);
  fflush(fout);
}

// qp_finish is triggered by NS3 to indicate that an RDMA queue pair has
// finished. qp_finish is registered as the callback handlerto the RdmaClient
// instance created at send_flow. This registration is done at
// common.h::SetupNetwork().
void qp_finish(FILE *fout, Ptr<RdmaQueuePair> q) {
  uint32_t sid = ip_to_node_id(q->sip), did = ip_to_node_id(q->dip);
  qp_finish_print_log(fout, q);

  // remove rxQp from the receiver.
  Ptr<Node> dstNode = n.Get(did);
  Ptr<RdmaDriver> rdma = dstNode->GetObject<RdmaDriver>();
  rdma->m_rdma->DeleteRxQp(q->sip.Get(), q->m_pg, q->sport);

  // Identify the tag of this message.
  if (sender_src_port_map.find(make_pair(q->sport, make_pair(sid, did))) ==
      sender_src_port_map.end()) {
    cout << "could not find the tag, there must be something wrong" << endl;
    exit(-1);
  }
  int tag = sender_src_port_map[make_pair(q->sport, make_pair(sid, did))];
  if (g_hostIf.mode != HostIfConfig::NONE) {
    // host interface (loom branch): RdmaHw releases sender and receiver itself
    flow_state[make_pair(q->sport, make_pair(sid, did))].qp = true;
    flow_maybe_done(make_pair(q->sport, make_pair(sid, did)));
    return;
  }
  sender_src_port_map.erase(make_pair(q->sport, make_pair(sid, did)));
  flow_state.erase(make_pair(q->sport, make_pair(sid, did)));

  // Let sender knows that the flow has finished.
  notify_sender_sending_finished(sid, did, q->m_size, tag, q->sport);

  // Let receiver knows that it has received packets.
  notify_receiver_receive_data(sid, did, q->m_size, tag);
}

// loom branch: the sender is released (pull: CQE seen, push: writes left the GPU)
void hif_sender_done(Ptr<RdmaQueuePair> q) {
  int sid = ip_to_node_id(q->sip), did = ip_to_node_id(q->dip);
  auto key = make_pair((int)q->sport, make_pair(sid, did));
  flow_state[key].snd = true;
  notify_sender_sending_finished(sid, did, q->m_size, sender_src_port_map[key], q->sport);
  flow_maybe_done(key);
}

// loom branch: the whole message is in the receiver's memory
void hif_rx_done(uint32_t sip, uint32_t dip, uint16_t sport, uint64_t size) {
  int sid = ip_to_node_id(Ipv4Address(sip)), did = ip_to_node_id(Ipv4Address(dip));
  auto key = make_pair((int)sport, make_pair(sid, did));
  flow_state[key].rcv = true;
  notify_receiver_receive_data(sid, did, size, sender_src_port_map[key]);
  flow_maybe_done(key);
}

// loom branch: a message between two GPUs of one server takes NVLink, not
// ns-3: it holds the sender's and the receiver's NVLink port for size / bw
// (the NVSwitch itself does not block); the receiver has it nvlink_lat_ns later.
vector<uint64_t> nvl_tx_free, nvl_rx_free;
void local_send(int src, int dst, uint64_t size, void (*msg_handler)(void *fun_arg),
                void *fun_arg, int tag) {
  if (nvl_tx_free.size() <= (size_t)max(src, dst)) {
    nvl_tx_free.resize(max(src, dst) + 1, 0);
    nvl_rx_free.resize(max(src, dst) + 1, 0);
  }
  uint64_t now = Simulator::Now().GetNanoSeconds();
  uint64_t start = max(now, max(nvl_tx_free[src], nvl_rx_free[dst]));
  uint64_t end = start + (uint64_t)ceil(size / nvlink_gbps); // GB/s = B/ns
  nvl_tx_free[src] = nvl_rx_free[dst] = end;
  Simulator::Schedule(NanoSeconds(end - now), msg_handler, fun_arg);
  Simulator::Schedule(NanoSeconds(end + (uint64_t)nvlink_lat_ns - now),
                      &notify_receiver_receive_data, src, dst, (int)size, tag);
}

// loom branch: a message split into puts (MSG_SPLIT_BYTES); the sender is done
// when all its puts are, the receiver counts bytes per tag as before
struct SplitSend {
  int left;
  void (*msg_handler)(void *fun_arg);
  void *fun_arg;
};
void split_put_done(void *arg) {
  SplitSend *s = (SplitSend *)arg;
  if (--s->left == 0) {
    s->msg_handler(s->fun_arg);
    delete s;
  }
}
void split_send(int src, int dst, uint64_t size, void (*msg_handler)(void *fun_arg),
                void *fun_arg, int tag) {
  if (msg_split_bytes == 0 || size <= msg_split_bytes) {
    send_flow(src, dst, size, msg_handler, fun_arg, tag);
    return;
  }
  uint64_t n = (size + msg_split_bytes - 1) / msg_split_bytes;
  SplitSend *s = new SplitSend{(int)n, msg_handler, fun_arg};
  for (uint64_t i = 0; i < n; i++)
    send_flow(src, dst, min(msg_split_bytes, size - i * msg_split_bytes), split_put_done, s, tag);
}

// loom branch, HOST_IF_MODE nic (rdma-hw.cc nic mode): a cross-server message on one QP per
// (src, dst): puts of MSG_SPLIT_BYTES (0 = one put), each rung as it is posted (the GPU posts at no
// cost), then an 8 B signal write behind them on the same QP. The receiver has the message when it
// sees the signal. The sender may reuse its buffer: RDMA (NIC_PUSH 0) when it sees the signal's CQE
// (SENDER_RELEASE cqe, the default) or at once (SENDER_RELEASE post); Loom (NIC_PUSH 1) when its
// stores, the signal behind the data, have left the GPU.
struct NicMsg {
  int src, dst, tag;
  uint64_t size;
  void (*handler)(void *fun_arg);
  void *fun_arg;
  bool released, received;
};
unordered_map<uint64_t, NicMsg> nic_msgs; // signal id -> message, until released and received
uint64_t nic_next_id = 1;
void nic_forget(unordered_map<uint64_t, NicMsg>::iterator it) {
  if (it->second.released && it->second.received)
    nic_msgs.erase(it);
}
void nic_sender_done(uint64_t id) {
  auto it = nic_msgs.find(id);
  if (it == nic_msgs.end() || it->second.released)
    return;
  NicMsg &m = it->second;
  m.released = true;
  node_to_bytes_sent_map[make_pair(m.src, 0)] += m.size;
  auto h = m.handler;
  auto a = m.fun_arg;
  nic_forget(it);
  h(a);
}
void nic_receiver_done(uint64_t id) {
  auto it = nic_msgs.find(id);
  if (it == nic_msgs.end() || it->second.received)
    return;
  it->second.received = true;
  NicMsg m = it->second;
  nic_forget(it);
  notify_receiver_receive_data(m.src, m.dst, (int)m.size, m.tag);
}
void nic_cqe(Ptr<RdmaQueuePair> qp, uint64_t wqe, uint64_t id) {
  if (!g_hostIf.push && !g_hostIf.release_on_post)
    nic_sender_done(id);
}
void nic_rx(uint32_t src, uint32_t dst, uint16_t sport, uint64_t id, bool atomic) {
  nic_receiver_done(id);
}
void nic_send(int src, int dst, uint64_t size, void (*msg_handler)(void *fun_arg), void *fun_arg, int tag) {
  Ptr<RdmaHw> hw = n.Get(src)->GetObject<RdmaDriver>()->m_rdma;
  Ptr<RdmaQueuePair> qp = hw->NicQp(dst, serverAddress[src], serverAddress[dst], 0);
  uint64_t put = msg_split_bytes ? msg_split_bytes : size;
  for (uint64_t off = 0; off < size; off += put) {
    hw->NicPost(qp, min(put, size - off), false, 0); // data puts: id 0, nobody waits on them alone
    hw->NicRing(qp);
  }
  uint64_t id = nic_next_id++;
  nic_msgs[id] = NicMsg{src, dst, tag, size, msg_handler, fun_arg, false, false};
  hw->NicPost(qp, 8, false, id); // the signal, behind the data
  hw->NicRing(qp);
  if (g_hostIf.push) // Loom: released once the signal store (behind every data store) is out of the GPU
    Simulator::Schedule(qp->nic_out - Simulator::Now(), &nic_sender_done, id);
  else if (g_hostIf.release_on_post)
    Simulator::ScheduleNow(&nic_sender_done, id);
}
bool same_server(int a, int b) {
  return gpus_per_server > 0 && a / (int)gpus_per_server == b / (int)gpus_per_server;
}

int setup_ns3_simulation(string network_configuration) {
  if (!ReadConf(network_configuration))
    return -1;

  SetConfig();

  if (!SetupNetwork(qp_finish)) {
    return -1;
  }
  RdmaHw::s_hifSenderDone = hif_sender_done;
  RdmaHw::s_hifRxDone = hif_rx_done;
  RdmaHw::s_nicCqe = nic_cqe;
  RdmaHw::s_nicRx = nic_rx;

  return 0;

}
