#include <string>

class Device {
public:
    Device(const std::string& backend);
    ~Device();

    // std::shared_ptr<SwapChain> createSwapChain(void* windowHandle, uint32_t width, uint32_t height);
    // std::shared_ptr<Buffer> createBuffer(const BufferDesc& desc);
    // std::shared_ptr<CommandBuffer> createCommandBuffer();
    // void submit(const CommandBuffer& cmd);

private:
    //nri::Device* m_device = nullptr;
    // plus queues, allocator, etc.
};