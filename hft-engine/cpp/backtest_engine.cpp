// Extract from HFT Quant Engine
// Backtesting engine with simulated exchange, order management, slippage modeling,
// and Parquet/CSV data loading via Apache Arrow.

#include "backtest_engine.h"
#include <arrow/api.h>
#include <arrow/io/api.h>
#include <parquet/arrow/reader.h>
#include <parquet/arrow/schema.h>
#include <parquet/exception.h>
#include <spdlog/spdlog.h>
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>

// ========== SimulatedExchange Implementation ==========

SimulatedExchange::SimulatedExchange(double initial_balance_usdt, double maker_fee, double taker_fee)
    : initial_balance_(initial_balance_usdt), maker_fee_(maker_fee), taker_fee_(taker_fee) {
    balances_["USDT"] = initial_balance_usdt;
    spdlog::info("[SimulatedExchange] Initialized with ${:.2f} USDT", initial_balance_usdt);
}

void SimulatedExchange::processTick(const MarketTick& tick) {
    current_time_ = tick.timestamp;
    last_tick_[tick.symbol] = tick;

    // Try to fill pending orders
    tryFillOrders(tick);
}

Order SimulatedExchange::placeOrder(const std::string& symbol, OrderSide side, OrderType type, double quantity,
                                    double price) {
    Order order;
    order.order_id = next_order_id_++;
    order.symbol = symbol;
    order.side = side;
    order.type = type;
    order.quantity = quantity;
    order.price = price;
    order.status = OrderStatus::NEW;
    order.transact_time = current_time_;

    // Check if we have sufficient balance
    if (side == OrderSide::BUY) {
        double required_usdt = quantity * price * (1.0 + taker_fee_);
        if (balances_["USDT"] < required_usdt) {
            order.status = OrderStatus::REJECTED;
            spdlog::warn("[SimulatedExchange] Insufficient balance: need ${:.2f}, have ${:.2f}", required_usdt,
                         balances_["USDT"]);
            return order;
        }
    } else {  // SELL
        std::string base = symbol.substr(0, symbol.find("USDT"));
        if (balances_[base] < quantity) {
            order.status = OrderStatus::REJECTED;
            spdlog::warn("[SimulatedExchange] Insufficient {} balance: need {}, have {}", base, quantity,
                         balances_[base]);
            return order;
        }
    }

    orders_[order.order_id] = order;

    // Market orders fill immediately at current price
    if (type == OrderType::MARKET) {
        auto it = last_tick_.find(symbol);
        if (it != last_tick_.end()) {
            double fill_price = it->second.price;
            fill_price = calculateSlippage(side, fill_price);

            auto fill = executeFill(order, fill_price, quantity, false);  // taker
            order.status = OrderStatus::FILLED;
            order.executed_qty = quantity;
            order.cumulative_quote_qty = quantity * fill_price;
            orders_[order.order_id] = order;

            spdlog::debug("[SimulatedExchange] Market order filled: {} {} @ ${}", quantity, symbol, fill_price);
        } else {
            order.status = OrderStatus::REJECTED;
            spdlog::error("[SimulatedExchange] No market data for {}", symbol);
        }
    } else {
        spdlog::debug("[SimulatedExchange] Limit order placed: {} {} @ ${}", quantity, symbol, price);
    }

    return order;
}

bool SimulatedExchange::cancelOrder(long long order_id) {
    auto it = orders_.find(order_id);
    if (it == orders_.end()) {
        return false;
    }

    Order& order = it->second;
    if (order.status == OrderStatus::FILLED || order.status == OrderStatus::CANCELED) {
        return false;
    }

    order.status = OrderStatus::CANCELED;
    orders_[order_id] = order;
    spdlog::debug("[SimulatedExchange] Order {} canceled", order_id);
    return true;
}

Order SimulatedExchange::getOrder(long long order_id) const {
    auto it = orders_.find(order_id);
    if (it != orders_.end()) {
        return it->second;
    }
    return Order{};
}

std::vector<Order> SimulatedExchange::getOpenOrders() const {
    std::vector<Order> open_orders;
    for (const auto& [id, order] : orders_) {
        if (order.status == OrderStatus::NEW || order.status == OrderStatus::PARTIALLY_FILLED) {
            open_orders.push_back(order);
        }
    }
    return open_orders;
}

