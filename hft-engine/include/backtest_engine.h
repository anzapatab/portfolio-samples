// Extract from HFT Quant Engine
// Backtesting engine header: SimulatedExchange (order matching, slippage,
// maker/taker fees), BacktestEngine (tick replay, strategy callbacks,
// Sharpe/Sortino/drawdown metrics, Parquet data loading).

#pragma once
#include <functional>
#include <map>
#include <memory>
#include <string>
#include <vector>

// Forward declarations for types defined in other modules
enum class OrderSide { BUY, SELL };
enum class OrderType { MARKET, LIMIT };
enum class OrderStatus { NEW, PARTIALLY_FILLED, FILLED, CANCELED, REJECTED };

struct Order {
    long long order_id{0};
    std::string symbol;
    OrderSide side{OrderSide::BUY};
    OrderType type{OrderType::MARKET};
    double quantity{0.0};
    double price{0.0};
    OrderStatus status{OrderStatus::NEW};
    double executed_qty{0.0};
    double cumulative_quote_qty{0.0};
    long long transact_time{0};
};

struct RiskConfig {};
class RiskManager {
public:
    RiskManager() = default;
    explicit RiskManager(const RiskConfig&) {}
    void updateMarketPrice(const std::string&, double) {}
};

// Market data tick for backtesting
struct MarketTick {
    long long timestamp{0};  // Unix timestamp (milliseconds)
    std::string symbol;
    double price{0.0};
    double quantity{0.0};
    bool is_buyer_maker{false};  // true = sell, false = buy

    // Order book data (optional)
    double bid_price{0.0};
    double bid_quantity{0.0};
    double ask_price{0.0};
    double ask_quantity{0.0};
};

// Simulated fill result
struct SimulatedFill {
    long long timestamp{0};
    long long order_id{0};
    std::string symbol;
    OrderSide side;
    double quantity{0.0};
    double price{0.0};       // Actual fill price (may include slippage)
    double commission{0.0};  // Trading fees
    bool is_maker{false};    // Maker vs taker
};

// Trade result for performance analysis
struct TradeResult {
    long long entry_time{0};
    long long exit_time{0};
    std::string symbol;
    OrderSide entry_side;
    double entry_price{0.0};
    double exit_price{0.0};
    double quantity{0.0};
    double pnl{0.0};      // Profit/loss
    double pnl_pct{0.0};  // P&L percentage
    double commission{0.0};
    long long duration_ms{0};  // Trade duration
};

// Performance metrics
struct BacktestMetrics {
    // Returns
    double total_return{0.0};
    double total_return_pct{0.0};
    double annualized_return{0.0};

    // Risk metrics
    double sharpe_ratio{0.0};
    double sortino_ratio{0.0};
    double max_drawdown{0.0};
    double max_drawdown_pct{0.0};

    // Trade statistics
    int total_trades{0};
    int winning_trades{0};
    int losing_trades{0};
    double win_rate{0.0};
    double avg_win{0.0};
    double avg_loss{0.0};
    double profit_factor{0.0};  // Total wins / Total losses

    // Position statistics
    double avg_position_duration_ms{0.0};
    double longest_position_ms{0.0};
    double shortest_position_ms{0.0};

    // Equity curve
    std::vector<double> equity_curve;
    std::vector<long long> equity_timestamps;
};

// Simulated Exchange - Mocks exchange behavior
class SimulatedExchange {
public:
    SimulatedExchange(double initial_balance_usdt = 100000.0,
                      double maker_fee = 0.001,   // 0.1% maker
                      double taker_fee = 0.001);  // 0.1% taker

    // Process market tick (update order book, check fills)
    void processTick(const MarketTick& tick);

    // Order management (simulated)
    Order placeOrder(const std::string& symbol, OrderSide side, OrderType type, double quantity, double price = 0.0);

    bool cancelOrder(long long order_id);

    Order getOrder(long long order_id) const;
    std::vector<Order> getOpenOrders() const;

    // Account state
    double getBalance(const std::string& asset) const;
    std::map<std::string, double> getAllBalances() const;

    // Fills
    const std::vector<SimulatedFill>& getFills() const;
    void clearFills();

    // Current market state
    double getCurrentPrice(const std::string& symbol) const;
    MarketTick getLastTick(const std::string& symbol) const;

    // Configuration
    void setSlippageModel(double slippage_bps);  // Basis points (1 bps = 0.01%)
    void setLatency(long long latency_ms);       // Simulated order latency

private:
    double initial_balance_;
    double maker_fee_;
    double taker_fee_;
    double slippage_bps_{5.0};  // Default 5 bps slippage
    long long latency_ms_{10};  // Default 10ms latency

    long long next_order_id_{1};
    long long current_time_{0};

    // State
    std::map<std::string, double> balances_;
    std::map<long long, Order> orders_;            // order_id -> Order
    std::map<std::string, MarketTick> last_tick_;  // symbol -> last tick
    std::vector<SimulatedFill> fills_;

    // Internal methods
    void tryFillOrders(const MarketTick& tick);
    SimulatedFill executeFill(Order& order, double fill_price, double fill_qty, bool is_maker);
    double calculateSlippage(OrderSide side, double price);
    void updateBalance(const std::string& asset, double delta);
};

// Backtest Engine - Replays market data
class BacktestEngine {
public:
    BacktestEngine();

    // Load market data
    void loadTicksFromCSV(const std::string& filename);
    void loadTicksFromParquet(const std::string& filename);
    void addTick(const MarketTick& tick);

    // Direct tick access (for walk-forward optimization)
    void setTicks(const std::vector<MarketTick>& ticks);
    const std::vector<MarketTick>& getTicks() const;

    // Set initial capital
    void setInitialCapital(double capital_usdt);

    // Set fees
    void setFees(double maker_fee, double taker_fee);

    // Set slippage model
    void setSlippage(double slippage_bps);

    // Set risk manager configuration
    void setRiskConfig(const RiskConfig& config);

    // Set strategy callback
    using StrategyCallback = std::function<void(const MarketTick&, SimulatedExchange&, RiskManager&)>;
    void setStrategy(StrategyCallback strategy);

    // Run backtest
    void run();

    // Get results
    const BacktestMetrics& getMetrics() const;
    const std::vector<TradeResult>& getTrades() const;
    const std::vector<SimulatedFill>& getFills() const;

    // Get exchange (for inspection)
    const SimulatedExchange& getExchange() const;

    // Generate report
    std::string generateReport() const;
    void exportToCSV(const std::string& filename) const;

private:
    std::vector<MarketTick> ticks_;
    std::unique_ptr<SimulatedExchange> exchange_;
    std::unique_ptr<RiskManager> risk_manager_;
    StrategyCallback strategy_;

    std::vector<TradeResult> trades_;
    BacktestMetrics metrics_;

    // Internal methods
    void calculateMetrics();
    void detectTrades();  // Match buys/sells to compute trades
    double calculateSharpeRatio(const std::vector<double>& returns);
    double calculateMaxDrawdown(const std::vector<double>& equity);
};
