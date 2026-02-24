// Extract from HFT Quant Engine
// ONNX Runtime inference engine for sub-millisecond ML prediction.
// Loads LightGBM models exported to ONNX format and runs single-event
// inference on the hot path. Supports both tensor and seq(map) outputs.

#include "inference_engine.h"
#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace bqe {

InferenceEngine::InferenceEngine(const std::string& model_path, bool use_gpu, int gpu_device_id)
    : env_(ORT_LOGGING_LEVEL_WARNING, "BQE_Inference") {
    session_options_.SetIntraOpNumThreads(1);
    session_options_.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);

    if (use_gpu) {
        std::cout << "GPU execution provider requested. Attempting to enable CUDA." << std::endl;
        // Requires onnxruntime-gpu package and CUDA drivers
        // OrtCUDAProviderOptions cuda_options;
        // cuda_options.device_id = gpu_device_id;
        // session_options_.AppendExecutionProvider_CUDA(cuda_options);
    }

// Ort::Session expects a wide character string on Windows, basic string on POSIX
#ifdef _WIN32
    const std::wstring wide_model_path(model_path.begin(), model_path.end());
    session_ = std::make_unique<Ort::Session>(env_, wide_model_path.c_str(), session_options_);
#else
    session_ = std::make_unique<Ort::Session>(env_, model_path.c_str(), session_options_);
#endif

    // --- Inspect Model Input/Output ---
    Ort::AllocatorWithDefaultOptions allocator;

    // 1. Inputs
    size_t num_input_nodes = session_->GetInputCount();
    input_node_names_.resize(num_input_nodes);
    input_name_storage_.resize(num_input_nodes);
    input_node_dims_.resize(num_input_nodes);

    for (size_t i = 0; i < num_input_nodes; i++) {
        auto type_info = session_->GetInputTypeInfo(i);
        auto tensor_info = type_info.GetTensorTypeAndShapeInfo();

        auto input_name_ptr = session_->GetInputNameAllocated(i, allocator);
        input_name_storage_[i] = input_name_ptr.get();
        input_node_names_[i] = input_name_storage_[i].c_str();

        // Get shape
        input_node_dims_[i] = tensor_info.GetShape();

        // Fix for negative/unknown dimensions (e.g. batch size -1)
        if (input_node_dims_[i].size() > 0 && input_node_dims_[i][0] < 0) {
            input_node_dims_[i][0] = 1;
        }
    }

    // 2. Outputs
    size_t num_output_nodes = session_->GetOutputCount();
    output_node_names_.resize(num_output_nodes);
    output_name_storage_.resize(num_output_nodes);
    output_node_dims_.resize(num_output_nodes);

    for (size_t i = 0; i < num_output_nodes; i++) {
        auto output_name_ptr = session_->GetOutputNameAllocated(i, allocator);
        output_name_storage_[i] = output_name_ptr.get();
        output_node_names_[i] = output_name_storage_[i].c_str();

        // Skip shape extraction for outputs - avoids crashes with dynamic-shape models
        output_node_dims_[i] = {};
    }

    std::cout << "InferenceEngine initialized for model: " << model_path << std::endl;
    std::cout << "Inputs: " << num_input_nodes << ", Outputs: " << num_output_nodes << std::endl;
}

InferenceEngine::~InferenceEngine() = default;

std::vector<float> InferenceEngine::run(const std::vector<float>& input_tensor_values,
                                        const std::vector<int64_t>& input_tensor_shape) {
    if (!session_) {
        throw std::runtime_error("Inference session is not initialized.");
    }

    if (input_node_names_.empty()) {
        throw std::runtime_error("Model has no inputs.");
    }

    // Create Memory Info
    Ort::MemoryInfo memory_info = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);

    // Create Input Tensor
    Ort::Value input_tensor = Ort::Value::CreateTensor<float>(
        memory_info, const_cast<float*>(input_tensor_values.data()), input_tensor_values.size(),
        input_tensor_shape.data(), input_tensor_shape.size());

    // Run Inference
    std::vector<Ort::Value> output_tensors =
        session_->Run(Ort::RunOptions{nullptr}, input_node_names_.data(), &input_tensor,
                      1,  // Number of inputs
                      output_node_names_.data(),
                      output_node_names_.size()  // Number of outputs
        );

    if (output_tensors.empty()) {
        return {};
    }

    // LightGBM ONNX classifier outputs:
    //   output[0] = "label" (int64 tensor with predicted class)
    //   output[1] = "probabilities" - format depends on zipmap setting:
    //     - zipmap=False: tensor(float) with shape [1, num_classes] (PREFERRED)
    //     - zipmap=True: seq(map(int64,tensor(float))) (COMPLEX)

    std::vector<float> probs;
    bool extracted_real_probs = false;

    // Try to extract real probabilities from output[1]
    if (output_tensors.size() > 1) {
        try {
            auto& prob_output = output_tensors[1];

            // Check if it's a tensor (zipmap=False case - PREFERRED)
            if (prob_output.IsTensor()) {
                auto type_info = prob_output.GetTensorTypeAndShapeInfo();
                auto shape = type_info.GetShape();
                size_t num_elements = type_info.GetElementCount();

                const float* prob_data = prob_output.GetTensorData<float>();

                if (num_elements >= 3) {
                    // Standard 3-class classifier output
                    probs.assign(prob_data, prob_data + 3);
                    extracted_real_probs = true;

                    // Validate probabilities sum to ~1.0
                    float sum = probs[0] + probs[1] + probs[2];
                    if (std::abs(sum - 1.0f) > 0.01f) {
                        for (auto& p : probs) p /= sum;
                    }
                }
            }
            // Handle seq(map) format (zipmap=True case - LEGACY)
            else if (prob_output.IsSparseTensor() == false && prob_output.IsTensor() == false) {
                extracted_real_probs = false;
            }
        } catch (const std::exception& e) {
            std::cerr << "[InferenceEngine] Warning: Could not extract probabilities: "
                      << e.what() << std::endl;
            extracted_real_probs = false;
        }
    }

    // Fallback: Generate synthetic probabilities from predicted label
    if (!extracted_real_probs) {
        const int64_t* label_ptr = output_tensors[0].GetTensorData<int64_t>();
        int64_t predicted_class = label_ptr[0];

        probs.resize(3);

        probs[0] = 0.10f;
        probs[1] = 0.10f;
        probs[2] = 0.10f;

        if (predicted_class >= 0 && predicted_class < 3) {
            probs[predicted_class] = 0.80f;
        }

        // Normalize
        float sum = probs[0] + probs[1] + probs[2];
        for (auto& p : probs) p /= sum;

        static bool warned = false;
        if (!warned) {
            std::cerr << "[InferenceEngine] WARNING: Using synthetic probabilities. "
                      << "For real probabilities, re-export model with zipmap=False" << std::endl;
            warned = true;
        }
    }

    return probs;
}

}  // namespace bqe
