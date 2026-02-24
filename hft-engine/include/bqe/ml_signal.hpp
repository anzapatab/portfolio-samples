// Extract from HFT Quant Engine
// ML signal generator: converts ONNX model predictions into actionable
// trading signals with confidence thresholds, edge filtering, cooldown,
// spread checks, and Kelly-inspired position sizing.

#pragma once

#include <chrono>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "types.hpp"

namespace bqe {

// Trading action derived from ML prediction
enum class SignalAction : uint8_t {
    HOLD = 0,  // No action (flat prediction or low confidence)
    BUY = 1,   // Long signal
    SELL = 2   // Short/exit signal
};

// Prediction class from the ML model
enum class PredictionClass : uint8_t {
    DOWN = 0,  // Price expected to decrease
    FLAT = 1,  // Price expected to stay flat
    UP = 2     // Price expected to increase
};

// Trading signal generated from ML inference
struct TradingSignal {
    Ts timestamp{};                           // Signal generation time
    SignalAction action{SignalAction::HOLD};  // Recommended action
    PredictionClass prediction{PredictionClass::FLAT};

    // Model output probabilities
    float prob_down{0.0f};
    float prob_flat{0.0f};
    float prob_up{0.0f};

    // Derived metrics
    float confidence{0.0f};   // Max probability (confidence in prediction)
    float edge{0.0f};         // Difference between max and second max prob
    float signal_strength{0.0f};  // Combined metric for position sizing

    // Feature snapshot (for debugging/audit)
    f64 mid_price{0.0};
    f64 spread{0.0};
    f64 rsi{50.0};

    // Latency tracking
    int64_t inference_latency_ns{0};  // Time to run inference

    // Risk-adjusted recommendation
    f64 suggested_quantity{0.0};  // After risk adjustment
    bool risk_approved{false};    // Passed risk checks
    std::string risk_reason;      // If not approved, why

    // Metadata
    uint64_t sequence_id{0};  // Monotonic sequence number
    std::string symbol;       // Trading symbol
};

// Configuration for signal generation
struct MLSignalConfig {
    // Confidence thresholds
    float min_confidence{0.50f};  // tune via config
    float high_confidence{0.75f}; // tune via config

    // Edge threshold (difference between top 2 probabilities)
    float min_edge{0.10f};  // tune via config

    // Position sizing
    f64 base_position_size{0.01};   // tune via config
    f64 max_position_size{0.10};    // tune via config
    f64 confidence_scale{2.0};      // Scale factor for high confidence

    // Signal generation
    bool require_trend_confirmation{false};  // Require EMA alignment
    int cooldown_ticks{10};  // Minimum ticks between signals

    // Risk parameters
    f64 max_spread_bps{50.0};  // Max spread in basis points to trade
    f64 min_volume{0.001};     // Minimum volume to trade
};

// ML Signal Generator: converts model predictions to actionable signals
class MLSignalGenerator {
public:
    explicit MLSignalGenerator(const MLSignalConfig& config = {})
        : config_(config) {}

