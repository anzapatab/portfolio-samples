// Extract from HFT Quant Engine
// Online feature engine interface: streaming computation of EMA, MACD, RSI,
// Order Flow Imbalance (OFI), microprice from tick-level L1 and trade data.

#pragma once
#include "ring_buffer.hpp"
#include "types.hpp"

namespace bqe {

struct RollingState {
    double alpha_s{2.0 / (12.0 + 1.0)};
    double alpha_l{2.0 / (26.0 + 1.0)};
    double alpha_rsi{2.0 / (14.0 + 1.0)};
    size_t vol_n{0};
    double vol_mean{0.0}, vol_m2{0.0};
    double ema_s{0.0}, ema_l{0.0}, ema_macd{0.0}, ema_signal{0.0};
    double rsi_avg_gain{0.0}, rsi_avg_loss{0.0};
    double last_close{0.0};
    double rsi_prev_price{0.0};  // Previous price for RSI calculation (per-instance state)
    double prev_bid{0.0}, prev_ask{0.0}, prev_bid_qty{0.0}, prev_ask_qty{0.0};
    double ofi{0.0};
};

class FeatureEngine {
public:
    FeatureEngine(SpscRing<BookL1>& in_l1, SpscRing<TradeFrame>& in_trades, SpscRing<FeaturesOnline>& out_feat,
                  RollingState init = {})
        : in_l1_(in_l1), in_trades_(in_trades), out_(out_feat), st_(init) {}

    void run_once();

    const RollingState& get_state() const {
        return st_;
    }

private:
    void update_from_trade(const TradeFrame& t);
    void update_from_l1(const BookL1& b);
    bool emit_feature(Ts ts);

    SpscRing<BookL1>& in_l1_;
    SpscRing<TradeFrame>& in_trades_;
    SpscRing<FeaturesOnline>& out_;
    RollingState st_;
    BookL1 last_l1_{};
    bool have_l1_{false};
};

}  // namespace bqe
