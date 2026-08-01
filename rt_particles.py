# /******************************************************************************
# * Copyright (C) 1991-2026 ASDAlexander77.
# *
# * Permission is hereby granted, free of charge, to any person obtaining
# * a copy of this software and associated documentation files (the
# * "Software"), to deal in the Software without restriction, including
# * without limitation the rights to use, copy, modify, merge, publish,
# * distribute, sublicense, and/or sell copies of the Software, and to
# * permit persons to whom the Software is furnished to do so, subject to
# * the following conditions:
# *
# * The above copyright notice and this permission notice shall be
# * included in all copies or substantial portions of the Software.
# *
# * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# * MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# * IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# * CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# * TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# * SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# ******************************************************************************/

if __name__ == "__main__":
    import math
    import random
    import struct
    import sys
    from pathlib import Path

    from src import pydonut as pyd

    WINDOW_TITLE = "PyDonut Ray Traced Particles"
    folder = Path(__file__).resolve().parent

    def FindParticleScene() -> Path | None:
        candidate = folder / "media" / "rt_particles" / "ParticleScene.gltf"
        return candidate if candidate.is_file() else None

    _MAX_PARTICLES = 1024
    _INDICES_PER_QUAD = 6
    _VERTICES_PER_QUAD = 4
    _SIZEOF_UINT32 = 4
    _SIZEOF_FLOAT3 = 12
    _SIZEOF_FLOAT2 = 8
    _SIZEOF_PARTICLE_INFO = 64

    # sizeof(GlobalConstants) from shaders/rt_particles/rt_particles_cb.h: PlanarViewConstants
    # view (720 bytes, per rt_reflections.py/rt_shadows.py) + primaryRayConeAngle (4) +
    # reorientParticlesInPrimaryRays (4) + reorientParticlesInSecondaryRays (4) +
    # orientationMode (4) + environmentMapTextureIndex (4) = 740 bytes, all already
    # 4-byte aligned.
    _GLOBAL_CONSTANTS_SIZE = 740

    # Binding slots from shaders/rt_particles/rt_particles_cb.h / rt_particles.hlsl.
    _BINDING_CONSTANTS = 0
    _BINDING_SCENE_BVH = 0
    _BINDING_INSTANCE_BUFFER = 1
    _BINDING_GEOMETRY_BUFFER = 2
    _BINDING_MATERIAL_BUFFER = 3
    _BINDING_PARTICLE_INFO_BUFFER = 4
    _BINDING_MATERIAL_SAMPLER = 0
    _BINDING_OUTPUT_UAV = 0

    # From shaders/rt_particles/rt_particles_cb.h.
    _INSTANCE_MASK_OPAQUE = 1
    _INSTANCE_MASK_PARTICLE_GEOMETRY = 2
    _INSTANCE_MASK_INTERSECTION_PARTICLE = 4

    _ORIENTATION_MODE_AVT_MATRIX = 0
    _ORIENTATION_MODE_QUATERNION = 1
    _ORIENTATION_MODE_BEAM = 2
    _ORIENTATION_MODE_BASIS = 3

    _PARTICLE_TEXTURE_SMOKE = 0
    _PARTICLE_TEXTURE_LOGO = 1

    _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE = 64

    def RandomFloat() -> float:
        return random.random()

    def RandomFloat3() -> tuple[float, float, float]:
        return (random.random(), random.random(), random.random())

    # Minimal 3-vector arithmetic -- math types aren't exposed to Python, and the billboard
    # orientation math below only needs add/sub/scale/cross/normalize on plain (x, y, z) tuples.
    def VAdd(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
        return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

    def VSub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def VScale(a: tuple[float, float, float], s: float) -> tuple[float, float, float]:
        return (a[0] * s, a[1] * s, a[2] * s)

    def VCross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
        return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

    def VNormalize(a: tuple[float, float, float]) -> tuple[float, float, float]:
        length = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
        return (a[0] / length, a[1] / length, a[2] / length) if length > 0.0 else a

    class ParticleEntity:
        def __init__(self: ParticleEntity) -> None:
            self.active = False
            self.position: tuple[float, float, float] = (0.0, 0.0, 0.0)
            self.velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)
            self.color: tuple[float, float, float] = (1.0, 1.0, 1.0)
            self.radius = 0.0
            self.age = 0.0
            self.opacity = 1.0
            self.rotation = 0.0

        def Emit(self: ParticleEntity, emitterPosition: tuple[float, float, float]) -> None:
            self.active = True
            self.position = emitterPosition
            vx, vy, vz = RandomFloat3()
            self.velocity = (vx - 0.5, 1.0 + (vy - 0.5), vz - 0.5)
            self.radius = RandomFloat() * 0.05 + 0.1
            self.age = 0.0
            self.opacity = 1.0
            cx, cy, cz = RandomFloat3()
            self.color = (cx * 0.5 + 0.1, cy * 0.5 + 0.1, cz * 0.5 + 0.1)
            self.rotation = RandomFloat() * 6.28

        def Animate(self: ParticleEntity, time: float) -> None:
            lifeTime = 2.0
            px, py, pz = self.position
            vx, vy, vz = self.velocity
            self.position = (px + vx * time, py + vy * time, pz + vz * time)
            self.velocity = (vx + 1.0 * time, vy + 1.0 * time, vz)
            self.age += time
            self.radius += 0.5 * time
            self.opacity = max(0.0, min(1.0, (lifeTime - self.age) * 0.5))
            if self.age > lifeTime:
                self.active = False

    class UIData:
        def __init__(self: UIData) -> None:
            self.updatePipeline = True
            self.enableAnimations = True
            self.alwaysUpdateOrientation = True
            self.reorientParticlesInPrimaryRays = False
            self.reorientParticlesInSecondaryRays = True
            self.orientationMode = _ORIENTATION_MODE_QUATERNION
            self.mlabFragments = 4
            self.particleTexture = _PARTICLE_TEXTURE_SMOKE
            self.emitterPosition: tuple[float, float, float] = (0.0, 0.0, 0.0)

    class RayTracedParticles(pyd.ApplicationBase):
        def __init__(self: RayTracedParticles, deviceManager: pyd.DeviceManager, ui: UIData) -> None:
            super().__init__(deviceManager)
            self.ui = ui

            self.rootFS: pyd.RootFileSystem | None = None
            self.shaderFactory: pyd.ShaderFactory | None = None
            self.commonPasses: pyd.CommonRenderPasses | None = None
            self.bindingCache: pyd.BindingCache | None = None
            self.descriptorTableManager: pyd.DescriptorTableManager | None = None
            self.textureCache: pyd.TextureCache | None = None
            self.scene: pyd.Scene | None = None

            self.computeShader: pyd.Shader | None = None
            self.computePipeline: pyd.ComputePipeline | None = None
            self.commandList: pyd.CommandList | None = None
            self.bindingLayout: pyd.BindingLayout | None = None
            self.bindingSet: pyd.BindingSet | None = None
            self.bindlessLayout: pyd.BindingLayout | None = None
            self.topLevelAS: pyd.AccelStruct | None = None
            self.constantBuffer: pyd.Buffer | None = None
            self.colorBuffer: pyd.Texture | None = None

            self.camera = pyd.ThirdPersonCamera()
            self.view = pyd.PlanarView()

            self.particleBuffers: pyd.BufferGroup | None = None
            self.particleGeometry: pyd.MeshGeometry | None = None
            self.particleMesh: pyd.MeshInfo | None = None
            self.particleInstance: pyd.MeshInstance | None = None
            self.particleMaterial: pyd.Material | None = None
            self.particleInfoBuffer: pyd.Buffer | None = None
            self.particleIntersectionBLAS: pyd.AccelStruct | None = None

            self.particles: list[ParticleEntity] = []

            self.environmentMap: pyd.LoadedTexture | None = None
            self.smokeTexture: pyd.LoadedTexture | None = None
            self.logoTexture: pyd.LoadedTexture | None = None

            self.wallclockTime = 0.0
            self.lastEmitTime = 0.0

        def Init(self: RayTracedParticles) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            sceneFileName = FindParticleScene()
            if sceneFileName is None:
                pyd.log.fatal("Could not find ParticleScene.gltf under media/rt_particles/")
                return False

            # rt_particles.hlsl is this example's own shader, compiled at runtime below (same
            # pattern as the other RT examples) -- framework shaders are read as precompiled
            # .bin files via the mounted filesystem instead, since this project's CMake leaves
            # DONUT_WITH_STATIC_SHADERS off.
            frameworkShaderPath = folder / "bin" / "shaders" / "framework" / pyd.GetShaderTypeName(api)
            appShaderPath = folder / "shaders" / "rt_particles"
            mediaPath = folder / "media"

            self.rootFS = pyd.RootFileSystem()
            self.rootFS.mount(Path("/shaders/donut"), frameworkShaderPath)
            self.rootFS.mount(Path("/shaders/app"), appShaderPath)
            self.rootFS.mount(Path("/media"), mediaPath)

            self.shaderFactory = pyd.ShaderFactory(device, self.rootFS, Path("/shaders"))
            self.commonPasses = pyd.CommonRenderPasses(device, self.shaderFactory)
            self.m_CommonPasses = self.commonPasses
            self.bindingCache = pyd.BindingCache(device)

            bindlessLayoutDesc = pyd.BindlessLayoutDesc()
            bindlessLayoutDesc.visibility = pyd.ShaderType.All
            bindlessLayoutDesc.firstSlot = 0
            bindlessLayoutDesc.maxCapacity = 1024
            bindlessLayoutDesc.addRegisterSpace(pyd.BindingLayoutItem.RawBuffer_SRV(1))
            bindlessLayoutDesc.addRegisterSpace(pyd.BindingLayoutItem.Texture_SRV(2))
            self.bindlessLayout = device.createBindlessLayout(bindlessLayoutDesc)

            globalBindingLayoutDesc = pyd.BindingLayoutDesc()
            globalBindingLayoutDesc.visibility = pyd.ShaderType.All
            globalBindingLayoutDesc.bindings = [
                pyd.BindingLayoutItem.VolatileConstantBuffer(_BINDING_CONSTANTS),
                pyd.BindingLayoutItem.RayTracingAccelStruct(_BINDING_SCENE_BVH),
                pyd.BindingLayoutItem.StructuredBuffer_SRV(_BINDING_INSTANCE_BUFFER),
                pyd.BindingLayoutItem.StructuredBuffer_SRV(_BINDING_GEOMETRY_BUFFER),
                pyd.BindingLayoutItem.StructuredBuffer_SRV(_BINDING_MATERIAL_BUFFER),
                pyd.BindingLayoutItem.StructuredBuffer_SRV(_BINDING_PARTICLE_INFO_BUFFER),
                pyd.BindingLayoutItem.Sampler(_BINDING_MATERIAL_SAMPLER),
                pyd.BindingLayoutItem.Texture_UAV(_BINDING_OUTPUT_UAV),
            ]
            self.bindingLayout = device.createBindingLayout(globalBindingLayoutDesc)

            self.descriptorTableManager = pyd.DescriptorTableManager(device, self.bindlessLayout)

            self.textureCache = pyd.TextureCache(device, self.rootFS, self.descriptorTableManager)
            self.m_TextureCache = self.textureCache

            self.commandList = device.createCommandList()

            self.CreateParticleMesh()
            self.particles = [ParticleEntity() for _ in range(_MAX_PARTICLES)]

            self.environmentMap = self.textureCache.LoadTextureFromFileDeferred(Path("/media/rt_particles/environment-map.dds"), False)
            self.smokeTexture = self.textureCache.LoadTextureFromFileDeferred(Path("/media/rt_particles/smoke-particle.png"), True)
            self.logoTexture = self.textureCache.LoadTextureFromFileDeferred(Path("/media/nvidia-logo.png"), True)

            # Runs LoadScene() (below) synchronously, followed by the base ApplicationBase's
            # default SceneLoaded() (texture-cache finalization only -- this class doesn't
            # override SceneLoaded(), matching the C++ original). m_CommonPasses/m_TextureCache
            # were wired into the base above so that inherited SceneLoaded() finalizes correctly.
            self.SetAsynchronousLoadingEnabled(False)
            self.BeginLoadingScene(self.rootFS, Path("/media/rt_particles/ParticleScene.gltf"))
            if not self.IsSceneLoaded():
                return False
            assert self.scene is not None

            sceneGraph = self.scene.GetSceneGraph()
            assert self.particleInstance is not None
            sceneGraph.AttachLeafNode(sceneGraph.GetRootNode(), self.particleInstance)
            self.scene.RefreshSceneGraph(0)

            emitterNode = sceneGraph.FindNode(Path("/Emitter"))
            if emitterNode is not None:
                self.ui.emitterPosition = emitterNode.GetWorldPosition()

            self.scene.FinishedLoading(self.GetFrameIndex())

            ex, ey, ez = self.ui.emitterPosition
            self.camera.SetTargetPosition(ex, ey + 2.0, ez)
            self.camera.SetDistance(6.0)
            self.camera.SetRotation(math.radians(225.0), math.radians(20.0))
            self.camera.SetMoveSpeed(3.0)

            self.constantBuffer = device.createBuffer(
                pyd.CreateVolatileConstantBufferDesc(_GLOBAL_CONSTANTS_SIZE, "LightingConstants", 16)
            )

            self.commandList.open()

            self.CreateAccelStructs(self.commandList)
            self.BuildParticleIntersectionBLAS(self.commandList)

            self.commandList.close()
            device.executeCommandList(self.commandList)

            device.waitForIdle()

            return True

        # Creates the buffers and initializes engine structures to attach a procedural particle
        # mesh to the scene.
        def CreateParticleMesh(self: RayTracedParticles) -> None:
            assert self.descriptorTableManager is not None
            device = self.GetDevice()

            self.particleBuffers = pyd.BufferGroup()

            positionByteOffset = 0
            positionByteSize = _MAX_PARTICLES * _VERTICES_PER_QUAD * _SIZEOF_FLOAT3
            texcoordByteOffset = positionByteOffset + positionByteSize
            texcoordByteSize = _MAX_PARTICLES * _VERTICES_PER_QUAD * _SIZEOF_FLOAT2
            self.particleBuffers.setVertexBufferRange(pyd.VertexAttribute.Position, positionByteOffset, positionByteSize)
            self.particleBuffers.setVertexBufferRange(pyd.VertexAttribute.TexCoord1, texcoordByteOffset, texcoordByteSize)

            # bufferDesc is reused across all three buffers below (index/vertex/particle-info),
            # matching the C++ original -- so the particle-info buffer also inherits the dual
            # ShaderResource|AccelStructBuildInput initial state and isAccelStructBuildInput
            # flag from the index/vertex buffers, even though it isn't itself a BLAS input.
            bufferDesc = pyd.BufferDesc()
            bufferDesc.byteSize = _MAX_PARTICLES * _INDICES_PER_QUAD * _SIZEOF_UINT32
            bufferDesc.debugName = "ParticleIndices"
            bufferDesc.canHaveRawViews = True
            bufferDesc.initialState = pyd.ResourceStates.ShaderResource | pyd.ResourceStates.AccelStructBuildInput
            bufferDesc.keepInitialState = True
            bufferDesc.isAccelStructBuildInput = True
            self.particleBuffers.indexBuffer = device.createBuffer(bufferDesc)

            bufferDesc.byteSize = texcoordByteOffset + texcoordByteSize
            bufferDesc.debugName = "ParticleVertices"
            self.particleBuffers.vertexBuffer = device.createBuffer(bufferDesc)

            self.particleBuffers.indexBufferDescriptor = self.descriptorTableManager.CreateDescriptorHandle(
                pyd.BindingSetItem.RawBuffer_SRV(0, self.particleBuffers.indexBuffer)
            )
            self.particleBuffers.vertexBufferDescriptor = self.descriptorTableManager.CreateDescriptorHandle(
                pyd.BindingSetItem.RawBuffer_SRV(0, self.particleBuffers.vertexBuffer)
            )

            self.particleMaterial = pyd.Material()
            self.particleMaterial.domain = pyd.MaterialDomain.AlphaBlended

            self.particleGeometry = pyd.MeshGeometry()
            self.particleGeometry.material = self.particleMaterial

            # Set numVertices/numIndices to the max possible up front so the first BLAS built
            # for this mesh (in CreateAccelStructs) is already large enough for any frame.
            self.particleGeometry.numVertices = _MAX_PARTICLES * _VERTICES_PER_QUAD
            self.particleGeometry.numIndices = _MAX_PARTICLES * _INDICES_PER_QUAD

            self.particleMesh = pyd.MeshInfo()
            self.particleMesh.buffers = self.particleBuffers
            self.particleMesh.geometries = [self.particleGeometry]
            self.particleMesh.name = "ParticleMesh"

            self.particleInstance = pyd.MeshInstance(self.particleMesh)

            bufferDesc.byteSize = _MAX_PARTICLES * _SIZEOF_PARTICLE_INFO
            bufferDesc.canHaveRawViews = False
            bufferDesc.structStride = _SIZEOF_PARTICLE_INFO
            bufferDesc.debugName = "ParticleInfoBuffer"
            self.particleInfoBuffer = device.createBuffer(bufferDesc)

        # Updates particle geometry -- called before rendering every frame.
        def BuildParticleGeometry(self: RayTracedParticles, commandList: pyd.CommandList) -> None:
            assert self.particleBuffers is not None
            assert self.particleGeometry is not None
            assert self.particleMesh is not None
            assert self.particleMaterial is not None
            assert self.particleInfoBuffer is not None

            cameraForward = self.camera.GetDir()
            cameraUp = self.camera.GetUp()

            # To demonstrate beam orientation, vertical sprites free to rotate around the
            # world-space Y axis, simulating what old Doom-like games used.
            if self.ui.orientationMode == _ORIENTATION_MODE_BEAM:
                if abs(cameraForward[1]) > 0.999:
                    cameraForward = cameraUp
                cameraForward = VNormalize((cameraForward[0], 0.0, cameraForward[2]))
                cameraUp = (0.0, 1.0, 0.0)

            cameraRight = VCross(cameraForward, cameraUp)

            indices: list[int] = []
            positions: list[float] = []
            texcoords: list[float] = []
            particleInfoBytes = bytearray()

            textureIndex = self.particleMaterial.baseOrDiffuseTexture.bindlessDescriptorIndex \
                if self.particleMaterial.baseOrDiffuseTexture is not None else -1

            numParticles = 0
            for particle in self.particles:
                if not particle.active:
                    continue

                baseVertex = numParticles * _VERTICES_PER_QUAD
                indices += [
                    baseVertex + 0, baseVertex + 1, baseVertex + 2,
                    baseVertex + 0, baseVertex + 2, baseVertex + 3,
                ]

                rotation = 0.0 if self.ui.orientationMode == _ORIENTATION_MODE_BEAM else particle.rotation
                localRightX, localRightY = math.cos(rotation), math.sin(rotation)
                localUpX, localUpY = -localRightY, localRightX
                worldRight = VAdd(VScale(cameraRight, localRightX), VScale(cameraUp, localRightY))
                worldUp = VAdd(VScale(cameraRight, localUpX), VScale(cameraUp, localUpY))

                p = particle.position
                r = particle.radius
                v0 = VAdd(VSub(p, VScale(worldRight, r)), VScale(worldUp, r))
                v1 = VAdd(VAdd(p, VScale(worldRight, r)), VScale(worldUp, r))
                v2 = VSub(VAdd(p, VScale(worldRight, r)), VScale(worldUp, r))
                v3 = VSub(VSub(p, VScale(worldRight, r)), VScale(worldUp, r))
                positions += [*v0, *v1, *v2, *v3]
                texcoords += [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]

                inverseRadius = 1.0 / r
                particleInfoBytes += struct.pack(
                    "<3f f 3f f 3f i 3f f",
                    p[0], p[1], p[2], particle.rotation,
                    worldRight[0], worldRight[1], worldRight[2], inverseRadius,
                    worldUp[0], worldUp[1], worldUp[2], textureIndex,
                    particle.color[0], particle.color[1], particle.color[2], particle.opacity,
                )

                numParticles += 1

            self.particleGeometry.numIndices = numParticles * _INDICES_PER_QUAD
            self.particleGeometry.numVertices = numParticles * _VERTICES_PER_QUAD

            if numParticles > 0:
                positionRange = self.particleBuffers.getVertexBufferRange(pyd.VertexAttribute.Position)
                texcoordRange = self.particleBuffers.getVertexBufferRange(pyd.VertexAttribute.TexCoord1)
                assert self.particleBuffers.indexBuffer is not None
                assert self.particleBuffers.vertexBuffer is not None
                commandList.writeBuffer(self.particleBuffers.indexBuffer, struct.pack(f"<{len(indices)}I", *indices))
                commandList.writeBuffer(self.particleBuffers.vertexBuffer, struct.pack(f"<{len(positions)}f", *positions), positionRange.byteOffset)
                commandList.writeBuffer(self.particleBuffers.vertexBuffer, struct.pack(f"<{len(texcoords)}f", *texcoords), texcoordRange.byteOffset)
                commandList.writeBuffer(self.particleInfoBuffer, bytes(particleInfoBytes))

            blasDesc = pyd.AccelStructDesc()
            self.GetMeshBlasDesc(self.particleMesh, blasDesc)
            assert self.particleMesh.accelStruct is not None
            pyd.BuildBottomLevelAccelStruct(commandList, self.particleMesh.accelStruct, blasDesc)

        def BuildParticleIntersectionBLAS(self: RayTracedParticles, commandList: pyd.CommandList) -> None:
            # Only need to create and build the BLAS once, it's immutable.
            if self.particleIntersectionBLAS is not None:
                return

            aabbBufferDesc = pyd.BufferDesc()
            aabbBufferDesc.byteSize = 6 * 4  # sizeof(nvrhi::rt::GeometryAABB): 6 floats
            aabbBufferDesc.initialState = pyd.ResourceStates.CopyDest
            aabbBufferDesc.keepInitialState = True
            aabbBufferDesc.isAccelStructBuildInput = True
            aabbBuffer = self.GetDevice().createBuffer(aabbBufferDesc)

            commandList.writeBuffer(aabbBuffer, struct.pack("<6f", -1.0, -1.0, -1.0, 1.0, 1.0, 1.0))

            blasDesc = pyd.AccelStructDesc()
            blasDesc.isTopLevel = False
            blasDesc.debugName = "ParticleIntersectionBLAS"
            aabbs = pyd.GeometryAABBs()
            aabbs.setBuffer(aabbBuffer)
            aabbs.setCount(1)
            geometryDesc = pyd.GeometryDesc()
            geometryDesc.setAABBs(aabbs)
            blasDesc.bottomLevelGeometries = [geometryDesc]

            self.particleIntersectionBLAS = self.GetDevice().createAccelStruct(blasDesc)
            pyd.BuildBottomLevelAccelStruct(commandList, self.particleIntersectionBLAS, blasDesc)

        def LoadScene(self: RayTracedParticles, fs: pyd.IFileSystem, sceneFileName: Path) -> bool:
            assert self.shaderFactory is not None
            assert self.textureCache is not None
            assert self.descriptorTableManager is not None
            device = self.GetDevice()
            scene = pyd.Scene(device, self.shaderFactory, fs, self.textureCache, self.descriptorTableManager)
            if scene.Load(sceneFileName):
                self.scene = scene
                return True
            return False

        def KeyboardUpdate(self: RayTracedParticles, key: int, scancode: int, action: int, mods: int) -> bool:
            self.camera.KeyboardUpdate(key, scancode, action, mods)
            if key == 32 and action == 1:  # GLFW_KEY_SPACE, GLFW_PRESS
                self.ui.enableAnimations = not self.ui.enableAnimations
                return True
            return True

        def MousePosUpdate(self: RayTracedParticles, xpos: float, ypos: float) -> bool:
            self.camera.MousePosUpdate(xpos, ypos)
            return True

        def MouseButtonUpdate(self: RayTracedParticles, button: int, action: int, mods: int) -> bool:
            self.camera.MouseButtonUpdate(button, action, mods)
            return True

        def MouseScrollUpdate(self: RayTracedParticles, xoffset: float, yoffset: float) -> bool:
            self.camera.MouseScrollUpdate(xoffset, yoffset)
            return True

        def GetShaderFactory(self: RayTracedParticles) -> pyd.ShaderFactory:
            assert self.shaderFactory is not None
            return self.shaderFactory

        def Animate(self: RayTracedParticles, elapsedTimeSeconds: float) -> None:
            self.camera.Animate(elapsedTimeSeconds)

            if self.IsSceneLoaded() and self.ui.enableAnimations:
                self.wallclockTime += elapsedTimeSeconds

                # Animate the live particles, also find the index of the first empty particle
                # slot for spawning later.
                firstEmptyParticle = -1
                for i, particle in enumerate(self.particles):
                    if particle.active:
                        particle.Animate(elapsedTimeSeconds)
                    if not particle.active and firstEmptyParticle < 0:
                        firstEmptyParticle = i

                particlesPerSecond = 20.0
                particleEmissionPeriod = 1.0 / particlesPerSecond

                # Emit a new particle if enough time has passed since the last emission.
                if self.wallclockTime - self.lastEmitTime > particleEmissionPeriod and firstEmptyParticle >= 0:
                    self.particles[firstEmptyParticle].Emit(self.ui.emitterPosition)
                    self.lastEmitTime = self.wallclockTime

            self.GetDeviceManager().SetInformativeWindowTitle(WINDOW_TITLE)

        def CreateComputePipeline(self: RayTracedParticles, shaderFactory: pyd.ShaderFactory) -> bool:
            device = self.GetDevice()
            api = device.getGraphicsAPI()

            shaderPath = folder / "shaders" / "rt_particles" / "rt_particles.hlsl"
            source = shaderPath.read_text(encoding="utf-8")
            # MLAB_FRAGMENTS is guarded by #ifndef in mlab.hlsli (defaults to 4) -- prepend an
            # override before it's #include-d, matching the C++ original's ShaderMacro define
            # without needing macro support in the compile binding.
            source = f"#define MLAB_FRAGMENTS {self.ui.mlabFragments}\n" + source

            donutShaderIncludeRoot = folder / "extern" / "donut" / "include"

            try:
                assert pyd.CompileShader is not None
                csBytecode = pyd.CompileShader(
                    source, "main", pyd.ShaderType.Compute, api, sourceName=shaderPath.name,
                    includePaths=[str(shaderPath.parent), str(donutShaderIncludeRoot)],
                )
            except RuntimeError as e:
                pyd.log.fatal(f"Shader compilation failed: {e}")
                return False

            self.computeShader = device.createShader(csBytecode, "main", pyd.ShaderType.Compute)
            if not self.computeShader:
                return False

            assert self.bindingLayout is not None
            assert self.bindlessLayout is not None
            pipelineDesc = pyd.ComputePipelineDesc()
            pipelineDesc.CS = self.computeShader
            pipelineDesc.addBindingLayout(self.bindingLayout)
            pipelineDesc.addBindingLayout(self.bindlessLayout)
            self.computePipeline = device.createComputePipeline(pipelineDesc)

            return self.computePipeline is not None

        def GetMeshBlasDesc(self: RayTracedParticles, mesh: pyd.MeshInfo, blasDesc: pyd.AccelStructDesc) -> None:
            assert mesh.buffers is not None
            blasDesc.isTopLevel = False
            blasDesc.debugName = mesh.name

            geometryDescs = []
            positionRange = mesh.buffers.getVertexBufferRange(pyd.VertexAttribute.Position)
            for geometry in mesh.geometries:
                assert geometry.material is not None
                triangles = pyd.GeometryTriangles()
                triangles.indexBuffer = mesh.buffers.indexBuffer
                triangles.indexOffset = (mesh.indexOffset + geometry.indexOffsetInMesh) * _SIZEOF_UINT32
                triangles.indexFormat = pyd.Format.R32_UINT
                triangles.indexCount = geometry.numIndices
                triangles.vertexBuffer = mesh.buffers.vertexBuffer
                triangles.vertexOffset = (mesh.vertexOffset + geometry.vertexOffsetInMesh) * _SIZEOF_FLOAT3 + positionRange.byteOffset
                triangles.vertexFormat = pyd.Format.RGB32_FLOAT
                triangles.vertexStride = _SIZEOF_FLOAT3
                triangles.vertexCount = geometry.numVertices

                geometryDesc = pyd.GeometryDesc()
                geometryDesc.setTriangles(triangles)
                geometryDesc.flags = pyd.GeometryFlags.Opaque if geometry.material.domain == pyd.MaterialDomain.Opaque else pyd.GeometryFlags.None_
                geometryDescs.append(geometryDesc)

            blasDesc.bottomLevelGeometries = geometryDescs
            blasDesc.buildFlags = pyd.AccelStructBuildFlags.PreferFastTrace

        def CreateAccelStructs(self: RayTracedParticles, commandList: pyd.CommandList) -> None:
            assert self.scene is not None
            for mesh in self.scene.GetSceneGraph().GetMeshes():
                blasDesc = pyd.AccelStructDesc()
                self.GetMeshBlasDesc(mesh, blasDesc)

                accelStruct = self.GetDevice().createAccelStruct(blasDesc)

                # Build the BLAS if it's not the particle mesh -- that one's dynamic and gets
                # (re)built every frame in BuildParticleGeometry.
                if mesh.name != "ParticleMesh":
                    pyd.BuildBottomLevelAccelStruct(commandList, accelStruct, blasDesc)

                mesh.accelStruct = accelStruct

            tlasDesc = pyd.AccelStructDesc()
            tlasDesc.isTopLevel = True
            # The TLAS includes the scene geometries (including the single instance for
            # geometric particles) and many instances of the intersection BLAS, one instance
            # per particle.
            numSceneInstances = len(self.scene.GetSceneGraph().GetMeshInstances())
            tlasDesc.topLevelMaxInstances = numSceneInstances + _MAX_PARTICLES
            self.topLevelAS = self.GetDevice().createAccelStruct(tlasDesc)

        def BuildTLAS(self: RayTracedParticles, commandList: pyd.CommandList, frameIndex: int) -> None:
            assert self.scene is not None
            assert self.particleIntersectionBLAS is not None
            instances: list[pyd.InstanceDesc] = []

            # Regular instances for scene meshes.
            for instance in self.scene.GetSceneGraph().GetMeshInstances():
                mesh = instance.GetMesh()
                blas = mesh.accelStruct
                assert blas is not None
                node = instance.GetNode()
                assert node is not None

                instanceDesc = pyd.InstanceDesc()
                instanceDesc.setBLAS(blas)
                instanceDesc.setInstanceMask(_INSTANCE_MASK_PARTICLE_GEOMETRY if mesh.name == "ParticleMesh" else _INSTANCE_MASK_OPAQUE)
                instanceDesc.setInstanceID(instance.GetInstanceIndex())
                instanceDesc.setTransformFromNode(node)
                instances.append(instanceDesc)

            # Intersection instances for active particles.
            particleIndex = 0
            for particle in self.particles:
                if not particle.active:
                    continue

                px, py, pz = particle.position
                instanceDesc = pyd.InstanceDesc()
                instanceDesc.setBLAS(self.particleIntersectionBLAS)
                instanceDesc.setInstanceMask(_INSTANCE_MASK_INTERSECTION_PARTICLE)
                instanceDesc.setInstanceID(particleIndex)
                # Scale and translate the AABB to make it contain the particle billboard.
                instanceDesc.setTransformScaleTranslation(particle.radius, particle.radius, particle.radius, px, py, pz)
                instances.append(instanceDesc)

                particleIndex += 1

            assert self.topLevelAS is not None
            commandList.buildTopLevelAccelStruct(self.topLevelAS, instances)

        def BackBufferResizing(self: RayTracedParticles) -> None:
            self.colorBuffer = None
            assert self.bindingCache is not None
            self.bindingCache.Clear()

        def Render(self: RayTracedParticles, framebuffer: pyd.Framebuffer) -> None:
            assert self.commandList is not None
            assert self.scene is not None
            assert self.commonPasses is not None
            assert self.particleMaterial is not None
            assert self.shaderFactory is not None

            fbinfo = framebuffer.getFramebufferInfo()

            if self.ui.updatePipeline:
                if not self.CreateComputePipeline(self.shaderFactory):
                    return
                self.ui.updatePipeline = False

            if self.colorBuffer is None:
                desc = pyd.TextureDesc()
                desc.width = fbinfo.width
                desc.height = fbinfo.height
                desc.isUAV = True
                desc.keepInitialState = True
                desc.format = pyd.Format.RGBA16_FLOAT
                desc.initialState = pyd.ResourceStates.UnorderedAccess
                desc.debugName = "ColorBuffer"
                self.colorBuffer = self.GetDevice().createTexture(desc)

                assert self.constantBuffer is not None
                assert self.topLevelAS is not None
                assert self.particleInfoBuffer is not None
                assert self.bindingLayout is not None

                bindingSetDesc = pyd.BindingSetDesc()
                bindingSetDesc.bindings = [
                    pyd.BindingSetItem.ConstantBuffer(_BINDING_CONSTANTS, self.constantBuffer),
                    pyd.BindingSetItem.RayTracingAccelStruct(_BINDING_SCENE_BVH, self.topLevelAS),
                    pyd.BindingSetItem.StructuredBuffer_SRV(_BINDING_INSTANCE_BUFFER, self.scene.GetInstanceBuffer()),
                    pyd.BindingSetItem.StructuredBuffer_SRV(_BINDING_GEOMETRY_BUFFER, self.scene.GetGeometryBuffer()),
                    pyd.BindingSetItem.StructuredBuffer_SRV(_BINDING_MATERIAL_BUFFER, self.scene.GetMaterialBuffer()),
                    pyd.BindingSetItem.StructuredBuffer_SRV(_BINDING_PARTICLE_INFO_BUFFER, self.particleInfoBuffer),
                    pyd.BindingSetItem.Sampler(_BINDING_MATERIAL_SAMPLER, self.commonPasses.m_AnisotropicWrapSampler),
                    pyd.BindingSetItem.Texture_UAV(_BINDING_OUTPUT_UAV, self.colorBuffer),
                ]
                self.bindingSet = self.GetDevice().createBindingSet(bindingSetDesc, self.bindingLayout)

            particleTexture = self.smokeTexture if self.ui.particleTexture == _PARTICLE_TEXTURE_SMOKE else self.logoTexture
            if self.particleMaterial.baseOrDiffuseTexture is not particleTexture:
                self.particleMaterial.baseOrDiffuseTexture = particleTexture
                self.particleMaterial.dirty = True

            windowViewport = pyd.Viewport(float(fbinfo.width), float(fbinfo.height))
            self.view.SetViewport(windowViewport)
            verticalFovRadians = math.pi * 0.25
            self.view.SetMatricesFromCamera(self.camera, windowViewport.width() / windowViewport.height(), verticalFovRadians, 0.1)
            self.view.UpdateCache()
            self.camera.SetView(self.view)

            self.commandList.open()

            if self.ui.enableAnimations or self.ui.alwaysUpdateOrientation or self.particleMaterial.dirty:
                self.scene.Refresh(self.commandList, self.GetFrameIndex())
                self.BuildParticleGeometry(self.commandList)
                self.BuildTLAS(self.commandList, self.GetFrameIndex())

            environmentMapTextureIndex = self.environmentMap.bindlessDescriptorIndex if self.environmentMap is not None else -1
            constants = self.view.FillPlanarViewConstants() + struct.pack(
                "<f I I I i",
                verticalFovRadians / windowViewport.height(),
                1 if self.ui.reorientParticlesInPrimaryRays else 0,
                1 if self.ui.reorientParticlesInSecondaryRays else 0,
                self.ui.orientationMode,
                environmentMapTextureIndex,
            )

            assert self.constantBuffer is not None
            assert self.bindingSet is not None
            assert self.descriptorTableManager is not None

            self.commandList.writeBuffer(self.constantBuffer, constants)

            state = pyd.ComputeState()
            state.pipeline = self.computePipeline
            state.addBindingSet(self.bindingSet)
            state.addBindingSet(self.descriptorTableManager.GetDescriptorTable())
            self.commandList.setComputeState(state)

            self.commandList.dispatch(
                (fbinfo.width + 15) // 16,
                (fbinfo.height + 15) // 16,
            )

            self.commonPasses.BlitTexture(self.commandList, framebuffer, self.colorBuffer, self.bindingCache)

            self.commandList.close()
            self.GetDevice().executeCommandList(self.commandList)

    class UserInterface(pyd.ImGui_Renderer):
        def __init__(self: UserInterface, deviceManager: pyd.DeviceManager, ui: UIData) -> None:
            super().__init__(deviceManager)
            self.ui = ui
            pyd.ImGui.DisableIniFile()

        def buildUI(self: UserInterface) -> None:
            pyd.ImGui.SetNextWindowPos(10.0, 10.0)
            pyd.ImGui.Begin("Settings", _IMGUI_WINDOW_FLAGS_ALWAYS_AUTO_RESIZE)

            _, self.ui.enableAnimations = pyd.ImGui.Checkbox("Animate particles (Space)", self.ui.enableAnimations)
            _, self.ui.alwaysUpdateOrientation = pyd.ImGui.Checkbox("Update orientation when paused", self.ui.alwaysUpdateOrientation)
            pyd.ImGui.Separator()

            pyd.ImGui.Text("Orientation mode:")
            pyd.ImGui.Indent()
            _, self.ui.orientationMode = pyd.ImGui.Combo(
                "##orientationMode", self.ui.orientationMode,
                ["Accumulated Vector Transform", "Quaternion Rotation", "Beam or Vertical Sprite", "Basis (RTG2)"],
            )
            pyd.ImGui.Unindent()
            pyd.ImGui.Separator()

            pyd.ImGui.Text("Reorient particles:")
            pyd.ImGui.Indent()
            _, self.ui.reorientParticlesInPrimaryRays = pyd.ImGui.Checkbox("In primary rays", self.ui.reorientParticlesInPrimaryRays)
            _, self.ui.reorientParticlesInSecondaryRays = pyd.ImGui.Checkbox("In secondary rays", self.ui.reorientParticlesInSecondaryRays)
            pyd.ImGui.Unindent()
            pyd.ImGui.Separator()

            allowedMlabFragmentCounts = (1, 2, 4, 8)
            pyd.ImGui.PushItemWidth(40.0)
            newFragmentCount = self.ui.mlabFragments
            if pyd.ImGui.BeginCombo("Blending fragments", str(self.ui.mlabFragments)):
                for fragmentCount in allowedMlabFragmentCounts:
                    if pyd.ImGui.Selectable(str(fragmentCount), newFragmentCount == fragmentCount):
                        newFragmentCount = fragmentCount
                pyd.ImGui.EndCombo()
            pyd.ImGui.PopItemWidth()
            if newFragmentCount != self.ui.mlabFragments:
                self.ui.mlabFragments = newFragmentCount
                self.ui.updatePipeline = True
            pyd.ImGui.Separator()

            pyd.ImGui.Text("Emitter position:")
            pyd.ImGui.Indent()
            ex, ey, ez = self.ui.emitterPosition
            _, ex, ey, ez = pyd.ImGui.DragFloat3("##emitterPosition", ex, ey, ez, 0.01)
            self.ui.emitterPosition = (ex, ey, ez)
            pyd.ImGui.Unindent()

            pyd.ImGui.Text("Particle texture:")
            pyd.ImGui.Indent()
            _, self.ui.particleTexture = pyd.ImGui.Combo("##particleTexture", self.ui.particleTexture, ["Smoke", "Logo"])
            pyd.ImGui.Unindent()

            pyd.ImGui.End()

    is_debug = "-debug" in sys.argv

    # On Windows, Donut's default log config shows errors as a blocking MessageBox instead
    # of printing them -- redirect to the console so failures are actually visible here.
    pyd.log.ConsoleApplicationMode()

    api = pyd.GetGraphicsAPIFromCommandLine(sys.argv)
    print(f"Selected Graphics API: {api}")

    deviceManager = pyd.DeviceManager.Create(api)
    if not deviceManager:
        pyd.log.fatal("Failed to create DeviceManager.")
        sys.exit(1)
    else:
        print("DeviceManager created successfully.")

    deviceParams = pyd.DeviceCreationParameters()
    deviceParams.enableRayTracingExtensions = True
    if is_debug:
        print("Debug mode is enabled.")
        deviceParams.enableDebugRuntime = True
        deviceParams.enableNvrhiValidationLayer = True

    if not deviceManager.CreateWindowDeviceAndSwapChain(deviceParams, WINDOW_TITLE):
        pyd.log.fatal("Cannot initialize a graphics device with the requested parameters")
        sys.exit(1)

    if not deviceManager.GetDevice().queryFeatureSupport(pyd.Feature.RayQuery):
        pyd.log.fatal("The graphics device does not support Ray Queries")
        sys.exit(1)

    uiData = UIData()
    example = RayTracedParticles(deviceManager, uiData)
    gui = UserInterface(deviceManager, uiData)

    if example.Init() and gui.Init(example.GetShaderFactory()):
        deviceManager.AddRenderPassToBack(example)
        deviceManager.AddRenderPassToBack(gui)
        deviceManager.RunMessageLoop()
        deviceManager.RemoveRenderPass(gui)
        deviceManager.RemoveRenderPass(example)

    deviceManager.Shutdown()

    if is_debug:
        deviceManager.ReportLiveObjects()

    del deviceManager

    print("Done.")
