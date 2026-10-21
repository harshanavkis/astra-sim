/******************************************************************************
This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
*******************************************************************************/

// TODO: HardwareResource.cc should be moved to the system layer.

#include "astra-sim/workload/HardwareResource.hh"

using namespace std;
using namespace AstraSim;
using namespace Chakra;

// loom branch: ASTRA_CONCURRENT_SENDS=1 lets point-to-point sends run side by side, like receives
// (a GPU-initiated send is a post; the GPU's warps post many at once). Default: upstream.
static bool concurrent_sends() {
    static const bool on = getenv("ASTRA_CONCURRENT_SENDS") && atoi(getenv("ASTRA_CONCURRENT_SENDS"));
    return on;
}

// loom branch: ASTRA_COMM_PER_GROUP=1 keeps one communication op in flight per communicator group (NCCL: one stream
// per communicator; frameworks run TP, DP and PP traffic on separate streams) instead of one per GPU (upstream). With
// one per GPU, collectives of crossing groups (TP inside a server, DP across) that peers issue in different orders
// wait for each other in a cycle (deadlock 2026-10-20, Phase A hybrid on ns-3 and DP on the analytical fabric model).
// A GPU's point-to-point sends share one key ("send"); ASTRA_CONCURRENT_SENDS=1 frees them as before.
static bool comm_per_group() {
    static const bool on = getenv("ASTRA_COMM_PER_GROUP") && atoi(getenv("ASTRA_COMM_PER_GROUP"));
    return on;
}
static std::string comm_key(const shared_ptr<Chakra::FeederV3::ETFeederNode>& node) {
    if (node->type() == ChakraProtoMsg::NodeType::COMM_SEND_NODE)
        return "send";
    return "pg:" + node->pg_name<std::string>("");
}

typedef ChakraProtoMsg::NodeType ChakraNodeType;

HardwareResource::HardwareResource(uint32_t num_npus, int sys_id)
    : num_npus(num_npus),
      num_in_flight_cpu_ops(0),
      num_in_flight_gpu_comm_ops(0),
      num_in_flight_gpu_comp_ops(0),
      sys_id(sys_id) {

    num_cpu_ops = 0;
    num_gpu_ops = 0;
    num_gpu_comms = 0;

    tics_cpu_ops = 0;
    tics_gpu_ops = 0;
    tics_gpu_comms = 0;

    // cpu_ops_node = NULL;
    // gpu_ops_node = NULL;
    // gpu_comms_node = NULL;
}

void HardwareResource::occupy(
    const shared_ptr<Chakra::FeederV3::ETFeederNode> node) {
    if (node->is_cpu_op()) {
        assert(num_in_flight_cpu_ops == 0);
        ++num_in_flight_cpu_ops;
        ++num_cpu_ops;
        cpu_ops_node.emplace(node->id());
    } else {
        if (node->type() == ChakraNodeType::COMP_NODE) {
            assert(num_in_flight_gpu_comp_ops == 0);
            ++num_in_flight_gpu_comp_ops;
            ++num_gpu_ops;
            // gpu_ops_node = node;
            gpu_ops_node.emplace(node->id());
        } else {
            if (node->type() == ChakraNodeType::COMM_RECV_NODE ||
                (concurrent_sends() && node->type() == ChakraNodeType::COMM_SEND_NODE)) {
                return;
            }
            if (comm_per_group()) {
                auto& n = comm_in_flight[comm_key(node)];
                assert(n == 0);
                ++n;
                ++num_gpu_comms;
                gpu_comms_node.emplace(node->id());
                return;
            }
            assert(num_in_flight_gpu_comm_ops == 0);
            ++num_in_flight_gpu_comm_ops;
            ++num_gpu_comms;
            // gpu_comms_node = node;
            gpu_comms_node.emplace(node->id());
        }
    }
}

void HardwareResource::release(
    const shared_ptr<Chakra::FeederV3::ETFeederNode> node) {
    if (node->is_cpu_op()) {
        --num_in_flight_cpu_ops;
        assert(num_in_flight_cpu_ops == 0);
        this->cpu_ops_node.erase(node->id());
    } else {
        if (node->type() == ChakraNodeType::COMP_NODE) {
            --num_in_flight_gpu_comp_ops;
            assert(num_in_flight_gpu_comp_ops == 0);
            this->gpu_ops_node.erase(node->id());
        } else {
            if (node->type() == ChakraNodeType::COMM_RECV_NODE ||
                (concurrent_sends() && node->type() == ChakraNodeType::COMM_SEND_NODE)) {
                return;
            }
            if (comm_per_group()) {
                auto& n = comm_in_flight[comm_key(node)];
                --n;
                assert(n == 0);
                this->gpu_comms_node.erase(node->id());
                return;
            }
            --num_in_flight_gpu_comm_ops;
            assert(num_in_flight_gpu_comm_ops == 0);
            this->gpu_comms_node.erase(node->id());
        }
    }
}

bool HardwareResource::is_available(
    const shared_ptr<Chakra::FeederV3::ETFeederNode> node) const {
    if (node->is_cpu_op()) {
        if (num_in_flight_cpu_ops == 0) {
            return true;
        } else {
            return false;
        }
    } else {
        if (node->type() == ChakraNodeType::COMP_NODE) {
            if (num_in_flight_gpu_comp_ops == 0) {
                return true;
            } else {
                return false;
            }
        } else {
            if (comm_per_group() && node->type() != ChakraNodeType::COMM_RECV_NODE &&
                !(concurrent_sends() && node->type() == ChakraNodeType::COMM_SEND_NODE)) {
                auto it = comm_in_flight.find(comm_key(node));
                return it == comm_in_flight.end() || it->second == 0;
            }
            if (num_in_flight_gpu_comm_ops == 0) {
                return true;
            } else {
                if (node->type() == ChakraNodeType::COMM_RECV_NODE ||
                    (concurrent_sends() && node->type() == ChakraNodeType::COMM_SEND_NODE)) {
                    return true;
                }
                if (num_in_flight_gpu_comm_ops == 0) {
                    return true;
                }
                return false;
            }
        }
    }
}

void HardwareResource::report() {
    cout << "num_cpu_ops: " << num_cpu_ops << endl;
    cout << "num_gpu_ops: " << num_gpu_ops << endl;
    cout << "num_gpu_comms: " << num_gpu_comms << endl;

    cout << "tics_cpu_ops: " << tics_cpu_ops << endl;
    cout << "tics_gpu_ops: " << tics_gpu_ops << endl;
    cout << "tics_gpu_comms: " << tics_gpu_comms << endl;
}
