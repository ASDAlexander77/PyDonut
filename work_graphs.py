if __name__ == "__main__":
    import math
    import random
    import struct
    import sys
    from pathlib import Path

    from src import pydonut as pyd

    folder = Path(__file__).resolve().parent

    # ImGuiWindowFlags_AlwaysAutoResize -- same constant rt_particles.py already defines for
    # the same purpose.
    _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE = 64

    # MeshType
    MESH_PLANE = 0
    MESH_BOX = 1
    MESH_SPHERE = 2
    MESH_COUNT = 3

    # MaterialType
    BT_LAMBERT = 0
    BT_PHONG = 1
    BT_METALLIC = 2
    BT_VELVET = 3
    BT_FLAKES = 4
    BT_FACETED = 5
    BT_STAN = 6
    BT_CHECKER = 7

    # AnimType
    AT_STATIC = 0
    AT_ROTATEY = 1
    AT_DANCE = 2

    MATERIAL_STRIDE = 36   # 3f baseColor, u32 materialType, 3f param1, f param2, f param3
    INSTANCE_STRIDE = 40   # 3f position, f rotationY, 3f size, u32 meshType, u32 material, u32 animType
    LIGHT_STRIDE = 56      # 3f position, 3f target, 3f targetOffset, 3f color, f innerAngle, f outerAngle
    # u32 state, u32 stateRepeats, f statePeriod, f timeInState, 3f scale, f rotationY, f offsetY, f twist
    # -- matches sizeof(Scene::AnimState) in scene.h exactly (no straddling-vector padding: the
    # float3 scale starts at byte 16, already 16-byte aligned, so nothing is inserted before it).
    ANIM_STATE_STRIDE = 40

    # Scene generation constants, matching scene.cpp exactly.
    SceneParam_MaterialCountOfEachType = 10
    SceneParam_Floors = 3
    SceneParam_FloorToCeilingHeight = 70.0
    SceneParam_FloorSize = 500.0
    SceneParam_ObjectRoomSize = 50.0
    SceneParam_BallRoomSize = 120.0
    SceneParam_BallSize = 15.0
    SceneParam_LightsPerBall = 3
    SceneParam_BoxSubdivisions = 100
    SceneParam_SphereSides = 100
    SceneParam_SphereSlices = 50
    SceneParam_GroundColor = (0.5, 0.5, 0.5)
    SceneParam_PhongSpecularColorScale = 0.05
    SceneParam_PhongSpecularPowerMin = 15.0
    SceneParam_PhongSpecularPowerRange = 25.0
    SceneParam_VelvetRoughnessMin = 0.45
    SceneParam_VelvetRoughnessRange = 0.1
    SceneParam_FlakesSpecularColorScale = 0.05
    SceneParam_FlakesSpecularPowerMin = 15.0
    SceneParam_FlakesSpecularPowerRange = 25.0
    SceneParam_FlakesGranularityMin = 0.3
    SceneParam_FlakesGranularityRange = 0.1
    SceneParam_StanLineThicknessMin = 0.2
    SceneParam_StanLineThicknessRange = 0.4
    SceneParam_StanLineSpacingMin = 1.0
    SceneParam_StanLineSpacingRange = 3.0
    SceneParam_CheckersSize = 4.0
    SceneParam_CheckersSpecularPowerMin = 15.0
    SceneParam_CheckersSpecularPowerRange = 25.0

    def GeneratePlaneInternal(y: float, sign: float, positions: list, normals: list, indices: list) -> None:
        baseVtx = len(positions)
        positions.extend([
            (-0.5 * sign, y, -0.5),
            (-0.5 * sign, y, 0.5),
            (0.5 * sign, y, 0.5),
            (0.5 * sign, y, -0.5),
        ])
        normals.extend([(0.0, sign, 0.0)] * 4)
        indices.extend([baseVtx + 0, baseVtx + 1, baseVtx + 2, baseVtx + 2, baseVtx + 3, baseVtx + 0])

    def GeneratePlane() -> tuple:
        positions, normals, indices = [], [], []
        GeneratePlaneInternal(0.0, 1.0, positions, normals, indices)
        GeneratePlaneInternal(0.0, -1.0, positions, normals, indices)
        return positions, normals, indices

    def GenerateBox(faceSubdivisions: int) -> tuple:
        positions, normals, indices = [], [], []

        def GenerateSide(coord0: int, coord1: int, posInit: tuple, nrm: tuple, sign: float) -> None:
            baseVtx = len(positions)
            pos = list(posInit)
            for y in range(faceSubdivisions + 1):
                pos[coord1] = y / faceSubdivisions - 0.5
                for x in range(faceSubdivisions + 1):
                    pos[coord0] = (x / faceSubdivisions - 0.5) * sign
                    positions.append((pos[0], pos[1], pos[2]))
                    normals.append(nrm)
            for y in range(faceSubdivisions):
                for x in range(faceSubdivisions):
                    faceBaseVtx = baseVtx + y * (faceSubdivisions + 1) + x
                    indices.append(faceBaseVtx + 0)
                    indices.append(faceBaseVtx + (faceSubdivisions + 1) + 0)
                    indices.append(faceBaseVtx + (faceSubdivisions + 1) + 1)
                    indices.append(faceBaseVtx + (faceSubdivisions + 1) + 1)
                    indices.append(faceBaseVtx + 1)
                    indices.append(faceBaseVtx + 0)

        GenerateSide(0, 1, (0.0, 0.0, -0.5), (0.0, 0.0, -1.0), 1.0)   # Front
        GenerateSide(2, 1, (0.5, 0.0, 0.0), (1.0, 0.0, 0.0), 1.0)     # Right
        GenerateSide(0, 1, (0.0, 0.0, 0.5), (0.0, 0.0, 1.0), -1.0)    # Back
        GenerateSide(2, 1, (-0.5, 0.0, 0.0), (-1.0, 0.0, 0.0), -1.0)  # Left
        GeneratePlaneInternal(0.5, 1.0, positions, normals, indices)   # Top
        GeneratePlaneInternal(-0.5, -1.0, positions, normals, indices) # Bottom
        return positions, normals, indices

    def GenerateSphere(sides: int, slices: int) -> tuple:
        positions, normals, indices = [], [], []
        baseVtx = len(positions)

        positions.append((0.0, -0.5, 0.0))
        normals.append((0.0, -1.0, 0.0))
        for y in range(1, slices):
            py = y / slices - 0.5
            ringRadius = math.sqrt(max(0.0, 1.0 - py * py * 4.0)) * 0.5
            for x in range(sides):
                angle = (x / sides) * math.pi * 2.0
                px = math.cos(angle) * ringRadius
                pz = math.sin(angle) * ringRadius
                positions.append((px, py, pz))
                length = math.sqrt(px * px + py * py + pz * pz) or 1.0
                normals.append((px / length, py / length, pz / length))

        capVtx = len(positions)
        positions.append((0.0, 0.5, 0.0))
        normals.append((0.0, 1.0, 0.0))

        for i in range(sides):
            indices.append(baseVtx + 0)
            indices.append(baseVtx + 1 + i)
            indices.append(baseVtx + 1 + (i + 1) % sides)

        for y in range(slices - 2):
            sliceBaseVtx = baseVtx + 1 + y * sides
            for x in range(sides):
                indices.append(sliceBaseVtx + x + 0)
                indices.append(sliceBaseVtx + x + 0 + sides)
                indices.append(sliceBaseVtx + (x + 1) % sides + sides)
                indices.append(sliceBaseVtx + (x + 1) % sides + sides)
                indices.append(sliceBaseVtx + (x + 1) % sides)
                indices.append(sliceBaseVtx + x + 0)

        capBaseVtx = baseVtx + 1 + (slices - 2) * sides
        for i in range(sides):
            indices.append(capBaseVtx + i)
            indices.append(capVtx)
            indices.append(capBaseVtx + (i + 1) % sides)

        return positions, normals, indices

    class Scene:
        def __init__(self) -> None:
            self.materials: list[dict] = []
            self.instances: list[dict] = []
            self.lights: list[dict] = []
            self._vertex_buffers: list = [None] * MESH_COUNT
            self._index_buffers: list = [None] * MESH_COUNT
            self._index_counts: list = [0] * MESH_COUNT
            self._materials_buffer: pyd.Buffer | None = None
            self._instances_buffer: pyd.Buffer | None  = None
            self._lights_buffer: pyd.Buffer | None  = None
            self._anim_state_buffer: pyd.Buffer | None  = None

        def GetSceneSize(self) -> float:
            return SceneParam_FloorSize

        def GetSceneHeight(self) -> float:
            return SceneParam_FloorToCeilingHeight * SceneParam_Floors

        def GetMaterialsBuffer(self) -> pyd.Buffer:
            assert self._materials_buffer is not None
            return self._materials_buffer

        def GetWorldObjectsBuffer(self) -> pyd.Buffer:
            assert self._instances_buffer is not None
            return self._instances_buffer

        def GetLightsBuffer(self) -> pyd.Buffer:
            assert self._lights_buffer is not None
            return self._lights_buffer

        def GetAnimStateBuffer(self) -> pyd.Buffer:
            assert self._anim_state_buffer is not None
            return self._anim_state_buffer

        def GetMeshVertexBuffer(self, meshType: int):
            return self._vertex_buffers[meshType]

        def GetMeshIndexBuffer(self, meshType: int):
            return self._index_buffers[meshType]

        def GetIndexCount(self, meshType: int) -> int:
            return self._index_counts[meshType]

        def _populate_world(self, rnd: random.Random) -> None:
            def random_color(normalized: bool) -> tuple:
                c = (rnd.random(), rnd.random(), rnd.random())
                if not normalized:
                    return c
                length = math.sqrt(c[0] * c[0] + c[1] * c[1] + c[2] * c[2]) or 1.0
                return (c[0] / length, c[1] / length, c[2] / length)

            def random01() -> float:
                return rnd.random()

            def random_angle() -> float:
                return rnd.random() * math.pi * 2.0

            def random_pos_xz(extentsX: float, y: float, extentsZ: float) -> tuple:
                return ((rnd.random() - 0.5) * extentsX * 2.0, y, (rnd.random() - 0.5) * extentsZ * 2.0)

            def random_size(height: float, size: float, heightVariation: float, sizeVariation: float) -> tuple:
                return (
                    size + (rnd.random() - 0.5) * sizeVariation,
                    height + (rnd.random() - 0.5) * heightVariation,
                    size + (rnd.random() - 0.5) * sizeVariation,
                )

            # Materials 0 and 1 are hard-coded (ground Lambert, Faceted).
            self.materials.append({"baseColor": SceneParam_GroundColor, "materialType": BT_LAMBERT, "param1": (0, 0, 0), "param2": 0.0, "param3": 0.0})
            self.materials.append({"baseColor": (1.0, 1.0, 1.0), "materialType": BT_FACETED, "param1": (0, 0, 0), "param2": 0.0, "param3": 0.0})

            for _ in range(SceneParam_MaterialCountOfEachType):
                self.materials.append({"baseColor": random_color(True), "materialType": BT_LAMBERT, "param1": (0, 0, 0), "param2": 0.0, "param3": 0.0})

            for _ in range(SceneParam_MaterialCountOfEachType):
                specColor = tuple(c * SceneParam_PhongSpecularColorScale for c in random_color(True))
                specPower = random01() * SceneParam_PhongSpecularPowerRange + SceneParam_PhongSpecularPowerMin
                self.materials.append({"baseColor": random_color(True), "materialType": BT_PHONG, "param1": specColor, "param2": specPower, "param3": 0.0})

            for _ in range(SceneParam_MaterialCountOfEachType):
                self.materials.append({"baseColor": random_color(True), "materialType": BT_METALLIC, "param1": (0, 0, 0), "param2": 0.0, "param3": 0.0})

            for _ in range(SceneParam_MaterialCountOfEachType):
                roughness = random01() * SceneParam_VelvetRoughnessRange + SceneParam_VelvetRoughnessMin
                self.materials.append({"baseColor": random_color(True), "materialType": BT_VELVET, "param1": (roughness, 0, 0), "param2": 0.0, "param3": 0.0})

            for _ in range(SceneParam_MaterialCountOfEachType):
                specColor = tuple(c * SceneParam_FlakesSpecularColorScale for c in random_color(True))
                specPower = random01() * SceneParam_FlakesSpecularPowerRange + SceneParam_FlakesSpecularPowerMin
                granularity = random01() * SceneParam_FlakesGranularityRange + SceneParam_FlakesGranularityMin
                self.materials.append({"baseColor": random_color(True), "materialType": BT_FLAKES, "param1": specColor, "param2": specPower, "param3": granularity})

            for _ in range(SceneParam_MaterialCountOfEachType):
                linesColor = random_color(False)
                linesThickness = random01() * SceneParam_StanLineThicknessRange + SceneParam_StanLineThicknessMin
                linesSpacing = random01() * SceneParam_StanLineSpacingRange + SceneParam_StanLineSpacingMin
                self.materials.append({"baseColor": random_color(True), "materialType": BT_STAN, "param1": linesColor, "param2": linesThickness, "param3": linesSpacing})

            for _ in range(SceneParam_MaterialCountOfEachType):
                baseColor2 = random_color(False)
                specPower = random01() * SceneParam_CheckersSpecularPowerRange + SceneParam_CheckersSpecularPowerMin
                self.materials.append({"baseColor": random_color(True), "materialType": BT_CHECKER, "param1": baseColor2, "param2": SceneParam_CheckersSize, "param3": specPower})

            for floor in range(SceneParam_Floors):
                floorHeight = floor * SceneParam_FloorToCeilingHeight
                ceilingHeight = (floor + 1) * SceneParam_FloorToCeilingHeight

                self.instances.append({"position": (0.0, floorHeight, 0.0), "rotationY": 0.0, "size": (SceneParam_FloorSize, 0.0, SceneParam_FloorSize), "meshType": MESH_PLANE, "material": 0, "animType": AT_STATIC})

                roomCount1D = int(SceneParam_FloorSize / SceneParam_BallRoomSize)
                ballHeight = ceilingHeight - SceneParam_BallSize * 0.5
                for roomX in range(roomCount1D):
                    for roomZ in range(roomCount1D):
                        roomCenterX = -SceneParam_FloorSize * 0.5 + roomX * SceneParam_BallRoomSize + SceneParam_BallRoomSize * 0.5
                        roomCenterZ = -SceneParam_FloorSize * 0.5 + roomZ * SceneParam_BallRoomSize + SceneParam_BallRoomSize * 0.5
                        bx, by, bz = random_pos_xz((SceneParam_BallRoomSize - SceneParam_BallSize) * 0.3, ballHeight, (SceneParam_BallRoomSize - SceneParam_BallSize) * 0.3)
                        ballPos = (bx + roomCenterX, by, bz + roomCenterZ)
                        self.instances.append({"position": ballPos, "rotationY": random_angle(), "size": (SceneParam_BallSize,) * 3, "meshType": MESH_SPHERE, "material": 1, "animType": AT_ROTATEY})

                        for _ in range(SceneParam_LightsPerBall):
                            dx, dy, dz = random_size(-1.0, 0.0, 0.8, 2.0)
                            dlen = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
                            dx, dy, dz = dx / dlen, dy / dlen, dz / dlen
                            length = random01() * SceneParam_FloorSize * 0.35 + SceneParam_FloorToCeilingHeight
                            tgt = (dx * length + ballPos[0], dy * length + ballPos[1], dz * length + ballPos[2])
                            angle1 = random_angle() * 0.25 + 0.25
                            angle2 = random_angle() * 0.25 + 0.25
                            innerAngle = min(angle1, angle2)
                            outerAngle = max(angle1, angle2) + random_angle() * 0.1
                            self.lights.append({"position": ballPos, "target": tgt, "targetOffset": (0.0, 0.0, 0.0), "color": random_color(True), "innerAngle": innerAngle, "outerAngle": outerAngle})

                roomCount1D = int(SceneParam_FloorSize / SceneParam_ObjectRoomSize)
                for roomX in range(roomCount1D):
                    for roomZ in range(roomCount1D):
                        roomCenterX = -SceneParam_FloorSize * 0.5 + roomX * SceneParam_ObjectRoomSize + SceneParam_ObjectRoomSize * 0.5
                        roomCenterZ = -SceneParam_FloorSize * 0.5 + roomZ * SceneParam_ObjectRoomSize + SceneParam_ObjectRoomSize * 0.5
                        size = random_size(SceneParam_FloorToCeilingHeight * 0.35, SceneParam_ObjectRoomSize * 0.20, SceneParam_FloorToCeilingHeight * 0.1, SceneParam_ObjectRoomSize * 0.05)
                        px, py, pz = random_pos_xz((SceneParam_ObjectRoomSize - size[0]) * 0.5, floorHeight + size[1] * 0.5, (SceneParam_ObjectRoomSize - size[2]) * 0.5)
                        pos = (px + roomCenterX, py + 0.01, pz + roomCenterZ)
                        material = rnd.randrange(len(self.materials) - 2) + 2
                        self.instances.append({"position": pos, "rotationY": random_angle(), "size": size, "meshType": MESH_BOX, "material": material, "animType": AT_DANCE})

        def CreateAssets(self, device, commandList) -> None:
            rnd = random.Random(0)  # Deterministic layout, not bit-identical to the C++ srand(0) sequence.
            self._populate_world(rnd)

            mesh_generators = {
                MESH_PLANE: GeneratePlane(),
                MESH_BOX: GenerateBox(SceneParam_BoxSubdivisions),
                MESH_SPHERE: GenerateSphere(SceneParam_SphereSides, SceneParam_SphereSlices),
            }

            for meshType, (positions, normals, indices) in mesh_generators.items():
                vertexFloats = []
                for p, n in zip(positions, normals):
                    vertexFloats.extend(p)
                    vertexFloats.extend(n)
                vertexBytes = struct.pack(f"<{len(vertexFloats)}f", *vertexFloats)

                vbDesc = pyd.BufferDesc()
                vbDesc.byteSize = len(vertexBytes)
                vbDesc.isVertexBuffer = True
                vbDesc.initialState = pyd.ResourceStates.VertexBuffer
                vbDesc.keepInitialState = True
                vbDesc.debugName = f"MeshVB{meshType}"
                vb = device.createBuffer(vbDesc)
                commandList.writeBuffer(vb, vertexBytes)
                self._vertex_buffers[meshType] = vb

                indexBytes = struct.pack(f"<{len(indices)}H", *indices)
                ibDesc = pyd.BufferDesc()
                ibDesc.byteSize = len(indexBytes)
                ibDesc.isIndexBuffer = True
                ibDesc.initialState = pyd.ResourceStates.IndexBuffer
                ibDesc.keepInitialState = True
                ibDesc.debugName = f"MeshIB{meshType}"
                ib = device.createBuffer(ibDesc)
                commandList.writeBuffer(ib, indexBytes)
                self._index_buffers[meshType] = ib
                self._index_counts[meshType] = len(indices)

            materialBytes = b"".join(
                struct.pack("<3fI3fff", *m["baseColor"], m["materialType"], *m["param1"], m["param2"], m["param3"])
                for m in self.materials
            )
            matDesc = pyd.BufferDesc()
            matDesc.byteSize = len(materialBytes)
            matDesc.canHaveTypedViews = True
            matDesc.structStride = MATERIAL_STRIDE
            matDesc.initialState = pyd.ResourceStates.ShaderResource
            matDesc.keepInitialState = True
            matDesc.debugName = "MaterialsData"
            self._materials_buffer = device.createBuffer(matDesc)
            commandList.writeBuffer(self._materials_buffer, materialBytes)

            instanceBytes = b"".join(
                struct.pack("<3ff3fIII", *i["position"], i["rotationY"], *i["size"], i["meshType"], i["material"], i["animType"])
                for i in self.instances
            )
            instDesc = pyd.BufferDesc()
            instDesc.byteSize = len(instanceBytes)
            instDesc.canHaveTypedViews = True
            instDesc.structStride = INSTANCE_STRIDE
            instDesc.initialState = pyd.ResourceStates.ShaderResource
            instDesc.keepInitialState = True
            instDesc.debugName = "InstancesData"
            self._instances_buffer = device.createBuffer(instDesc)
            commandList.writeBuffer(self._instances_buffer, instanceBytes)

            lightBytes = b"".join(
                struct.pack("<3f3f3f3fff", *light["position"], *light["target"], *light["targetOffset"], *light["color"], light["innerAngle"], light["outerAngle"])
                for light in self.lights
            )
            lightDesc = pyd.BufferDesc()
            lightDesc.byteSize = len(lightBytes)
            lightDesc.canHaveUAVs = True
            lightDesc.canHaveTypedViews = True
            lightDesc.structStride = LIGHT_STRIDE
            lightDesc.initialState = pyd.ResourceStates.UnorderedAccess
            lightDesc.keepInitialState = True
            lightDesc.debugName = "LightsData"
            self._lights_buffer = device.createBuffer(lightDesc)
            commandList.writeBuffer(self._lights_buffer, lightBytes)

            animStateDesc = pyd.BufferDesc()
            animStateDesc.byteSize = ANIM_STATE_STRIDE * len(self.instances)
            animStateDesc.canHaveUAVs = True
            animStateDesc.canHaveTypedViews = True
            animStateDesc.structStride = ANIM_STATE_STRIDE
            animStateDesc.initialState = pyd.ResourceStates.UnorderedAccess
            animStateDesc.keepInitialState = True
            animStateDesc.debugName = "AnimState"
            self._anim_state_buffer = device.createBuffer(animStateDesc)  # No upload: matches Scene::CreateAssets, which never
            # writes initial contents -- the first animation dispatch (g_ResetState=1) initializes it on the GPU.

    def _scene_smoke_test() -> bool:
        api = pyd.GraphicsAPI.D3D12
        deviceManager = pyd.DeviceManager.Create(api)
        if not deviceManager:
            pyd.log.fatal("Failed to create DeviceManager.")
            return False
        deviceParams = pyd.DeviceCreationParameters()
        if not deviceManager.CreateHeadlessDevice(deviceParams):
            pyd.log.error("Cannot initialize a graphics device with the requested parameters")
            return False
        device = deviceManager.GetDevice()

        commandList = device.createCommandList()
        commandList.open()
        scene = Scene()
        scene.CreateAssets(device, commandList)
        commandList.close()
        device.executeCommandList(commandList)
        device.waitForIdle()

        expectedMaterialCount = 2 + 7 * SceneParam_MaterialCountOfEachType
        ok = (
            len(scene.materials) == expectedMaterialCount
            and scene.GetMaterialsBuffer() is not None
            and scene.GetWorldObjectsBuffer() is not None
            and scene.GetLightsBuffer() is not None
            and scene.GetAnimStateBuffer() is not None
            and all(scene.GetMeshVertexBuffer(mt) is not None for mt in (MESH_PLANE, MESH_BOX, MESH_SPHERE))
            and all(scene.GetMeshIndexBuffer(mt) is not None for mt in (MESH_PLANE, MESH_BOX, MESH_SPHERE))
            and scene.GetIndexCount(MESH_BOX) > 0
            and len(scene.instances) > 0
            and len(scene.lights) > 0
        )
        print(f"materials={len(scene.materials)} (expected {expectedMaterialCount}), "
              f"instances={len(scene.instances)}, lights={len(scene.lights)}, "
              f"box_indices={scene.GetIndexCount(MESH_BOX)}")
        print("Test PASSED" if ok else "Test FAILED!")
        deviceManager.Shutdown()
        return ok

    DeferredShadingParam_MaxLightsPerTile = 64  # Must match c_MaxLightsPerTile in lighting.hlsli.
    DeferredShadingParam_TileWidth = 8
    DeferredShadingParam_TileHeight = 4

    # Program name the work graph state object is built under and later looked up by, matching
    # WORKGRAPH_NAME in work_graphs_d3d12.cpp:42. Arbitrary, but it must be identical between
    # the CD3DX12_WORK_GRAPH_SUBOBJECT's SetProgramName and GetProgramIdentifier lookups (both
    # done inside the D3D12WorkGraphPipeline binding).
    WORK_GRAPH_NAME = "D3D12WorkGraphs"

    def GetLightTileCountX(viewportWidth: int) -> int:
        return (viewportWidth + DeferredShadingParam_TileWidth - 1) // DeferredShadingParam_TileWidth

    def GetLightTileCountY(viewportHeight: int) -> int:
        return (viewportHeight + DeferredShadingParam_TileHeight - 1) // DeferredShadingParam_TileHeight

    class RenderTargets:
        def __init__(self, device, width: int, height: int) -> None:
            self.size = (width, height)

            depthDesc = pyd.TextureDesc()
            depthDesc.width = width
            depthDesc.height = height
            depthDesc.keepInitialState = True
            depthDesc.useClearValue = True
            depthDesc.clearValue = pyd.Color(1.0)
            depthDesc.isRenderTarget = True
            depthDesc.isTypeless = True
            depthDesc.format = pyd.Format.D32
            depthDesc.initialState = pyd.ResourceStates.ShaderResource
            depthDesc.debugName = "DepthBuffer"
            self.depth = device.createTexture(depthDesc)

            gbufferDesc = pyd.TextureDesc()
            gbufferDesc.width = width
            gbufferDesc.height = height
            gbufferDesc.keepInitialState = True
            gbufferDesc.isRenderTarget = True
            gbufferDesc.format = pyd.Format.RGBA16_UINT
            gbufferDesc.useClearValue = True
            gbufferDesc.clearValue = pyd.Color(0.0)
            gbufferDesc.initialState = pyd.ResourceStates.ShaderResource
            gbufferDesc.debugName = "GBuffer"
            self.gbuffer = device.createTexture(gbufferDesc)

            ldrDesc = pyd.TextureDesc()
            ldrDesc.width = width
            ldrDesc.height = height
            ldrDesc.keepInitialState = True
            ldrDesc.format = pyd.Format.RGBA8_UNORM
            ldrDesc.isUAV = True
            ldrDesc.initialState = pyd.ResourceStates.UnorderedAccess
            ldrDesc.debugName = "LDRBuffer"
            self.ldr_buffer = device.createTexture(ldrDesc)

            self.framebuffer_gb = pyd.FramebufferFactory(device)
            self.framebuffer_gb.SetRenderTargets([self.gbuffer])
            self.framebuffer_gb.depthTarget = self.depth

        def is_update_required(self, width: int, height: int) -> bool:
            return self.size != (width, height)

    class UIData:
        def __init__(self) -> None:
            # 0 = Work Graph (Broadcast Launch), 1 = Compute Dispatches -- same order/index as
            # the combo built in UIRenderer.buildUI, matching work_graphs_d3d12.cpp's
            # techniqueNames array and UIData::CurrentTechnique's default of 0.
            self.currentTechnique = 0
            self.paused = False
            self.resetAnim = False
            self.gpuFrameTime = 0.0
            self.gpuShadingTime = 0.0

    class WorkGraphs:
        _TIMER_RING_SIZE = 10  # matches work_graphs_d3d12.cpp's QueuedFramesCount

        def __init__(self, device, ui) -> None:
            self.device = device
            self.ui = ui
            self.scene = Scene()
            self.render_targets = None
            self.time_in_seconds = 0.0
            self.time_diff_this_frame = 0.0
            self.force_reset_animation = True
            # Which shading technique to use, synchronized from ui.currentTechnique each
            # Animate() call (see animate() below). Only honoured once load_scene_pipelines has
            # actually built a work graph -- see use_work_graph_now(). Starts True to match
            # work_graphs_d3d12.cpp's m_CurrentTechnique default of
            # Techniques::WorkGraphBroadcastingLaunch (== ui.currentTechnique's default of 0).
            self.want_work_graph = ui.currentTechnique == 0
            self.work_graph_pipeline = None
            self.work_graph_backing = None
            self.init_work_graph_backing = True

            self.next_timer_to_use = 0
            self.frame_timers = [device.createTimerQuery() for _ in range(self._TIMER_RING_SIZE)]
            self.shading_timers = [device.createTimerQuery() for _ in range(self._TIMER_RING_SIZE)]

        def _get_last_valid_query_timer(self, timers) -> float:
            # Ports work_graphs_d3d12.cpp's GetLastValidQueryTimer: search backward from just
            # before the ring-buffer slot about to be reused, then wrap around to the end --
            # this always finds the most recently completed query without stalling on one still
            # in flight. Returns milliseconds, or -1.0 if nothing has completed yet.
            device = self.device
            for i in range(self.next_timer_to_use - 1, -1, -1):
                if device.pollTimerQuery(timers[i]):
                    return device.getTimerQueryTime(timers[i]) * 1000.0
            for i in range(self._TIMER_RING_SIZE - 1, self.next_timer_to_use, -1):
                if device.pollTimerQuery(timers[i]):
                    return device.getTimerQueryTime(timers[i]) * 1000.0
            return -1.0

        def toggle_technique(self) -> None:
            self.want_work_graph = not self.want_work_graph
            # The backing memory must be re-initialized whenever the graph starts being used
            # again, since something else may have used that memory in between -- same reason
            # work_graphs_d3d12.cpp:814 sets m_InitWorkGraphBackingMemory on a technique change.
            self.init_work_graph_backing = True

        def init_scene(self, commandList) -> None:
            self.scene.CreateAssets(self.device, commandList)

        def load_scene_pipelines(self, fbinfo_view) -> None:
            # Design note: unlike the C++ sample (which builds ONE shared, over-provisioned
            # BindingLayoutDesc across all 5 passes, padded with null SRV/UAV placeholder
            # resources for slots a given pass doesn't use, so every pass can share one root
            # signature), each pass here gets its OWN binding layout, tailored to exactly the
            # registers that specific compiled shader stage actually declares. This is possible
            # because pydonut's BindingLayoutItem has no PushConstants factory (only
            # BindingSetItem does) -- a layout can only be hand-built from BindingLayoutItem, so
            # a manually-constructed shared layout can't declare a push-constant range at all.
            # `pyd.CreateBindingSetAndLayout(device, visibility, registerSpace, bindingSetDesc)`
            # derives the matching layout FROM a binding set (which DOES support
            # BindingSetItem.PushConstants), so it's used once per pass instead. This also drops
            # the null-placeholder buffers/textures entirely -- each pass only ever binds what
            # its own shader stage actually uses.
            api = self.device.getGraphicsAPI()
            shader_dir = folder / "shaders" / "work_graphs"
            source_paths = {
                "animation": shader_dir / "animation.hlsl",
                "gbuffer_fill": shader_dir / "gbuffer_fill.hlsl",
                "light_culling": shader_dir / "light_culling.hlsl",
                "deferred_shading": shader_dir / "deferred_shading.hlsl",
            }
            sources = {k: v.read_text(encoding="utf-8") for k, v in source_paths.items()}
            include_paths = [str(shader_dir)]

            assert pyd.CompileShader is not None

            animate_objects_bc = pyd.CompileShader(sources["animation"], "CSMainObjects", pyd.ShaderType.Compute, api, sourceName="animation.hlsl", includePaths=include_paths)
            animate_lights_bc = pyd.CompileShader(sources["animation"], "CSMainLights", pyd.ShaderType.Compute, api, sourceName="animation.hlsl", includePaths=include_paths)
            gbuffer_vs_bc = pyd.CompileShader(sources["gbuffer_fill"], "VSMain", pyd.ShaderType.Vertex, api, sourceName="gbuffer_fill.hlsl", includePaths=include_paths)
            gbuffer_ps_bc = pyd.CompileShader(sources["gbuffer_fill"], "PSMain", pyd.ShaderType.Pixel, api, sourceName="gbuffer_fill.hlsl", includePaths=include_paths)
            # requiresVulkan11=True: CSMain uses WaveActiveBitOr/WaveIsFirstLane, which need a
            # higher SPIR-V target env than DXC's default on Vulkan.
            light_culling_bc = pyd.CompileShader(sources["light_culling"], "CSMain", pyd.ShaderType.Compute, api, sourceName="light_culling.hlsl", includePaths=include_paths, requiresVulkan11=True)
            deferred_shading_bc = pyd.CompileShader(sources["deferred_shading"], "CSMain", pyd.ShaderType.Compute, api, sourceName="deferred_shading.hlsl", includePaths=include_paths)

            animate_objects_shader = self.device.createShader(animate_objects_bc, "CSMainObjects", pyd.ShaderType.Compute)
            animate_lights_shader = self.device.createShader(animate_lights_bc, "CSMainLights", pyd.ShaderType.Compute)
            gbuffer_vs = self.device.createShader(gbuffer_vs_bc, "VSMain", pyd.ShaderType.Vertex)
            gbuffer_ps = self.device.createShader(gbuffer_ps_bc, "PSMain", pyd.ShaderType.Pixel)
            light_culling_shader = self.device.createShader(light_culling_bc, "CSMain", pyd.ShaderType.Compute)
            deferred_shading_shader = self.device.createShader(deferred_shading_bc, "CSMain", pyd.ShaderType.Compute)

            attributes = [pyd.VertexAttributeDesc(), pyd.VertexAttributeDesc()]
            attributes[0].name = "POSITION"
            attributes[0].format = pyd.Format.RGB32_FLOAT
            attributes[0].offset = 0
            attributes[0].elementStride = 24
            attributes[1].name = "NORMAL"
            attributes[1].format = pyd.Format.RGB32_FLOAT
            attributes[1].offset = 12
            attributes[1].elementStride = 24
            self.input_layout = self.device.createInputLayout(attributes, gbuffer_vs)

            cbDesc = pyd.BufferDesc()
            cbDesc.byteSize = 256
            cbDesc.maxVersions = 16
            cbDesc.isConstantBuffer = True
            cbDesc.isVolatile = True
            cbDesc.debugName = "SceneConstants"
            cbDesc.initialState = pyd.ResourceStates.ShaderResource
            cbDesc.keepInitialState = True
            self.constant_buffer = self.device.createBuffer(cbDesc)

            assert self.render_targets is not None

            width, height = self.render_targets.size
            tilesX, tilesY = GetLightTileCountX(width), GetLightTileCountY(height)
            tileCount = tilesX * tilesY
            culledLightsDesc = pyd.BufferDesc()
            culledLightsDesc.byteSize = tileCount * DeferredShadingParam_MaxLightsPerTile * 4
            culledLightsDesc.structStride = 4
            culledLightsDesc.canHaveUAVs = True
            culledLightsDesc.debugName = "CulledLights"
            culledLightsDesc.initialState = pyd.ResourceStates.ShaderResource
            culledLightsDesc.keepInitialState = True
            self.culled_lights_buffer = self.device.createBuffer(culledLightsDesc)

            # Per-pass binding sets/layouts, each matching exactly that shader's own registers
            # (register numbers taken directly from the copied HLSL files in shaders/work_graphs/).

            objectsSetDesc = pyd.BindingSetDesc()
            objectsSetDesc.bindings = [
                pyd.BindingSetItem.PushConstants(0, 12),  # cbuffer InlineConstants: g_Time, g_TimeDiff, g_ResetState (animation.hlsl)
                pyd.BindingSetItem.StructuredBuffer_SRV(0, self.scene.GetWorldObjectsBuffer()),  # t_InstanceData : t0
                pyd.BindingSetItem.StructuredBuffer_UAV(0, self.scene.GetAnimStateBuffer()),      # u_AnimStateData : u0
            ]
            self.animate_objects_layout, self.binding_sets_animate_objects = pyd.CreateBindingSetAndLayout(
                self.device, pyd.ShaderType.Compute, 0, objectsSetDesc)

            lightsSetDesc = pyd.BindingSetDesc()
            lightsSetDesc.bindings = [
                pyd.BindingSetItem.PushConstants(0, 12),  # same InlineConstants layout, CSMainLights only reads g_Time/g_ResetState
                pyd.BindingSetItem.StructuredBuffer_UAV(0, self.scene.GetLightsBuffer()),  # u_LightData : u0
            ]
            self.animate_lights_layout, self.binding_sets_animate_lights = pyd.CreateBindingSetAndLayout(
                self.device, pyd.ShaderType.Compute, 0, lightsSetDesc)

            gbufferSetDesc = pyd.BindingSetDesc()
            gbufferSetDesc.bindings = [
                pyd.BindingSetItem.PushConstants(0, 4),  # cbuffer InstanceConstantBuffer: g_InstanceID (gbuffer_fill.hlsl)
                pyd.BindingSetItem.ConstantBuffer(1, self.constant_buffer),  # SceneConstantBuffer : b1 (scene_data.hlsli, viewProj)
                pyd.BindingSetItem.StructuredBuffer_SRV(0, self.scene.GetWorldObjectsBuffer()),  # t_InstanceData : t0
                pyd.BindingSetItem.StructuredBuffer_SRV(3, self.scene.GetMaterialsBuffer()),     # t_MaterialData : t3
                pyd.BindingSetItem.StructuredBuffer_SRV(4, self.scene.GetAnimStateBuffer()),     # t_AnimStateData : t4
            ]
            self.gbuffer_fill_layout, self.binding_sets_gbuffer_fill = pyd.CreateBindingSetAndLayout(
                self.device, pyd.ShaderType.All, 0, gbufferSetDesc)

            cullingSetDesc = pyd.BindingSetDesc()
            cullingSetDesc.bindings = [
                pyd.BindingSetItem.PushConstants(0, 12),  # g_LightTilesX, g_LightTilesY, g_LightCount (light_culling.hlsl)
                pyd.BindingSetItem.ConstantBuffer(1, self.constant_buffer),
                pyd.BindingSetItem.Texture_SRV(1, self.render_targets.depth),                    # t_DepthBuffer : t1
                pyd.BindingSetItem.StructuredBuffer_SRV(4, self.scene.GetLightsBuffer()),        # t_LightData : t4
                pyd.BindingSetItem.StructuredBuffer_UAV(0, self.culled_lights_buffer),           # u_CulledLightsDataRW : u0
            ]
            self.light_culling_layout, self.binding_sets_light_culling = pyd.CreateBindingSetAndLayout(
                self.device, pyd.ShaderType.Compute, 0, cullingSetDesc)

            shadingSetDesc = pyd.BindingSetDesc()
            shadingSetDesc.bindings = [
                pyd.BindingSetItem.PushConstants(0, 12),  # g_LightTilesX, g_LightTilesY, g_LightCount (deferred_shading.hlsl)
                pyd.BindingSetItem.ConstantBuffer(1, self.constant_buffer),
                pyd.BindingSetItem.StructuredBuffer_SRV(0, self.scene.GetMaterialsBuffer()),     # t_MaterialData : t0
                pyd.BindingSetItem.Texture_SRV(1, self.render_targets.gbuffer),                  # t_GBuffer : t1
                pyd.BindingSetItem.Texture_SRV(2, self.render_targets.depth),                    # t_DepthBuffer : t2
                pyd.BindingSetItem.StructuredBuffer_SRV(3, self.culled_lights_buffer),           # t_CulledLightsData : t3
                pyd.BindingSetItem.StructuredBuffer_SRV(4, self.scene.GetLightsBuffer()),        # t_LightData : t4
                pyd.BindingSetItem.Texture_UAV(1, self.render_targets.ldr_buffer),               # u_LDRBuffer : u1
            ]
            self.deferred_shading_layout, self.binding_sets_deferred_shading = pyd.CreateBindingSetAndLayout(
                self.device, pyd.ShaderType.Compute, 0, shadingSetDesc)

            gfxDesc = pyd.GraphicsPipelineDesc()
            gfxDesc.inputLayout = self.input_layout
            gfxDesc.addBindingLayout(self.gbuffer_fill_layout)
            gfxDesc.VS = gbuffer_vs
            gfxDesc.PS = gbuffer_ps
            self.gbuffer_fill_pso = self.device.createGraphicsPipeline(gfxDesc, fbinfo_view)

            csDesc = pyd.ComputePipelineDesc()
            csDesc.addBindingLayout(self.animate_objects_layout)
            csDesc.CS = animate_objects_shader
            self.animate_objects_pso = self.device.createComputePipeline(csDesc)
            csDesc = pyd.ComputePipelineDesc()
            csDesc.addBindingLayout(self.animate_lights_layout)
            csDesc.CS = animate_lights_shader
            self.animate_lights_pso = self.device.createComputePipeline(csDesc)
            csDesc = pyd.ComputePipelineDesc()
            csDesc.addBindingLayout(self.light_culling_layout)
            csDesc.CS = light_culling_shader
            self.cull_lights_pso = self.device.createComputePipeline(csDesc)
            csDesc = pyd.ComputePipelineDesc()
            csDesc.addBindingLayout(self.deferred_shading_layout)
            csDesc.CS = deferred_shading_shader
            self.shade_pso = self.device.createComputePipeline(csDesc)

            self.binding_sets = {
                "animate_objects": self.binding_sets_animate_objects,
                "animate_lights": self.binding_sets_animate_lights,
                "gbuffer_fill": self.binding_sets_gbuffer_fill,
                "light_culling": self.binding_sets_light_culling,
                "deferred_shading": self.binding_sets_deferred_shading,
            }

            self._load_work_graph_pipeline(shader_dir, include_paths, api, tilesX, tilesY)

            self.force_reset_animation = True

        def _load_work_graph_pipeline(self, shader_dir, include_paths, api, tilesX: int, tilesY: int) -> None:
            # The work graph replaces BOTH the light-culling and deferred-shading dispatches
            # with one launch: its LightCull_Node entry culls per tile and then spawns
            # Sky_Node / DarkTile_Node / one Material_Nodes[materialType] node per tile, so
            # each tile only runs the material shading it actually needs.
            #
            # It reuses deferred_shading's root signature and binding set rather than getting
            # its own. work_graph_broadcasting.hlsl declares a strict SUBSET of that pass's
            # registers (b0, b1, t0, t1, t2, t4, u1 -- it has no t3 culled-lights buffer,
            # since culled lights travel inside the node records instead), and binding a
            # superset root signature is legal in D3D12. Sharing also means the state object
            # can take shade_pso's root signature directly, matching how the C++ sample sources
            # its root signature from an existing PSO.
            self.work_graph_pipeline = None
            self.work_graph_backing = None
            self.init_work_graph_backing = True

            if pyd.D3D12WorkGraphPipeline is None or api != pyd.GraphicsAPI.D3D12:
                return  # Vulkan build, or a non-D3D12 build without the binding at all.

            try:
                source = (shader_dir / "work_graph_broadcasting.hlsl").read_text(encoding="utf-8")
                # Work graph nodes need shader model 6.8; the rest of this sample is 6_5.
                assert pyd.CompileShaderLibrary is not None
                bytecode = pyd.CompileShaderLibrary(
                    source, api, sourceName="work_graph_broadcasting.hlsl",
                    shaderModel="6_8", includePaths=include_paths)
                library = self.device.createShaderLibrary(bytecode)
                assert library is not None, "createShaderLibrary returned null for the work graph"

                # LightCull_Node's [NodeDispatchGrid(1,1,1)] is a placeholder -- the real grid is
                # one group per screen tile, known only once the viewport size is.
                self.work_graph_pipeline = pyd.D3D12WorkGraphPipeline(
                    self.device, library, self.shade_pso, WORK_GRAPH_NAME,
                    broadcastEntryNodeName="LightCull_Node",
                    dispatchGridX=tilesX, dispatchGridY=tilesY, dispatchGridZ=1)

                backingDesc = pyd.BufferDesc()
                backingDesc.byteSize = self.work_graph_pipeline.getBackingMemorySize()
                backingDesc.canHaveUAVs = True
                backingDesc.debugName = "WorkGraphBackingMem"
                backingDesc.initialState = pyd.ResourceStates.UnorderedAccess
                backingDesc.keepInitialState = True
                self.work_graph_backing = self.device.createBuffer(backingDesc)
            except RuntimeError as e:
                # Raised when the device/driver reports no D3D12_WORK_GRAPHS_TIER support, or
                # when state object creation fails. Not fatal: the dispatch path still works.
                pyd.log.warning(f"Work graph technique unavailable, dispatch only: {e}")
                self.work_graph_pipeline = None
                self.work_graph_backing = None

        def update_scene_constants(self, commandList, view) -> None:
            sceneSize = self.scene.GetSceneSize()
            sceneHeight = self.scene.GetSceneHeight()

            camPosOrbitSpeed = 0.1
            camTargetOrbitSpeed = 0.03
            camPosRadiusRatio = 0.75
            camTargetRadiusRatio = 0.1
            camClimbSpeed = 0.1
            camClimbRatio = 0.6
            camVerticalFov = (math.pi / 4.0) * 1.15
            camNearClip = 0.5

            t = self.time_in_seconds
            camX = math.cos(t * camPosOrbitSpeed) * sceneSize * camPosRadiusRatio
            camY = math.sin(t * camClimbSpeed - 1.75) * sceneHeight * camClimbRatio + sceneHeight * camClimbRatio + 10.0
            camZ = math.sin(t * camPosOrbitSpeed) * sceneSize * camPosRadiusRatio

            tgtX = math.cos(t * camTargetOrbitSpeed) * sceneSize * camTargetRadiusRatio
            tgtY = 0.0
            tgtZ = math.sin(t * camTargetOrbitSpeed) * sceneSize * camTargetRadiusRatio

            assert self.render_targets is not None

            width, height = self.render_targets.size
            aspectRatio = width / height
            # The view's viewport is set by render() before this runs -- see the note there.
            view.SetMatricesLookAt(camX, camY, camZ, tgtX, tgtY, tgtZ, 0.0, 1.0, 0.0,
                                    aspectRatio, camVerticalFov, camNearClip, sceneSize * 1.2)
            view.UpdateCache()

            dirX, dirY, dirZ = tgtX - camX, tgtY - camY, tgtZ - camZ
            dirLen = math.sqrt(dirX * dirX + dirY * dirY + dirZ * dirZ) or 1.0
            dirX, dirY, dirZ = dirX / dirLen, dirY / dirLen, dirZ / dirLen

            # SceneConstantBuffer layout (256 bytes total): viewProj(64) + viewProjInverse(64)
            # + camPosAndSceneTime(16) + camDir(16) + viewportSizeXY(16) + padding(80), matching
            # scene_data.hlsli's cbuffer exactly. GetViewProjMatrixBytes() (Task 1) returns the
            # first 128 bytes (viewProj + viewProjInverse) directly from PlanarView's own
            # GetViewProjectionMatrix()/GetInverseViewProjectionMatrix() -- no matrix math here.
            viewProjBytes = view.GetViewProjMatrixBytes()  # 128 bytes: viewProj + viewProjInverse
            constants = viewProjBytes + struct.pack(
                "<4f4f4f80x",
                camX, camY, camZ, self.time_in_seconds,
                dirX, dirY, dirZ, 0.0,
                float(width), float(height), 0.0, 0.0,
            )
            assert len(constants) == 256
            commandList.writeBuffer(self.constant_buffer, constants)

        def populate_animation_pass(self, commandList) -> None:
            resetAnim = self.force_reset_animation or self.ui.resetAnim

            state = pyd.ComputeState()
            state.pipeline = self.animate_objects_pso
            state.addBindingSet(self.binding_sets["animate_objects"])
            commandList.setComputeState(state)
            rootConstants = struct.pack("<ffI", self.time_in_seconds, self.time_diff_this_frame, 1 if resetAnim else 0)
            commandList.setPushConstants(rootConstants)
            threadsX = 32
            totalDispatch = (len(self.scene.instances) + threadsX - 1) // threadsX
            commandList.dispatch(max(totalDispatch, 1), 1, 1)

            state = pyd.ComputeState()
            state.pipeline = self.animate_lights_pso
            state.addBindingSet(self.binding_sets["animate_lights"])
            commandList.setComputeState(state)
            commandList.setPushConstants(rootConstants)
            totalDispatch = (len(self.scene.lights) + threadsX - 1) // threadsX
            commandList.dispatch(max(totalDispatch, 1), 1, 1)

            self.force_reset_animation = False

        def populate_gbuffer_pass(self, commandList, framebuffer) -> None:

            assert self.render_targets is not None

            commandList.clearDepthStencilTexture(self.render_targets.depth, True, 1.0, False, 0)

            fbinfo = framebuffer.getFramebufferInfo()

            lastMeshType = None
            indexCount = 0
            for objectIndex, instance in enumerate(self.scene.instances):
                meshType = instance["meshType"]
                if meshType != lastMeshType:
                    lastMeshType = meshType
                    indexCount = self.scene.GetIndexCount(meshType)

                    state = pyd.GraphicsState()
                    state.pipeline = self.gbuffer_fill_pso
                    state.addBindingSet(self.binding_sets["gbuffer_fill"])
                    state.framebuffer = framebuffer
                    state.viewport.addViewportAndScissorRect(fbinfo.getViewport())
                    state.addVertexBuffer(self.scene.GetMeshVertexBuffer(meshType), 0)
                    state.setIndexBuffer(self.scene.GetMeshIndexBuffer(meshType), pyd.Format.R16_UINT)
                    commandList.setGraphicsState(state)

                # cbuffer InstanceConstantBuffer (gbuffer_fill.hlsl): one uint32, g_InstanceID.
                rootConstant = struct.pack("<I", objectIndex)
                commandList.setPushConstants(rootConstant)
                drawArgs = pyd.DrawArguments()
                drawArgs.vertexCount = indexCount
                commandList.drawIndexed(drawArgs)

        def populate_light_culling_pass(self, commandList) -> None:
            state = pyd.ComputeState()
            state.pipeline = self.cull_lights_pso
            state.addBindingSet(self.binding_sets["light_culling"])
            commandList.setComputeState(state)

            assert self.render_targets is not None

            width, height = self.render_targets.size
            tilesX, tilesY = GetLightTileCountX(width), GetLightTileCountY(height)
            rootConstants = struct.pack("<III", tilesX, tilesY, len(self.scene.lights))
            commandList.setPushConstants(rootConstants)
            commandList.dispatch(tilesX, tilesY, 1)

        def populate_deferred_shading_pass(self, commandList) -> None:
            state = pyd.ComputeState()
            state.pipeline = self.shade_pso
            state.addBindingSet(self.binding_sets["deferred_shading"])
            commandList.setComputeState(state)

            assert self.render_targets is not None

            width, height = self.render_targets.size
            tilesX, tilesY = GetLightTileCountX(width), GetLightTileCountY(height)
            rootConstants = struct.pack("<III", tilesX, tilesY, len(self.scene.lights))
            commandList.setPushConstants(rootConstants)
            threadsX, threadsY = 8, 4
            commandList.dispatch((width + threadsX - 1) // threadsX, (height + threadsY - 1) // threadsY, 1)

        def populate_deferred_shading_work_graph(self, commandList) -> None:
            # Resource bindings are established the ordinary way. The pipeline named in this
            # ComputeState is never actually executed -- SetProgram (inside dispatchWorkGraph)
            # swaps the program to the work graph. It has to be shade_pso specifically, because
            # the state object was created against shade_pso's root signature, and nvrhi binds
            # the descriptors through whichever pipeline it sees here.
            state = pyd.ComputeState()
            state.pipeline = self.shade_pso
            state.addBindingSet(self.binding_sets["deferred_shading"])
            commandList.setComputeState(state)

            # The shared root signature declares 3 uints (deferred_shading.hlsl's
            # g_LightTilesX/Y/g_LightCount). work_graph_broadcasting.hlsl's InlineConstants
            # declares only g_LightCount, so it must be first; the other two are padding here.
            commandList.setPushConstants(struct.pack("<III", len(self.scene.lights), 0, 0))

            # Backing memory only needs initializing the first time it is used by this graph
            # (and again after the technique is switched away and back).
            commandList.dispatchWorkGraph(
                self.work_graph_pipeline, self.work_graph_backing, self.init_work_graph_backing, 1)
            self.init_work_graph_backing = False

        def use_work_graph_now(self) -> bool:
            return self.want_work_graph and self.work_graph_pipeline is not None

        def render(self, commandList, view, backbuffer) -> None:
            fbinfo = backbuffer.getFramebufferInfo()
            width, height = fbinfo.width, fbinfo.height

            # Must happen before any GetFramebuffer(view) call below, including the one whose
            # FramebufferInfo the G-buffer pipeline is created from. FramebufferFactory keys
            # its framebuffers off view.GetSubresources(), and a PlanarView that never had a
            # viewport set yields a degenerate framebuffer whose getViewport() is empty -- so
            # the G-buffer pass rasterizes nothing, depth stays at its 1.0 clear value, and
            # deferred_shading.hlsl takes its "depth == 1.0 -> EvaluateSky" branch for every
            # pixel, drawing the starfield sky and no scene at all.
            view.SetViewport(pyd.Viewport(float(width), float(height)))

            if self.render_targets is None or self.render_targets.is_update_required(width, height):
                self.render_targets = RenderTargets(self.device, width, height)
                gbuffer_fb = self.render_targets.framebuffer_gb.GetFramebuffer(view)
                self.load_scene_pipelines(gbuffer_fb.getFramebufferInfo())

            timerIndex = self.next_timer_to_use
            self.device.resetTimerQuery(self.frame_timers[timerIndex])
            self.device.resetTimerQuery(self.shading_timers[timerIndex])
            commandList.beginTimerQuery(self.frame_timers[timerIndex])

            self.update_scene_constants(commandList, view)
            self.populate_animation_pass(commandList)
            self.populate_gbuffer_pass(commandList, self.render_targets.framebuffer_gb.GetFramebuffer(view))
            commandList.beginTimerQuery(self.shading_timers[timerIndex])
            if self.use_work_graph_now():
                # One launch replaces both the light-culling and deferred-shading dispatches.
                self.populate_deferred_shading_work_graph(commandList)
            else:
                self.populate_light_culling_pass(commandList)
                self.populate_deferred_shading_pass(commandList)
            commandList.endTimerQuery(self.shading_timers[timerIndex])

            # Plain GPU bit copy, matching work_graphs_d3d12.cpp:880's own
            # commandList->copyTexture(...) exactly. Deliberately NOT
            # CommonRenderPasses.BlitTexture: the swap chain is SRGBA8_UNORM while the LDR
            # buffer is RGBA8_UNORM, so a shader blit would resolve through an sRGB render
            # target and re-encode pixels this shader already wrote in final display form.
            # copyTexture moves the bits untouched, which is what the original sample does.
            backbufferTexture = backbuffer.getDesc().getColorAttachment(0).texture
            commandList.copyTexture(backbufferTexture, self.render_targets.ldr_buffer)

            commandList.endTimerQuery(self.frame_timers[timerIndex])
            self.next_timer_to_use = (self.next_timer_to_use + 1) % self._TIMER_RING_SIZE

        def animate(self, elapsed: float) -> None:
            if not self.ui.paused:
                self.time_diff_this_frame = elapsed
                self.time_in_seconds += elapsed
            else:
                self.time_diff_this_frame = 0.0

            if self.force_reset_animation or self.ui.resetAnim:
                self.time_in_seconds = 0.0
                self.time_diff_this_frame = 0.0

            wantWorkGraph = self.ui.currentTechnique == 0
            if wantWorkGraph != self.want_work_graph:
                self.toggle_technique()
                if self.want_work_graph and self.work_graph_pipeline is None:
                    pyd.log.warning("Work graph technique is unavailable on this device/driver.")

            self.ui.gpuFrameTime = self._get_last_valid_query_timer(self.frame_timers)
            self.ui.gpuShadingTime = self._get_last_valid_query_timer(self.shading_timers)

    class UIRenderer(pyd.ImGui_Renderer):
        def __init__(self, deviceManager, ui) -> None:
            super().__init__(deviceManager)
            self.ui = ui
            pyd.ImGui.DisableIniFile()

        def buildUI(self) -> None:
            pyd.ImGui.SetNextWindowPos(10.0, 10.0)
            pyd.ImGui.Begin("Options/Stats", _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE)

            _, self.ui.currentTechnique = pyd.ImGui.Combo(
                "Current Technique", self.ui.currentTechnique,
                ["Work Graph (Broadcast Launch)", "Compute Dispatches"],
            )
            _, self.ui.paused = pyd.ImGui.Checkbox("Pause Animation", self.ui.paused)
            self.ui.resetAnim = pyd.ImGui.Button("Reset Animation")
            pyd.ImGui.Text(f"Frame Time (GPU): {self.ui.gpuFrameTime:.3f} ms")
            pyd.ImGui.Text(f"Shading Time (GPU): {self.ui.gpuShadingTime:.3f} ms")

            pyd.ImGui.End()

    if "--scene-smoke-test" in sys.argv:
        sys.exit(0 if _scene_smoke_test() else 1)

    is_debug = "-debug" in sys.argv
    pyd.log.ConsoleApplicationMode()
    if not is_debug:
        pyd.log.SetMinSeverity(pyd.LogSeverity.Warning)

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        pyd.log.fatal("Failed to create DeviceManager.")
        sys.exit(1)

    deviceParams = pyd.DeviceCreationParameters()
    if is_debug:
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True
    deviceParams.backBufferWidth = 1920
    deviceParams.backBufferHeight = 1080

    WINDOW_TITLE = "PyDonut Work Graphs"

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, WINDOW_TITLE):
        pyd.log.fatal("Cannot initialize a graphics device with the requested parameters")
        sys.exit(1)

    device = deviceManager.GetDevice()

    uiData = UIData()
    wg = WorkGraphs(device, uiData)
    commandList = device.createCommandList()
    commandList.open()
    wg.init_scene(commandList)
    commandList.close()
    device.executeCommandList(commandList)
    device.waitForIdle()

    view = pyd.PlanarView()

    class RenderPass(pyd.IRenderPass):
        def __init__(self, deviceManager) -> None:
            super().__init__(deviceManager)

        def Render(self, framebuffer) -> None:
            commandList.open()
            wg.render(commandList, view, framebuffer)
            commandList.close()
            device.executeCommandList(commandList)
            deviceManager.SetInformativeWindowTitle(WINDOW_TITLE)

        def Animate(self, elapsedTimeSeconds: float) -> None:
            wg.animate(elapsedTimeSeconds)

    # Framework shaders (needed only so UIRenderer.Init() can load ImGui's own vertex/pixel
    # shaders) -- same RootFileSystem/ShaderFactory mount convention rt_particles.py uses.
    rootFS = pyd.RootFileSystem()
    frameworkShaderPath = folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(api)
    rootFS.mount(Path("/shaders/donut"), frameworkShaderPath)
    uiShaderFactory = pyd.ShaderFactory(device, rootFS, Path("/shaders"))

    renderPass = RenderPass(deviceManager)
    gui = UIRenderer(deviceManager, uiData)

    if not gui.Init(uiShaderFactory):
        pyd.log.fatal("Failed to initialize the ImGui renderer")
        sys.exit(1)

    deviceManager.AddRenderPassToBack(renderPass)
    deviceManager.AddRenderPassToBack(gui)
    deviceManager.RunMessageLoop()
    deviceManager.RemoveRenderPass(gui)
    deviceManager.RemoveRenderPass(renderPass)
    deviceManager.Shutdown()

    print("Done.")
