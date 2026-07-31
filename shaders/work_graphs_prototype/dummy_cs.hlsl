RWStructuredBuffer<uint> u_Output : register(u0);

[numthreads(1, 1, 1)]
void CSDummy(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    u_Output[0] = 0;
}
