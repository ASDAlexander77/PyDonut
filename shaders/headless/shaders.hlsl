Buffer<uint> t_Input : register(t0);
RWBuffer<uint> u_Output : register(u0);

static const uint GroupSize = 256;

groupshared uint s_ReductionData[GroupSize/2];

[numthreads(GroupSize, 1, 1)]
void main(uint threadIdx : SV_GroupThreadID)
{
    uint data = t_Input[threadIdx];

    // Simple parallel reduction implementation.
    // Process the data using groups of threads of reducing size.
    // Note: there is a faster way of doing group-wide reduction using wave intrinsics.
    for (uint size = GroupSize/2; size >= 1; size >>= 1)
    {
        // Upper half of the current group stores its data into the shared buffer
        if (size <= threadIdx && threadIdx < size * 2)
            s_ReductionData[threadIdx - size] = data;

        GroupMemoryBarrierWithGroupSync();

        // Lower half of the current group loads the data from the shared buffer and adds it to the accumulator
        if (threadIdx < size)
            data += s_ReductionData[threadIdx];

        GroupMemoryBarrierWithGroupSync();

        // Repeat with a smaller group...
    }

    if (threadIdx == 0)
        u_Output[0] = data;
}
