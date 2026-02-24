// Extract from HFT Quant Engine
// ONNX Runtime inference engine interface for sub-millisecond ML prediction.

#pragma once

#include <memory>
#include <string>
#include <vector>

// ONNX Runtime C++ API
#include <onnxruntime_cxx_api.h>

namespace bqe {

class InferenceEngine {
public:
    /**
     * @brief Constructs an InferenceEngine and loads a model.
     * @param model_path Path to the .onnx model file.
     * @param use_gpu Whether to attempt to use a GPU provider.
     * @param gpu_device_id The ID of the GPU to use.
     */
    explicit InferenceEngine(const std::string& model_path, bool use_gpu = false, int gpu_device_id = 0);
    ~InferenceEngine();

    // Deleted copy and move constructors to prevent accidental copies
    InferenceEngine(const InferenceEngine&) = delete;
    InferenceEngine& operator=(const InferenceEngine&) = delete;
    InferenceEngine(InferenceEngine&&) = delete;
    InferenceEngine& operator=(InferenceEngine&&) = delete;

    /**
     * @brief Runs inference on the provided input data.
     * @param input_tensor_values A vector of floats representing the input tensor.
     * @param input_tensor_shape The shape of the input tensor.
     * @return A vector of floats representing the output of the model.
     */
    std::vector<float> run(const std::vector<float>& input_tensor_values,
                           const std::vector<int64_t>& input_tensor_shape);

private:
    Ort::Env env_;
    Ort::SessionOptions session_options_;
    std::unique_ptr<Ort::Session> session_;

    std::vector<const char*> input_node_names_;
    std::vector<const char*> output_node_names_;

    // Storage to keep string data alive if needed
    std::vector<std::string> input_name_storage_;
    std::vector<std::string> output_name_storage_;

    std::vector<std::vector<int64_t>> input_node_dims_;
    std::vector<std::vector<int64_t>> output_node_dims_;
};

}  // namespace bqe
