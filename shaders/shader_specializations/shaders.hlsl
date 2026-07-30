[[vk::constant_id(0)]] const float c_offset = 0;
[[vk::constant_id(1)]] const uint c_color = 0xffffff;

static const float2 g_positions[] = {
	float2(-0.5, -0.5),
	float2(0, 0.5),
	float2(0.5, -0.5)
};

static const float3 g_colors[] = {
	float3(1, 0, 0),
	float3(0, 1, 0),
	float3(0, 0, 1)
};

void main_vs(
	uint i_vertexId : SV_VertexID,
	out float4 o_pos : SV_Position,
	out float3 o_color : COLOR
)
{
	o_pos = float4(g_positions[i_vertexId], 0, 1);
	o_pos.x = o_pos.x * 0.5 + c_offset;
	o_color = g_colors[i_vertexId];
}

void main_ps(
	in float4 i_pos : SV_Position,
	in float3 i_color : COLOR,
	out float4 o_color : SV_Target0
)
{
	o_color.r = float(c_color & 0xff) / 0xff;
	o_color.g = float((c_color >> 8) & 0xff) / 0xff;
	o_color.b = float((c_color >> 16) & 0xff) / 0xff;
	o_color.a = 1;
}