double SimulatedExchange::getBalance(const std::string& asset) const {
    auto it = balances_.find(asset);
    return (it != balances_.end()) ? it->second : 0.0;
}

std::map<std::string, double> SimulatedExchange::getAllBalances() const {
    return balances_;
}

const std::vector<SimulatedFill>& SimulatedExchange::getFills() const {
    return fills_;
}

void SimulatedExchange::clearFills() {
    fills_.clear();
}

double SimulatedExchange::getCurrentPrice(const std::string& symbol) const {
    auto it = last_tick_.find(symbol);
    return (it != last_tick_.end()) ? it->second.price : 0.0;
}

MarketTick SimulatedExchange::getLastTick(const std::string& symbol) const {
    auto it = last_tick_.find(symbol);
    return (it != last_tick_.end()) ? it->second : MarketTick{};
}

void SimulatedExchange::setSlippageModel(double slippage_bps) {
    slippage_bps_ = slippage_bps;
}

void SimulatedExchange::setLatency(long long latency_ms) {
    latency_ms_ = latency_ms;
}

// ========== Private Methods ==========

void SimulatedExchange::tryFillOrders(const MarketTick& tick) {
    for (auto& [id, order] : orders_) {
        if (order.status != OrderStatus::NEW && order.status != OrderStatus::PARTIALLY_FILLED) {
            continue;
        }

        if (order.symbol != tick.symbol) {
            continue;
        }

        if (order.type != OrderType::LIMIT) {
            continue;  // Only LIMIT orders stay on the book
        }

        // Check if order can be filled
        bool can_fill = false;
        bool is_maker = true;

        if (order.side == OrderSide::BUY) {
            // Buy limit order fills when market price <= limit price
            double market_price = (tick.ask_price > 0) ? tick.ask_price : tick.price;
            can_fill = (market_price <= order.price);
        } else {  // SELL
            // Sell limit order fills when market price >= limit price
            double market_price = (tick.bid_price > 0) ? tick.bid_price : tick.price;
            can_fill = (market_price >= order.price);
        }

        if (can_fill) {
            double remaining_qty = order.quantity - order.executed_qty;
            double fill_qty = std::min(remaining_qty, tick.quantity);
            double fill_price = order.price;  // Fill at limit price (maker)

            auto fill = executeFill(order, fill_price, fill_qty, is_maker);

            order.executed_qty += fill_qty;
            order.cumulative_quote_qty += fill_qty * fill_price;

            if (order.executed_qty >= order.quantity) {
                order.status = OrderStatus::FILLED;
                spdlog::debug("[SimulatedExchange] Order {} fully filled", order.order_id);
            } else {
                order.status = OrderStatus::PARTIALLY_FILLED;
                spdlog::debug("[SimulatedExchange] Order {} partially filled: {}/{}", order.order_id,
                              order.executed_qty, order.quantity);
            }
        }
    }
}

SimulatedFill SimulatedExchange::executeFill(Order& order, double fill_price, double fill_qty, bool is_maker) {
    SimulatedFill fill;
    fill.timestamp = current_time_;
    fill.order_id = order.order_id;
    fill.symbol = order.symbol;
    fill.side = order.side;
    fill.quantity = fill_qty;
    fill.price = fill_price;
    fill.is_maker = is_maker;

    double fee_rate = is_maker ? maker_fee_ : taker_fee_;
    double quote_value = fill_qty * fill_price;

    if (order.side == OrderSide::BUY) {
        // Buying: pay USDT, receive base currency
        double total_cost = quote_value * (1.0 + fee_rate);
        fill.commission = quote_value * fee_rate;

        updateBalance("USDT", -total_cost);

        std::string base = order.symbol.substr(0, order.symbol.find("USDT"));
        updateBalance(base, fill_qty);

        spdlog::debug("[SimulatedExchange] BUY fill: {} {} @ ${:.2f}, cost ${:.2f}", fill_qty, base, fill_price,
                      total_cost);

    } else {  // SELL
        // Selling: pay base currency, receive USDT
        std::string base = order.symbol.substr(0, order.symbol.find("USDT"));
        double proceeds = quote_value * (1.0 - fee_rate);
        fill.commission = quote_value * fee_rate;

        updateBalance(base, -fill_qty);
        updateBalance("USDT", proceeds);

        spdlog::debug("[SimulatedExchange] SELL fill: {} {} @ ${:.2f}, proceeds ${:.2f}", fill_qty, base, fill_price,
                      proceeds);
    }

    fills_.push_back(fill);
    return fill;
}

