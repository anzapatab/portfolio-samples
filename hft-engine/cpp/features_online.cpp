// Extract from HFT Quant Engine
// Online feature engineering: computes streaming technical indicators
// (EMA, MACD, RSI, OFI, microprice) from tick-level market data
// using lock-free SPSC ring buffers for zero-copy data flow.

#include "bqe/features_online.hpp"
#include <cmath>

namespace bqe {

static inline double logret(double last, double now) {
    if (last <= 0.0 || now <= 0.0)
        return 0.0;
    return std::log(now) - std::log(last);
}

void FeatureEngine::update_from_trade(const TradeFrame& t) {
    double r = logret(st_.last_close > 0 ? st_.last_close : t.px, t.px);
    st_.last_close = t.px;

    st_.vol_n += 1;
    double delta = r - st_.vol_mean;
    st_.vol_mean += delta / static_cast<double>(st_.vol_n);
    st_.vol_m2 += delta * (r - st_.vol_mean);

    st_.ema_s = (st_.ema_s == 0.0) ? t.px : st_.alpha_s * t.px + (1.0 - st_.alpha_s) * st_.ema_s;
    st_.ema_l = (st_.ema_l == 0.0) ? t.px : st_.alpha_l * t.px + (1.0 - st_.alpha_l) * st_.ema_l;
    double macd = st_.ema_s - st_.ema_l;
    st_.ema_signal = (st_.ema_signal == 0.0) ? macd : 0.2 * macd + 0.8 * st_.ema_signal;
    st_.ema_macd = macd;

    // RSI calculation using per-instance state (thread-safe)
    if (st_.rsi_prev_price == 0.0)
        st_.rsi_prev_price = t.px;
    double chg = t.px - st_.rsi_prev_price;
    st_.rsi_prev_price = t.px;
    double gain = chg > 0 ? chg : 0.0;
    double loss = chg < 0 ? -chg : 0.0;
    st_.rsi_avg_gain =
        (st_.rsi_avg_gain == 0.0) ? gain : st_.alpha_rsi * gain + (1.0 - st_.alpha_rsi) * st_.rsi_avg_gain;
    st_.rsi_avg_loss =
        (st_.rsi_avg_loss == 0.0) ? loss : st_.alpha_rsi * loss + (1.0 - st_.alpha_rsi) * st_.rsi_avg_loss;
}

void FeatureEngine::update_from_l1(const BookL1& b) {
    if (!have_l1_) {
        st_.prev_bid = b.best_bid;
        st_.prev_ask = b.best_ask;
        st_.prev_bid_qty = b.bid_qty;
        st_.prev_ask_qty = b.ask_qty;
        have_l1_ = true;
        last_l1_ = b;
        return;
    }
    double d_bid = (b.best_bid > st_.prev_bid)   ? b.bid_qty
                   : (b.best_bid < st_.prev_bid) ? -st_.prev_bid_qty
                                                 : (b.bid_qty - st_.prev_bid_qty);
    double d_ask = (b.best_ask < st_.prev_ask)   ? b.ask_qty
                   : (b.best_ask > st_.prev_ask) ? -st_.prev_ask_qty
                                                 : (st_.prev_ask_qty - b.ask_qty);
    st_.ofi += (d_bid + d_ask);
    st_.prev_bid = b.best_bid;
    st_.prev_ask = b.best_ask;
    st_.prev_bid_qty = b.bid_qty;
    st_.prev_ask_qty = b.ask_qty;
    last_l1_ = b;
}

bool FeatureEngine::emit_feature(Ts ts) {
    if (!have_l1_)
        return false;
    FeaturesOnline f;
    f.ts = ts;
    f.spread = last_l1_.best_ask - last_l1_.best_bid;
    f.mid = (last_l1_.best_ask + last_l1_.best_bid) * 0.5;
    double w =
        (last_l1_.bid_qty + last_l1_.ask_qty) > 0 ? last_l1_.ask_qty / (last_l1_.bid_qty + last_l1_.ask_qty) : 0.5;
    f.microprice = w * last_l1_.best_bid + (1.0 - w) * last_l1_.best_ask;

    f.ema_s = st_.ema_s;
    f.ema_l = st_.ema_l;
    f.macd = st_.ema_macd;
    f.macd_signal = st_.ema_signal;
    f.macd_hist = f.macd - f.macd_signal;

    double rs = (st_.rsi_avg_loss > 1e-12) ? (st_.rsi_avg_gain / st_.rsi_avg_loss) : 1e9;
    f.rsi = 100.0 - (100.0 / (1.0 + rs));

    f.r_log = 0.0;
    f.ofi = st_.ofi;

    return out_.push(f);
}

void FeatureEngine::run_once() {
    TradeFrame t;
    while (in_trades_.pop(t)) {
        update_from_trade(t);
        emit_feature(t.ts);
    }
    BookL1 b;
    while (in_l1_.pop(b)) {
        update_from_l1(b);
        emit_feature(b.ts);
    }
}

}  // namespace bqe
