# Arm 3D Example

Run either launcher from the repository root:

```bash
PYTHONPATH=python python examples/py/arm3d.py
./build/cpp/examples/rti_demo_ui_arm3d
```

Both launchers serve this directory as the application-owned `static_root`.
The page uses `/sdk/client.js` for v2 snapshots and opts into the shared
`/sdk/runtime3d.js` renderer. No DDS installation or Node development server
is needed at runtime.

The fixture model is a GLB with stable paths `Arm/Base`, `Arm/Shoulder`,
`Arm/Elbow`, `Arm/Wrist`, and `Arm/Tool`. Paths are local transforms in a
right-handed, Y-up glTF coordinate system and translations are meters. The
application owns conversion from domain joint values to quaternions; the SDK
only transports generic transforms.

Replace the fixture with an application model only after checking its node
names, hierarchy, pivots, materials, and coordinate units. Keep the asset as a
same-origin `.glb` under this static root. GLTF JSON, remote URLs, external
buffers, data URLs, and query strings are intentionally rejected.

The mock launchers update five deterministic targets every 200 ms. A real
application can replace that loop with DDS subscriptions and retain the same
scene contract. If WebGL or model loading is unavailable, the renderer keeps
the node list and transform/status readout available as ordinary HTML.
