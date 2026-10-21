// ASTRA-sim network API on the LoomNet analytical model (see LoomNet.hh, e8-astrasim/ANALYTICAL.md).
#pragma once
#include "common/CommonNetworkApi.hh"
#include "loom/LoomNet.hh"
#include <memory>
#include <vector>

namespace AstraSimAnalyticalLoom {

class LoomNetworkApi : public AstraSimAnalytical::CommonNetworkApi {
  public:
    static void set_model(std::shared_ptr<LoomNet::Model> m) noexcept;
    explicit LoomNetworkApi(int rank) noexcept;
    int sim_send(void* buffer, uint64_t count, int type, int dst, int tag, AstraSim::sim_request* request,
                 void (*msg_handler)(void* fun_arg), void* fun_arg) override;
    void sim_notify_finished() override;
    double get_BW_at_dimension(int dim) override;
    static int finished() noexcept;   // ranks whose workload finished

  private:
    static std::shared_ptr<LoomNet::Model> model;
};

}  // namespace AstraSimAnalyticalLoom