double SimulatedExchange::calculateSlippage(OrderSide side, double price) {
    // Slippage in basis points (1 bps = 0.01%)
    double slippage_factor = slippage_bps_ / 10000.0;

    if (side == OrderSide::BUY) {
        // Buying: price goes up (unfavorable)
        return price * (1.0 + slippage_factor);
    } else {
        // Selling: price goes down (unfavorable)
        return price * (1.0 - slippage_factor);
    }
}

void SimulatedExchange::updateBalance(const std::string& asset, double delta) {
    balances_[asset] += delta;
}

// ========== BacktestEngine Implementation ==========

BacktestEngine::BacktestEngine()
    : exchange_(std::make_unique<SimulatedExchange>()), risk_manager_(std::make_unique<RiskManager>()) {
    spdlog::info("[BacktestEngine] Initialized");
}

void BacktestEngine::loadTicksFromCSV(const std::string& filename) {
    std::ifstream file(filename);
    if (!file.is_open()) {
        throw std::runtime_error("Failed to open CSV file: " + filename);
    }

    std::string line;
    std::getline(file, line);  // Skip header

    int count = 0;
    while (std::getline(file, line)) {
        std::istringstream iss(line);
        std::string token;

        MarketTick tick;

        // Parse CSV: timestamp,symbol,price,quantity,is_buyer_maker
        std::getline(iss, token, ',');
        tick.timestamp = std::stoll(token);

        std::getline(iss, token, ',');
        tick.symbol = token;

        std::getline(iss, token, ',');
        tick.price = std::stod(token);

        std::getline(iss, token, ',');
        tick.quantity = std::stod(token);

        std::getline(iss, token, ',');
        tick.is_buyer_maker = (token == "true" || token == "1");

        ticks_.push_back(tick);
        count++;
    }

    // Sort by timestamp
    std::sort(ticks_.begin(), ticks_.end(),
              [](const MarketTick& a, const MarketTick& b) { return a.timestamp < b.timestamp; });

    spdlog::info("[BacktestEngine] Loaded {} ticks from {}", count, filename);
}

