RWBuffer<uint> u_Output : register(u0);

[Shader("node")]
[NodeLaunch("broadcasting")]
[NodeIsProgramEntry]
[NodeDispatchGrid(1, 1, 1)]
[numthreads(1, 1, 1)]
void WriteConstant_Node(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    u_Output[0] = 0xC0FFEE;
}
