// Extract from HFT Quant Engine
// ZeroMQ PUB/SUB signal publisher: broadcasts trading signals and feature
// snapshots to downstream consumers (execution engines, loggers, dashboards)
// using topic-based routing (e.g., "SIGNAL.BTCUSDT.BUY").

#pragma once

#include <chrono>
#include <memory>
#include <string>
#include <sstream>

#include <zmq.hpp>

#include "ml_signal.hpp"

namespace bqe {

// ZMQ Publisher for trading signals
// Publishes signals to subscribers (execution engines, loggers, dashboards)
// Uses simple JSON serialization for portability
class SignalPublisher {
public:
    explicit SignalPublisher(const std::string& bind_address = "tcp://*:5555")
        : context_(1), socket_(context_, zmq::socket_type::pub) {
        socket_.bind(bind_address);
        bound_address_ = bind_address;
    }

    ~SignalPublisher() {
        try {
            socket_.close();
            context_.close();
        } catch (...) {
            // Ignore errors during shutdown
        }
    }

    // Non-copyable
    SignalPublisher(const SignalPublisher&) = delete;
    SignalPublisher& operator=(const SignalPublisher&) = delete;

    // Publish a trading signal (JSON format)
    bool publish(const TradingSignal& signal) {
        try {
            // Serialize to JSON string
            std::ostringstream json;
            json << "{"
                 << "\"ts\":" << signal.timestamp.ns << ","
                 << "\"symbol\":\"" << signal.symbol << "\","
                 << "\"seq\":" << signal.sequence_id << ","
                 << "\"action\":" << static_cast<int>(signal.action) << ","
                 << "\"pred\":" << static_cast<int>(signal.prediction) << ","
                 << "\"prob_down\":" << signal.prob_down << ","
                 << "\"prob_flat\":" << signal.prob_flat << ","
                 << "\"prob_up\":" << signal.prob_up << ","
                 << "\"confidence\":" << signal.confidence << ","
                 << "\"edge\":" << signal.edge << ","
                 << "\"strength\":" << signal.signal_strength << ","
                 << "\"mid\":" << signal.mid_price << ","
                 << "\"spread\":" << signal.spread << ","
                 << "\"rsi\":" << signal.rsi << ","
                 << "\"latency_ns\":" << signal.inference_latency_ns << ","
                 << "\"qty\":" << signal.suggested_quantity << ","
                 << "\"risk_ok\":" << (signal.risk_approved ? "true" : "false") << ","
                 << "\"risk_reason\":\"" << signal.risk_reason << "\""
                 << "}";

            std::string serialized = json.str();

            // Create topic: "SIGNAL.<symbol>.<action>"
            std::string topic = "SIGNAL." + signal.symbol + "." +
                                action_to_string(signal.action);

            // Send topic frame
            zmq::message_t topic_msg(topic.data(), topic.size());
            socket_.send(topic_msg, zmq::send_flags::sndmore);

            // Send data frame
            zmq::message_t data_msg(serialized.data(), serialized.size());
            socket_.send(data_msg, zmq::send_flags::none);

            signals_published_++;
            return true;

        } catch (const zmq::error_t& e) {
            last_error_ = e.what();
            return false;
        }
    }

    // Publish raw features (JSON format for debugging/monitoring)
    bool publish_features(const FeaturesOnline& features, const std::string& symbol = "BTCUSDT") {
        try {
            std::ostringstream json;
            json << "{"
                 << "\"ts\":" << features.ts.ns << ","
                 << "\"mid\":" << features.mid << ","
                 << "\"spread\":" << features.spread << ","
                 << "\"microprice\":" << features.microprice << ","
                 << "\"ofi\":" << features.ofi << ","
                 << "\"r_log\":" << features.r_log << ","
                 << "\"vol_w\":" << features.vol_w << ","
                 << "\"ema_s\":" << features.ema_s << ","
                 << "\"ema_l\":" << features.ema_l << ","
                 << "\"macd\":" << features.macd << ","
                 << "\"macd_signal\":" << features.macd_signal << ","
                 << "\"macd_hist\":" << features.macd_hist << ","
                 << "\"rsi\":" << features.rsi
                 << "}";

            std::string serialized = json.str();

            std::string topic = "FEATURES." + symbol;
            zmq::message_t topic_msg(topic.data(), topic.size());
            socket_.send(topic_msg, zmq::send_flags::sndmore);

            zmq::message_t data_msg(serialized.data(), serialized.size());
            socket_.send(data_msg, zmq::send_flags::none);

            features_published_++;
            return true;

        } catch (const zmq::error_t& e) {
            last_error_ = e.what();
            return false;
        }
    }

    // Statistics
    uint64_t signals_published() const { return signals_published_; }
    uint64_t features_published() const { return features_published_; }
    const std::string& last_error() const { return last_error_; }
    const std::string& bound_address() const { return bound_address_; }

private:
    zmq::context_t context_;
    zmq::socket_t socket_;
    std::string bound_address_;

    uint64_t signals_published_{0};
    uint64_t features_published_{0};
    std::string last_error_;

    static std::string action_to_string(SignalAction action) {
        switch (action) {
            case SignalAction::BUY: return "BUY";
            case SignalAction::SELL: return "SELL";
            case SignalAction::HOLD:
            default: return "HOLD";
        }
    }
};

}  // namespace bqe
