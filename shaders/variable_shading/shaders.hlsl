// Shading rate enum values copied from D3D12 header
/*
    {
        D3D12_SHADING_RATE_1X1	= 0,
        D3D12_SHADING_RATE_1X2	= 0x1,
        D3D12_SHADING_RATE_2X1	= 0x4,
        D3D12_SHADING_RATE_2X2	= 0x5,
        D3D12_SHADING_RATE_2X4	= 0x6,
        D3D12_SHADING_RATE_4X2	= 0x9,
        D3D12_SHADING_RATE_4X4	= 0xa
    } 	D3D12_SHADING_RATE;
*/
RWTexture2D<uint> shadingRateSurface : register(u0);
Texture2D<float2> motionVectors : register(t0);
Texture2D<float4> prevFrameColors : register(t1);

#define TILE_SIZE 16

[numthreads(1, 1, 1)]
void main_cs(uint3 DispatchThreadID : SV_DispatchThreadID)
{
    // This is a fairly nonsensical algorithm, reads the average color for the tile in the previous frame
    // and sets the shading rate to 4X4 if green channel is bigger than red channel, 1X1 otherwise
    // really just intended to make the VRS difference very noticeable to confirm that it is working
    float2 motionVector = motionVectors.Load(int3(TILE_SIZE * DispatchThreadID.xy, 0));
    uint2 oldTexel = uint2(float2(DispatchThreadID.xy * TILE_SIZE) + motionVector);
    float4 averageColor = 0;
    for (int i = 0; i < TILE_SIZE; i++)
    {
        for (int j = 0; j < TILE_SIZE; j++)
        {
            averageColor += prevFrameColors.Load(int3(oldTexel + uint2(i, j), 0));
        }
    }
    averageColor /= (TILE_SIZE * TILE_SIZE);
    if (averageColor.g > averageColor.r)
    {
        shadingRateSurface[DispatchThreadID.xy] = 0xa;
    }
    else
    {
        shadingRateSurface[DispatchThreadID.xy] = 0x0;
    }
}