void BacktestEngine::loadTicksFromParquet(const std::string& path) {
    namespace fs = std::filesystem;

    std::vector<std::string> parquet_files;

    // Check if path is a file or directory
    if (fs::is_regular_file(path)) {
        parquet_files.push_back(path);
    } else if (fs::is_directory(path)) {
        // Recursively find all .parquet files
        for (const auto& entry : fs::recursive_directory_iterator(path)) {
            if (entry.is_regular_file() && entry.path().extension() == ".parquet") {
                parquet_files.push_back(entry.path().string());
            }
        }

        // Sort files by path for chronological order
        std::sort(parquet_files.begin(), parquet_files.end());
    } else {
        throw std::runtime_error("Path not found: " + path);
    }

    if (parquet_files.empty()) {
        throw std::runtime_error("No parquet files found in: " + path);
    }

    spdlog::info("[BacktestEngine] Loading data from {} parquet files", parquet_files.size());

    int total_ticks = 0;

    for (const auto& filename : parquet_files) {
        // Open parquet file and read table
        std::shared_ptr<arrow::io::RandomAccessFile> source;
        PARQUET_ASSIGN_OR_THROW(source, arrow::io::ReadableFile::Open(filename));

        std::unique_ptr<parquet::arrow::FileReader> arrow_reader;
        parquet::ArrowReaderProperties properties = parquet::default_arrow_reader_properties();
        PARQUET_THROW_NOT_OK(parquet::arrow::FileReader::Make(
            arrow::default_memory_pool(), parquet::ParquetFileReader::Open(source), properties, &arrow_reader));

        // Read table
        std::shared_ptr<arrow::Table> table;
        PARQUET_THROW_NOT_OK(arrow_reader->ReadTable(&table));

        // Extract columns
        auto schema = table->schema();
        int64_t num_rows = table->num_rows();

        // Find column indices
        int col_open_time = schema->GetFieldIndex("open_time_ms");
        int col_open = schema->GetFieldIndex("open");
        int col_high = schema->GetFieldIndex("high");
        int col_low = schema->GetFieldIndex("low");
        int col_close = schema->GetFieldIndex("close");
        int col_volume = schema->GetFieldIndex("volume");

        if (col_open_time < 0 || col_open < 0 || col_close < 0) {
            spdlog::error("Missing required columns in: {}", filename);
            continue;
        }

        // Get column arrays
        auto col_open_time_arr = std::static_pointer_cast<arrow::Int64Array>(table->column(col_open_time)->chunk(0));
        auto col_open_arr = std::static_pointer_cast<arrow::DoubleArray>(table->column(col_open)->chunk(0));
        auto col_high_arr = std::static_pointer_cast<arrow::DoubleArray>(table->column(col_high)->chunk(0));
        auto col_low_arr = std::static_pointer_cast<arrow::DoubleArray>(table->column(col_low)->chunk(0));
        auto col_close_arr = std::static_pointer_cast<arrow::DoubleArray>(table->column(col_close)->chunk(0));
        auto col_volume_arr = std::static_pointer_cast<arrow::DoubleArray>(table->column(col_volume)->chunk(0));

        // Extract symbol from filename (format: .../symbol=BTCUSDT/...)
        std::string symbol = "BTCUSDT";  // default
        size_t pos = filename.find("symbol=");
        if (pos != std::string::npos) {
            size_t start = pos + 7;  // length of "symbol="
            size_t end = filename.find('/', start);
            if (end != std::string::npos) {
                symbol = filename.substr(start, end - start);
            }
        }

        // Convert each kline to ticks
        // Strategy: Generate 4 ticks per kline (open, high, low, close)
        // to simulate intra-candle movement
        for (int64_t i = 0; i < num_rows; ++i) {
            int64_t open_time = col_open_time_arr->Value(i);
            double open = col_open_arr->Value(i);
            double high = col_high_arr->Value(i);
            double low = col_low_arr->Value(i);
            double close = col_close_arr->Value(i);
            double volume = col_volume_arr->Value(i);

            double avg_tick_volume = volume / 4.0;

            // Tick 1: Open (at candle start)
            MarketTick tick1;
            tick1.timestamp = open_time;
            tick1.symbol = symbol;
            tick1.price = open;
            tick1.quantity = avg_tick_volume;
            tick1.is_buyer_maker = false;
            tick1.bid_price = open * 0.9995;
            tick1.ask_price = open * 1.0005;
            ticks_.push_back(tick1);

            // Tick 2: High (at ~25% into candle)
            MarketTick tick2;
            tick2.timestamp = open_time + 15000;
            tick2.symbol = symbol;
            tick2.price = high;
            tick2.quantity = avg_tick_volume;
            tick2.is_buyer_maker = (high > open);
            tick2.bid_price = high * 0.9995;
            tick2.ask_price = high * 1.0005;
            ticks_.push_back(tick2);

            // Tick 3: Low (at ~50% into candle)
            MarketTick tick3;
            tick3.timestamp = open_time + 30000;
            tick3.symbol = symbol;
            tick3.price = low;
            tick3.quantity = avg_tick_volume;
            tick3.is_buyer_maker = (low < open);
            tick3.bid_price = low * 0.9995;
            tick3.ask_price = low * 1.0005;
            ticks_.push_back(tick3);

            // Tick 4: Close (at candle end)
            MarketTick tick4;
            tick4.timestamp = open_time + 59000;
            tick4.symbol = symbol;
            tick4.price = close;
            tick4.quantity = avg_tick_volume;
            tick4.is_buyer_maker = (close < open);
            tick4.bid_price = close * 0.9995;
            tick4.ask_price = close * 1.0005;
            ticks_.push_back(tick4);

            total_ticks += 4;
        }

        spdlog::debug("[BacktestEngine] Loaded {} klines ({} ticks) from {}", num_rows, num_rows * 4, filename);
    }

    // Sort by timestamp
    std::sort(ticks_.begin(), ticks_.end(),
              [](const MarketTick& a, const MarketTick& b) { return a.timestamp < b.timestamp; });

    spdlog::info("[BacktestEngine] Loaded {} total ticks from {} klines", total_ticks, total_ticks / 4);
}

