#pragma pack_matrix(row_major)

#include <donut/shaders/gbuffer.hlsli>
#include <donut/shaders/lighting.hlsli>
#include "lighting_cb.h"

// ---[ Structures ]---

struct HitInfo
{
    bool missed;
};

// ---[ Resources ]---

ConstantBuffer<LightingConstants> g_Lighting : register(b0);

RWTexture2D<float4> u_Output : register(u0);

RaytracingAccelerationStructure SceneBVH : register(t0);
Texture2D t_GBufferDepth : register(t1);
Texture2D t_GBuffer0 : register(t2);
Texture2D t_GBuffer1 : register(t3);
Texture2D t_GBuffer2 : register(t4);
Texture2D t_GBuffer3 : register(t5);


// ---[ Ray Generation Shader ]---

[shader("raygeneration")]
void RayGen()
{
    uint2 globalIdx = DispatchRaysIndex().xy;
    float2 pixelPosition = float2(globalIdx) + 0.5;

    MaterialSample surfaceMaterial = DecodeGBuffer(globalIdx, t_GBuffer0, t_GBuffer1, t_GBuffer2, t_GBuffer3);

    float3 surfaceWorldPos = ReconstructWorldPosition(g_Lighting.view, pixelPosition.xy, t_GBufferDepth[pixelPosition.xy].x);

    float3 viewIncident = GetIncidentVector(g_Lighting.view.cameraDirectionOrPosition, surfaceWorldPos);

    // Setup the ray
    RayDesc ray;
    ray.Origin = surfaceWorldPos;
    ray.Direction = -normalize(g_Lighting.light.direction);
    ray.TMin = 0.01f;
    ray.TMax = 100.f;

    // Trace the ray
    HitInfo payload;
    payload.missed = false;

    TraceRay(
        SceneBVH,
        RAY_FLAG_CULL_BACK_FACING_TRIANGLES,
        0xFF,
        0,
        0,
        0,
        ray,
        payload);

    float shadow = (payload.missed) ? 1 : 0;

    float3 diffuseTerm = 0;
    float3 specularTerm = 0;

    float3 diffuseRadiance, specularRadiance;
    ShadeSurface(g_Lighting.light, surfaceMaterial, surfaceWorldPos, viewIncident, diffuseRadiance, specularRadiance);

    diffuseTerm += (shadow * diffuseRadiance) * g_Lighting.light.color;
    specularTerm += (shadow * specularRadiance) * g_Lighting.light.color;

    diffuseTerm += g_Lighting.ambientColor.rgb * surfaceMaterial.diffuseAlbedo;

    float3 outputColor = diffuseTerm
        + specularTerm
        + surfaceMaterial.emissiveColor;

    u_Output[globalIdx] = float4(outputColor, 1);
}

// ---[ Miss Shader ]---

[shader("miss")]
void Miss(inout HitInfo payload : SV_RayPayload)
{
    payload.missed = true;
}
