// AstraSim_Analytical_Loom: ASTRA-sim on the LoomNet analytical host-interface + network model.
//   --network-configuration = a cluster's rdma.txt or loom.txt (the ns-3 config format; its TOPOLOGY_FILE gives the
//   network). One logical dimension with every host of the topology (as the clusters' logical.json).
// See /scratch/harshanavkis/loom-proj/e8-astrasim/ANALYTICAL.md.
#include "astra-sim/common/Logging.hh"
#include "common/CmdLineParser.hh"
#include "loom/LoomNetworkApi.hh"
#include <astra-network-analytical/common/EventQueue.h>
#include <remote_memory_backend/analytical/AnalyticalRemoteMemory.hh>

using namespace AstraSim;
using namespace Analytical;
using namespace AstraSimAnalytical;
using namespace AstraSimAnalyticalLoom;
using namespace NetworkAnalytical;

int main(int argc, char* argv[]) {
    auto cmd_line_parser = CmdLineParser(argv[0]);
    cmd_line_parser.parse(argc, argv);
    const auto workload_configuration = cmd_line_parser.get<std::string>("workload-configuration");
    const auto comm_group_configuration = cmd_line_parser.get<std::string>("comm-group-configuration");
    const auto system_configuration = cmd_line_parser.get<std::string>("system-configuration");
    const auto remote_memory_configuration = cmd_line_parser.get<std::string>("remote-memory-configuration");
    const auto network_configuration = cmd_line_parser.get<std::string>("network-configuration");
    const auto logging_configuration = cmd_line_parser.get<std::string>("logging-configuration");
    const auto logging_folder = cmd_line_parser.get<std::string>("logging-folder");
    const auto num_queues_per_dim = cmd_line_parser.get<int>("num-queues-per-dim");
    const auto comm_scale = cmd_line_parser.get<double>("comm-scale");
    const auto injection_scale = cmd_line_parser.get<double>("injection-scale");
    const auto rendezvous_protocol = cmd_line_parser.get<bool>("rendezvous-protocol");

    AstraSim::LoggerFactory::init(logging_configuration, logging_folder);

    auto model = std::make_shared<LoomNet::Model>();
    if (!model->init(network_configuration)) return 1;
    int npus = 0;
    for (int i = 0; i < model->topo.nodes; i++)
        if (!model->topo.is_switch[i]) npus++;
    printf("loomnet: %s: %d GPUs, %s, link %.2f GB/s, PCIe %.2f GB/s, GPUs per server %u, puts %lu B\n",
           network_configuration.c_str(), npus, model->cfg.push ? "Loom (posted writes)" : "RDMA NIC",
           model->topo.link_gbps, model->cfg.pcie_gbps, model->cfg.gpus_per_server,
           (unsigned long)model->cfg.msg_split);

    const auto event_queue = std::make_shared<EventQueue>();
    LoomNetworkApi::set_event_queue(event_queue);
    LoomNetworkApi::set_model(model);

    auto network_apis = std::vector<std::unique_ptr<LoomNetworkApi>>();
    const auto memory_api = std::make_unique<AnalyticalRemoteMemory>(remote_memory_configuration);
    auto systems = std::vector<Sys*>();
    const auto npus_count_per_dim = std::vector<int>{npus};
    const auto queues_per_dim = std::vector<int>{num_queues_per_dim};
    for (int i = 0; i < npus; i++) {
        auto network_api = std::make_unique<LoomNetworkApi>(i);
        auto* const system = new Sys(i, workload_configuration, comm_group_configuration, system_configuration,
                                     memory_api.get(), network_api.get(), npus_count_per_dim, queues_per_dim,
                                     injection_scale, comm_scale, rendezvous_protocol);
        network_apis.push_back(std::move(network_api));
        systems.push_back(system);
    }
    for (int i = 0; i < npus; i++) systems[i]->workload->fire();
    while (!event_queue->finished()) event_queue->proceed();
    model->report();
    // Sys objects are not deleted: ASTRA-sim's ~CommunicatorGroup double-frees a CollectivePlan (valgrind,
    // 2026-10-20), which aborted runs at exit after the simulation had finished.
    printf("loomnet: simulation finished at %lu ns\n", (unsigned long)event_queue->get_current_time());
    const int done = LoomNetworkApi::finished();
    if (done != npus) {
        // the event queue ran dry with ranks still waiting: a trace whose collectives are not in program order
        // (ANALYTICAL.md section 4: tools/order_traces.sh)
        printf("LOOMNET DEADLOCK: %d of %d ranks finished\n", done, npus);
        fflush(stdout);
        return 3;
    }
    fflush(stdout);
    AstraSim::LoggerFactory::shutdown();
    return 0;
}