void BacktestEngine::addTick(const MarketTick& tick) {
    ticks_.push_back(tick);
}

void BacktestEngine::setTicks(const std::vector<MarketTick>& ticks) {
    ticks_ = ticks;
}

const std::vector<MarketTick>& BacktestEngine::getTicks() const {
    return ticks_;
}

void BacktestEngine::setInitialCapital(double capital_usdt) {
    exchange_ = std::make_unique<SimulatedExchange>(capital_usdt);
}

void BacktestEngine::setFees(double maker_fee, double taker_fee) {
    exchange_ = std::make_unique<SimulatedExchange>(exchange_->getBalance("USDT"), maker_fee, taker_fee);
}

void BacktestEngine::setSlippage(double slippage_bps) {
    exchange_->setSlippageModel(slippage_bps);
}

void BacktestEngine::setRiskConfig(const RiskConfig& config) {
    risk_manager_ = std::make_unique<RiskManager>(config);
}

void BacktestEngine::setStrategy(StrategyCallback strategy) {
    strategy_ = std::move(strategy);
}

void BacktestEngine::run() {
    if (!strategy_) {
        throw std::runtime_error("No strategy set");
    }

    if (ticks_.empty()) {
        throw std::runtime_error("No market data loaded");
    }

    spdlog::info("[BacktestEngine] Starting backtest with {} ticks", ticks_.size());

    double initial_equity = exchange_->getBalance("USDT");
    metrics_.equity_curve.push_back(initial_equity);
    metrics_.equity_timestamps.push_back(ticks_[0].timestamp);

    // Replay ticks
    for (size_t i = 0; i < ticks_.size(); ++i) {
        const auto& tick = ticks_[i];

        // Process tick (try to fill pending orders)
        exchange_->processTick(tick);

        // Update risk manager with current price
        risk_manager_->updateMarketPrice(tick.symbol, tick.price);

        // Call strategy
        strategy_(tick, *exchange_, *risk_manager_);

        // Record equity every 1000 ticks
        if (i % 1000 == 0 || i == ticks_.size() - 1) {
            double equity = exchange_->getBalance("USDT");

            // Add value of open positions
            auto balances = exchange_->getAllBalances();
            for (const auto& [asset, qty] : balances) {
                if (asset != "USDT" && qty > 0) {
                    std::string symbol = asset + "USDT";
                    double price = exchange_->getCurrentPrice(symbol);
                    equity += qty * price;
                }
            }

            metrics_.equity_curve.push_back(equity);
            metrics_.equity_timestamps.push_back(tick.timestamp);
        }

        if (i % 10000 == 0) {
            spdlog::debug("[BacktestEngine] Processed {}/{} ticks", i, ticks_.size());
        }
    }

    spdlog::info("[BacktestEngine] Backtest completed");

    // Calculate performance metrics
    detectTrades();
    calculateMetrics();
}

const BacktestMetrics& BacktestEngine::getMetrics() const {
    return metrics_;
}

const std::vector<TradeResult>& BacktestEngine::getTrades() const {
    return trades_;
}

const std::vector<SimulatedFill>& BacktestEngine::getFills() const {
    return exchange_->getFills();
}

const SimulatedExchange& BacktestEngine::getExchange() const {
    return *exchange_;
}

