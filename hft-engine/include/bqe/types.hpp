// Extract from HFT Quant Engine
// Core data types for the trading pipeline: nanosecond timestamps,
// trade frames, L1 book snapshots, and online feature vectors.

#pragma once
#include <cstdint>
#include <limits>

namespace bqe {

using i64 = std::int64_t;
using u64 = std::uint64_t;
using f64 = double;

struct Ts {
    u64 ns{0};  // UTC epoch nanoseconds
};

struct TradeFrame {
    Ts ts{};
    f64 px{0.0};
    f64 qty{0.0};
    bool is_buy{true};
    u64 id{0};
    bool agg{true};
};

struct BookL1 {
    Ts ts{};
    f64 best_bid{0.0};
    f64 best_ask{0.0};
    f64 bid_qty{0.0};
    f64 ask_qty{0.0};
};

struct FeaturesOnline {
    Ts ts{};
    f64 mid{0.0};
    f64 spread{0.0};
    f64 microprice{0.0};
    f64 ofi{0.0};
    f64 r_log{0.0};
    f64 vol_w{0.0};
    f64 ema_s{0.0};
    f64 ema_l{0.0};
    f64 macd{0.0};
    f64 macd_signal{0.0};
    f64 macd_hist{0.0};
    f64 rsi{50.0};
};

constexpr f64 kNaN = std::numeric_limits<f64>::quiet_NaN();

}  // namespace bqe
