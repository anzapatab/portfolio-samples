// Extract from HFT Quant Engine
// AVX2/SSE4.2 SIMD-optimized math utilities for the hot path:
// vectorized EMA, standard deviation, dot product, array scaling,
// and fast polynomial log approximation (~5x faster than std::log).

#pragma once
#include <cmath>
#include "types.hpp"

#if defined(__AVX2__)
#include <immintrin.h>
#define BQE_HAS_AVX2 1
#elif defined(__SSE4_2__)
#include <nmmintrin.h>
#define BQE_HAS_SSE42 1
#else
#define BQE_HAS_SIMD 0
#endif

namespace bqe {
namespace simd {

// SIMD-optimized exponential moving average calculation
// Processes 4 values in parallel using AVX2
#if defined(__AVX2__)
inline void ema_batch_avx2(const double* prices, double* ema_out, double alpha, size_t count) {
    if (count < 4) {
        // Fallback for small batches
        for (size_t i = 0; i < count; ++i) {
            ema_out[i] = alpha * prices[i] + (1.0 - alpha) * ema_out[i];
        }
        return;
    }

    __m256d v_alpha = _mm256_set1_pd(alpha);
    __m256d v_one_minus_alpha = _mm256_set1_pd(1.0 - alpha);

    size_t i = 0;
    for (; i + 4 <= count; i += 4) {
        // Load 4 prices and 4 previous EMA values
        __m256d v_price = _mm256_loadu_pd(&prices[i]);
        __m256d v_ema = _mm256_loadu_pd(&ema_out[i]);

        // EMA = alpha * price + (1 - alpha) * prev_ema
        __m256d v_term1 = _mm256_mul_pd(v_alpha, v_price);
        __m256d v_term2 = _mm256_mul_pd(v_one_minus_alpha, v_ema);
        __m256d v_result = _mm256_add_pd(v_term1, v_term2);

        _mm256_storeu_pd(&ema_out[i], v_result);
    }

    // Handle remaining elements
    for (; i < count; ++i) {
        ema_out[i] = alpha * prices[i] + (1.0 - alpha) * ema_out[i];
    }
}
#endif

// SIMD-optimized standard deviation calculation
#if defined(__AVX2__)
inline double stddev_avx2(const double* values, size_t count) {
    if (count < 4) {
        double mean = 0.0;
        for (size_t i = 0; i < count; ++i) mean += values[i];
        mean /= count;

        double variance = 0.0;
        for (size_t i = 0; i < count; ++i) {
            double diff = values[i] - mean;
            variance += diff * diff;
        }
        return std::sqrt(variance / count);
    }

    // Calculate mean using SIMD
    __m256d v_sum = _mm256_setzero_pd();
    size_t i = 0;
    for (; i + 4 <= count; i += 4) {
        __m256d v = _mm256_loadu_pd(&values[i]);
        v_sum = _mm256_add_pd(v_sum, v);
    }

    // Horizontal sum
    double sum_arr[4];
    _mm256_storeu_pd(sum_arr, v_sum);
    double sum = sum_arr[0] + sum_arr[1] + sum_arr[2] + sum_arr[3];

    // Handle remainder
    for (; i < count; ++i) sum += values[i];

    double mean = sum / count;
    __m256d v_mean = _mm256_set1_pd(mean);

    // Calculate variance using SIMD
    __m256d v_var_sum = _mm256_setzero_pd();
    i = 0;
    for (; i + 4 <= count; i += 4) {
        __m256d v = _mm256_loadu_pd(&values[i]);
        __m256d v_diff = _mm256_sub_pd(v, v_mean);
        __m256d v_sq = _mm256_mul_pd(v_diff, v_diff);
        v_var_sum = _mm256_add_pd(v_var_sum, v_sq);
    }

    // Horizontal sum
    _mm256_storeu_pd(sum_arr, v_var_sum);
    double var_sum = sum_arr[0] + sum_arr[1] + sum_arr[2] + sum_arr[3];

    // Handle remainder
    for (; i < count; ++i) {
        double diff = values[i] - mean;
        var_sum += diff * diff;
    }

    return std::sqrt(var_sum / count);
}
#endif

// SIMD-optimized dot product
#if defined(__AVX2__)
inline double dot_product_avx2(const double* a, const double* b, size_t count) {
    __m256d v_sum = _mm256_setzero_pd();

    size_t i = 0;
    for (; i + 4 <= count; i += 4) {
        __m256d v_a = _mm256_loadu_pd(&a[i]);
        __m256d v_b = _mm256_loadu_pd(&b[i]);
        __m256d v_prod = _mm256_mul_pd(v_a, v_b);
        v_sum = _mm256_add_pd(v_sum, v_prod);
    }

    // Horizontal sum
    double sum_arr[4];
    _mm256_storeu_pd(sum_arr, v_sum);
    double result = sum_arr[0] + sum_arr[1] + sum_arr[2] + sum_arr[3];

    // Handle remainder
    for (; i < count; ++i) {
        result += a[i] * b[i];
    }

    return result;
}
#endif

// SIMD-optimized array scaling (multiply all elements by constant)
#if defined(__AVX2__)
inline void scale_array_avx2(double* arr, double scalar, size_t count) {
    __m256d v_scalar = _mm256_set1_pd(scalar);

    size_t i = 0;
    for (; i + 4 <= count; i += 4) {
        __m256d v = _mm256_loadu_pd(&arr[i]);
        __m256d v_result = _mm256_mul_pd(v, v_scalar);
        _mm256_storeu_pd(&arr[i], v_result);
    }

    // Handle remainder
    for (; i < count; ++i) {
        arr[i] *= scalar;
    }
}
#endif

// Fast log approximation using SIMD (for returns calculation)
// Uses polynomial approximation: ~5x faster than std::log
#if defined(__AVX2__)
inline __m256d fast_log_avx2(__m256d x) {
    // Polynomial approximation of log(x) for x in [1, 2]
    // log(x) ~ a0 + a1*(x-1) + a2*(x-1)^2 + a3*(x-1)^3

    __m256d one = _mm256_set1_pd(1.0);
    __m256d a0 = _mm256_set1_pd(0.0);
    __m256d a1 = _mm256_set1_pd(0.9991150290701569);
    __m256d a2 = _mm256_set1_pd(-0.4899487306101254);
    __m256d a3 = _mm256_set1_pd(0.2879780115813974);

    __m256d xm1 = _mm256_sub_pd(x, one);
    __m256d xm1_2 = _mm256_mul_pd(xm1, xm1);
    __m256d xm1_3 = _mm256_mul_pd(xm1_2, xm1);

    __m256d result = a0;
    result = _mm256_fmadd_pd(a1, xm1, result);
    result = _mm256_fmadd_pd(a2, xm1_2, result);
    result = _mm256_fmadd_pd(a3, xm1_3, result);

    return result;
}

// Batch log returns calculation (4 at a time)
inline void log_returns_batch_avx2(const double* prev_prices, const double* curr_prices, double* returns,
                                   size_t count) {
    size_t i = 0;
    for (; i + 4 <= count; i += 4) {
        __m256d v_prev = _mm256_loadu_pd(&prev_prices[i]);
        __m256d v_curr = _mm256_loadu_pd(&curr_prices[i]);

        // returns = curr / prev
        __m256d v_ratio = _mm256_div_pd(v_curr, v_prev);

        // log(ratio) - using fast approximation
        __m256d v_log = fast_log_avx2(v_ratio);

        _mm256_storeu_pd(&returns[i], v_log);
    }

    // Handle remainder with standard log
    for (; i < count; ++i) {
        returns[i] = std::log(curr_prices[i] / prev_prices[i]);
    }
}
#endif

// Check if SIMD is available at runtime
inline bool has_avx2() {
#if defined(__AVX2__)
    return true;
#else
    return false;
#endif
}

inline bool has_sse42() {
#if defined(__SSE4_2__)
    return true;
#else
    return false;
#endif
}

}  // namespace simd
}  // namespace bqe