std::string BacktestEngine::generateReport() const {
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(2);

    oss << "\n=== BACKTEST PERFORMANCE REPORT ===\n\n";

    oss << "Returns:\n";
    oss << "  Total Return: $" << metrics_.total_return << " (" << metrics_.total_return_pct << "%)\n";
    oss << "  Annualized Return: " << metrics_.annualized_return << "%\n\n";

    oss << "Risk Metrics:\n";
    oss << "  Sharpe Ratio: " << metrics_.sharpe_ratio << "\n";
    oss << "  Sortino Ratio: " << metrics_.sortino_ratio << "\n";
    oss << "  Max Drawdown: $" << metrics_.max_drawdown << " (" << metrics_.max_drawdown_pct << "%)\n\n";

    oss << "Trade Statistics:\n";
    oss << "  Total Trades: " << metrics_.total_trades << "\n";
    oss << "  Winning Trades: " << metrics_.winning_trades << " (" << metrics_.win_rate << "%)\n";
    oss << "  Losing Trades: " << metrics_.losing_trades << "\n";
    oss << "  Average Win: $" << metrics_.avg_win << "\n";
    oss << "  Average Loss: $" << metrics_.avg_loss << "\n";
    oss << "  Profit Factor: " << metrics_.profit_factor << "\n\n";

    oss << "Position Statistics:\n";
    oss << "  Avg Duration: " << (metrics_.avg_position_duration_ms / 1000.0) << " seconds\n";
    oss << "  Longest Position: " << (metrics_.longest_position_ms / 1000.0) << " seconds\n";
    oss << "  Shortest Position: " << (metrics_.shortest_position_ms / 1000.0) << " seconds\n\n";

    oss << "Final Balances:\n";
    auto balances = exchange_->getAllBalances();
    for (const auto& [asset, qty] : balances) {
        if (qty > 1e-8) {
            oss << "  " << asset << ": " << qty << "\n";
        }
    }

    return oss.str();
}

void BacktestEngine::exportToCSV(const std::string& filename) const {
    std::ofstream file(filename);
    if (!file.is_open()) {
        throw std::runtime_error("Failed to open file: " + filename);
    }

    // Export trades
    file << "entry_time,exit_time,symbol,side,entry_price,exit_price,quantity,pnl,pnl_pct,commission,duration_ms\n";
    for (const auto& trade : trades_) {
        file << trade.entry_time << "," << trade.exit_time << "," << trade.symbol << ","
             << (trade.entry_side == OrderSide::BUY ? "BUY" : "SELL") << "," << trade.entry_price << ","
             << trade.exit_price << "," << trade.quantity << "," << trade.pnl << "," << trade.pnl_pct << ","
             << trade.commission << "," << trade.duration_ms << "\n";
    }

    spdlog::info("[BacktestEngine] Exported trades to {}", filename);
}

// ========== Private Methods ==========

void BacktestEngine::detectTrades() {
    auto fills = exchange_->getFills();

    // Match buys with sells to detect round-trip trades
    std::map<std::string, std::vector<SimulatedFill>> buy_fills;
    std::map<std::string, std::vector<SimulatedFill>> sell_fills;

    for (const auto& fill : fills) {
        if (fill.side == OrderSide::BUY) {
            buy_fills[fill.symbol].push_back(fill);
        } else {
            sell_fills[fill.symbol].push_back(fill);
        }
    }

    // Match fills using FIFO
    for (auto& [symbol, buys] : buy_fills) {
        auto& sells = sell_fills[symbol];

        size_t buy_idx = 0;
        size_t sell_idx = 0;

        while (buy_idx < buys.size() && sell_idx < sells.size()) {
            const auto& buy = buys[buy_idx];
            const auto& sell = sells[sell_idx];

            double qty = std::min(buy.quantity, sell.quantity);

            TradeResult trade;
            trade.entry_time = buy.timestamp;
            trade.exit_time = sell.timestamp;
            trade.symbol = symbol;
            trade.entry_side = OrderSide::BUY;
            trade.entry_price = buy.price;
            trade.exit_price = sell.price;
            trade.quantity = qty;
            trade.pnl = (sell.price - buy.price) * qty - buy.commission - sell.commission;
            trade.pnl_pct = ((sell.price - buy.price) / buy.price) * 100.0;
            trade.commission = buy.commission + sell.commission;
            trade.duration_ms = sell.timestamp - buy.timestamp;

            trades_.push_back(trade);

            buys[buy_idx].quantity -= qty;
            sells[sell_idx].quantity -= qty;

            if (buys[buy_idx].quantity <= 0)
                buy_idx++;
            if (sells[sell_idx].quantity <= 0)
                sell_idx++;
        }
    }

    spdlog::info("[BacktestEngine] Detected {} trades", trades_.size());
}

