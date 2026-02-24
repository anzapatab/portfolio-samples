// Extract from HFT Quant Engine
// Lock-free single-producer single-consumer (SPSC) ring buffer.
// Cache-line aligned head/tail for zero false-sharing between threads.
// Used for zero-copy data flow between market data and feature engine.

#pragma once
#include <atomic>
#include <cstddef>
#include <vector>

namespace bqe {

template <typename T>
class SpscRing {
public:
    explicit SpscRing(size_t capacity_pow2) : mask_(capacity_pow2 - 1), buf_(capacity_pow2) {}

    bool push(const T& v) {
        auto head = head_.load(std::memory_order_relaxed);
        auto next = (head + 1) & mask_;
        if (next == tail_.load(std::memory_order_acquire))
            return false;  // full
        buf_[head] = v;
        head_.store(next, std::memory_order_release);
        return true;
    }

    bool pop(T& out) {
        auto tail = tail_.load(std::memory_order_relaxed);
        if (tail == head_.load(std::memory_order_acquire))
            return false;  // empty
        out = buf_[tail];
        tail_.store((tail + 1) & mask_, std::memory_order_release);
        return true;
    }

    bool empty() const {
        return tail_.load(std::memory_order_acquire) == head_.load(std::memory_order_acquire);
    }

private:
    const size_t mask_;
    std::vector<T> buf_;
    alignas(64) std::atomic<size_t> head_{0};
    alignas(64) std::atomic<size_t> tail_{0};
};

}  // namespace bqe
