#ifndef LIGHTING_CB_H
#define LIGHTING_CB_H

#include <donut/shaders/light_cb.h>
#include <donut/shaders/view_cb.h>

struct LightingConstants
{
    float4 ambientColor;

    LightConstants light;
    PlanarViewConstants view;
};

#endif // LIGHTING_CB_H