    // Generate trading signal from model output
    TradingSignal generate(const std::vector<float>& prediction,
                           const FeaturesOnline& features,
                           const std::string& symbol = "BTCUSDT") {
        TradingSignal signal;
        signal.timestamp = features.ts;
        signal.symbol = symbol;
        signal.sequence_id = ++sequence_counter_;

        // Store feature snapshot
        signal.mid_price = features.mid;
        signal.spread = features.spread;
        signal.rsi = features.rsi;

        // Validate prediction vector
        if (prediction.size() < 3) {
            signal.action = SignalAction::HOLD;
            signal.risk_reason = "Invalid prediction size";
            return signal;
        }

        // Extract probabilities
        signal.prob_down = prediction[0];
        signal.prob_flat = prediction[1];
        signal.prob_up = prediction[2];

        // Determine prediction class and confidence
        auto [pred_class, confidence, edge] = analyze_prediction(prediction);
        signal.prediction = pred_class;
        signal.confidence = confidence;
        signal.edge = edge;

        // Calculate signal strength (combines confidence and edge)
        signal.signal_strength = calculate_signal_strength(confidence, edge);

        // Check spread filter
        f64 spread_bps = (features.spread / features.mid) * 10000.0;
        if (spread_bps > config_.max_spread_bps) {
            signal.action = SignalAction::HOLD;
            signal.risk_reason = "Spread too wide: " + std::to_string(spread_bps) + " bps";
            return signal;
        }

        // Check cooldown
        if (ticks_since_last_signal_ < config_.cooldown_ticks) {
            ticks_since_last_signal_++;
            signal.action = SignalAction::HOLD;
            signal.risk_reason = "Cooldown active";
            return signal;
        }

        // Check confidence threshold
        if (confidence < config_.min_confidence) {
            signal.action = SignalAction::HOLD;
            signal.risk_reason = "Low confidence: " + std::to_string(confidence);
            return signal;
        }

        // Check edge threshold
        if (edge < config_.min_edge) {
            signal.action = SignalAction::HOLD;
            signal.risk_reason = "Low edge: " + std::to_string(edge);
            return signal;
        }

        // Optional: trend confirmation using EMA
        if (config_.require_trend_confirmation) {
            bool ema_bullish = features.ema_s > features.ema_l;
            bool ema_bearish = features.ema_s < features.ema_l;

            if (pred_class == PredictionClass::UP && !ema_bullish) {
                signal.action = SignalAction::HOLD;
                signal.risk_reason = "UP prediction but EMA bearish";
                return signal;
            }
            if (pred_class == PredictionClass::DOWN && !ema_bearish) {
                signal.action = SignalAction::HOLD;
                signal.risk_reason = "DOWN prediction but EMA bullish";
                return signal;
            }
        }

        // Determine action
        switch (pred_class) {
            case PredictionClass::UP:
                signal.action = SignalAction::BUY;
                break;
            case PredictionClass::DOWN:
                signal.action = SignalAction::SELL;
                break;
            case PredictionClass::FLAT:
            default:
                signal.action = SignalAction::HOLD;
                break;
        }

        // Calculate suggested quantity based on confidence
        if (signal.action != SignalAction::HOLD) {
            signal.suggested_quantity = calculate_position_size(confidence, edge);
            ticks_since_last_signal_ = 0;  // Reset cooldown
        }

        return signal;
    }

    // Update configuration
    void set_config(const MLSignalConfig& config) {
        config_ = config;
    }

    const MLSignalConfig& get_config() const {
        return config_;
    }

    // Statistics
    uint64_t get_signal_count() const { return sequence_counter_; }

private:
    MLSignalConfig config_;
    uint64_t sequence_counter_{0};
    int ticks_since_last_signal_{1000};  // Start ready to trade

    // Analyze prediction to extract class, confidence, and edge
    std::tuple<PredictionClass, float, float> analyze_prediction(
        const std::vector<float>& pred) {

        // Find max and second max
        float max_prob = pred[0];
        float second_max = 0.0f;
        int max_idx = 0;

        for (size_t i = 1; i < pred.size(); ++i) {
            if (pred[i] > max_prob) {
                second_max = max_prob;
                max_prob = pred[i];
                max_idx = static_cast<int>(i);
            } else if (pred[i] > second_max) {
                second_max = pred[i];
            }
        }

        PredictionClass pred_class = static_cast<PredictionClass>(max_idx);
        float confidence = max_prob;
        float edge = max_prob - second_max;

        return {pred_class, confidence, edge};
    }

    // Calculate signal strength from confidence and edge
    float calculate_signal_strength(float confidence, float edge) {
        // proprietary signal strength formula omitted
        return std::min(confidence, 1.0f);
    }

    // Calculate position size based on confidence and edge
    f64 calculate_position_size(float confidence, float edge) {
        // proprietary position sizing logic omitted
        return config_.base_position_size;
    }
};

}  // namespace bqe