void BacktestEngine::calculateMetrics() {
    if (metrics_.equity_curve.size() < 2) {
        return;
    }

    double initial_equity = metrics_.equity_curve.front();
    double final_equity = metrics_.equity_curve.back();

    // Returns
    metrics_.total_return = final_equity - initial_equity;
    metrics_.total_return_pct = (metrics_.total_return / initial_equity) * 100.0;

    // Annualized return
    long long duration_ms = metrics_.equity_timestamps.back() - metrics_.equity_timestamps.front();
    double years = duration_ms / (365.25 * 24 * 60 * 60 * 1000.0);
    if (years > 0) {
        metrics_.annualized_return = (std::pow(final_equity / initial_equity, 1.0 / years) - 1.0) * 100.0;
    }

    // Trade statistics
    metrics_.total_trades = trades_.size();
    double total_wins = 0.0;
    double total_losses = 0.0;
    long long total_duration = 0;
    long long max_duration = 0;
    long long min_duration = LLONG_MAX;

    for (const auto& trade : trades_) {
        if (trade.pnl > 0) {
            metrics_.winning_trades++;
            total_wins += trade.pnl;
        } else {
            metrics_.losing_trades++;
            total_losses += std::abs(trade.pnl);
        }

        total_duration += trade.duration_ms;
        max_duration = std::max(max_duration, trade.duration_ms);
        min_duration = std::min(min_duration, trade.duration_ms);
    }

    if (metrics_.total_trades > 0) {
        metrics_.win_rate = (static_cast<double>(metrics_.winning_trades) / metrics_.total_trades) * 100.0;
        metrics_.avg_position_duration_ms = static_cast<double>(total_duration) / metrics_.total_trades;
        metrics_.longest_position_ms = max_duration;
        metrics_.shortest_position_ms = (min_duration != LLONG_MAX) ? min_duration : 0;
    }

    if (metrics_.winning_trades > 0) {
        metrics_.avg_win = total_wins / metrics_.winning_trades;
    }
    if (metrics_.losing_trades > 0) {
        metrics_.avg_loss = total_losses / metrics_.losing_trades;
    }
    if (total_losses > 0) {
        metrics_.profit_factor = total_wins / total_losses;
    }

    // Calculate Sharpe ratio
    std::vector<double> returns;
    for (size_t i = 1; i < metrics_.equity_curve.size(); ++i) {
        double ret = (metrics_.equity_curve[i] - metrics_.equity_curve[i - 1]) / metrics_.equity_curve[i - 1];
        returns.push_back(ret);
    }
    metrics_.sharpe_ratio = calculateSharpeRatio(returns);

    // Calculate max drawdown
    metrics_.max_drawdown = calculateMaxDrawdown(metrics_.equity_curve);
    if (initial_equity > 0) {
        double peak = *std::max_element(metrics_.equity_curve.begin(), metrics_.equity_curve.end());
        metrics_.max_drawdown_pct = (metrics_.max_drawdown / peak) * 100.0;
    }

    spdlog::info("[BacktestEngine] Metrics calculated");
}

double BacktestEngine::calculateSharpeRatio(const std::vector<double>& returns) {
    if (returns.empty())
        return 0.0;

    double mean_return = 0.0;
    for (double r : returns) {
        mean_return += r;
    }
    mean_return /= returns.size();

    double variance = 0.0;
    for (double r : returns) {
        double diff = r - mean_return;
        variance += diff * diff;
    }
    variance /= returns.size();

    double std_dev = std::sqrt(variance);

    if (std_dev < 1e-10)
        return 0.0;

    // Annualize (252 trading days/year)
    double sharpe = (mean_return / std_dev) * std::sqrt(252);

    return sharpe;
}

double BacktestEngine::calculateMaxDrawdown(const std::vector<double>& equity) {
    if (equity.empty())
        return 0.0;

    double max_dd = 0.0;
    double peak = equity[0];

    for (double value : equity) {
        if (value > peak) {
            peak = value;
        }

        double drawdown = peak - value;
        max_dd = std::max(max_dd, drawdown);
    }

    return max_dd;
}
