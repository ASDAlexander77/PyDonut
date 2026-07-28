struct Payload
{
    uint dummy;
};

struct VertexOutput
{
    float4 position : SV_Position;
};

groupshared Payload s_payload;

[numthreads(1, 1, 1)]
void main_as(uint3 dispatchThreadID : SV_DispatchThreadID)
{
    s_payload.dummy = 0;

    DispatchMesh(1, 1, 1, s_payload);
}

[numthreads(1, 1, 1)]
[outputtopology("triangle")]
void main_ms(
    in payload Payload payload,
    out vertices VertexOutput verts[3],
    out indices uint3 tris[1])
{
    SetMeshOutputCounts(3, 1);

    verts[0].position = float4( 0.0f, -0.5f, 0.0f, 1.0f);
    verts[1].position = float4( 0.5f,  0.5f, 0.0f, 1.0f);
    verts[2].position = float4(-0.5f,  0.5f, 0.0f, 1.0f);

    tris[0] = uint3(0, 1, 2);
}

float4 main_ps(VertexOutput input) : SV_Target0
{
    return float4(1.0f, 1.0f, 1.0f, 1.0f);
}
