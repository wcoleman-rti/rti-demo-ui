import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const output = resolve(dirname(new URL(import.meta.url).pathname), "../../../examples/web/arm3d/models/scene3d-fixture.glb");
const positions = [];
const normals = [];
const indices = [];
const faces = [
  [[[-0.35, -0.18, 0.18], [0.35, -0.18, 0.18], [0.35, 0.18, 0.18], [-0.35, 0.18, 0.18]], [0, 0, 1]],
  [[[0.35, -0.18, -0.18], [-0.35, -0.18, -0.18], [-0.35, 0.18, -0.18], [0.35, 0.18, -0.18]], [0, 0, -1]],
  [[[-0.35, 0.18, 0.18], [0.35, 0.18, 0.18], [0.35, 0.18, -0.18], [-0.35, 0.18, -0.18]], [0, 1, 0]],
  [[[-0.35, -0.18, -0.18], [0.35, -0.18, -0.18], [0.35, -0.18, 0.18], [-0.35, -0.18, 0.18]], [0, -1, 0]],
  [[[-0.35, -0.18, -0.18], [-0.35, -0.18, 0.18], [-0.35, 0.18, 0.18], [-0.35, 0.18, -0.18]], [-1, 0, 0]],
  [[[0.35, -0.18, 0.18], [0.35, -0.18, -0.18], [0.35, 0.18, -0.18], [0.35, 0.18, 0.18]], [1, 0, 0]],
];

for (const [face, normal] of faces) {
  for (const position of face) {
    positions.push(...position);
    normals.push(...normal);
  }
}
for (let face = 0; face < 6; face += 1) {
  const start = face * 4;
  indices.push(start, start + 1, start + 2, start, start + 2, start + 3);
}

const positionBytes = Buffer.from(new Float32Array(positions).buffer);
const normalBytes = Buffer.from(new Float32Array(normals).buffer);
const indexBytes = Buffer.from(new Uint16Array(indices).buffer);
const bin = Buffer.concat([positionBytes, normalBytes, indexBytes]);
const json = JSON.stringify({
  asset: { version: "2.0", generator: "rti-demo-ui scene3d fixture" },
  scene: 0,
  scenes: [{ nodes: [0] }],
  nodes: [
    { name: "Arm", children: [1, 2, 3, 4, 5] },
    { name: "Base", mesh: 0, translation: [0, 0.25, 0] },
    { name: "Shoulder", mesh: 0, translation: [0, 0.85, 0] },
    { name: "Elbow", mesh: 0, translation: [0, 1.45, 0] },
    { name: "Wrist", mesh: 0, translation: [0, 2.05, 0] },
    { name: "Tool", mesh: 0, translation: [0, 2.65, 0], scale: [0.7, 0.7, 0.7] },
  ],
  meshes: [{ primitives: [{ attributes: { POSITION: 0, NORMAL: 1 }, indices: 2, material: 0 }] }],
  materials: [{ name: "fixture-blue", pbrMetallicRoughness: { baseColorFactor: [0.12, 0.55, 0.95, 1], metallicFactor: 0.15, roughnessFactor: 0.35 } }],
  accessors: [
    { bufferView: 0, componentType: 5126, count: 24, type: "VEC3", min: [-0.35, -0.18, -0.18], max: [0.35, 0.18, 0.18] },
    { bufferView: 1, componentType: 5126, count: 24, type: "VEC3" },
    { bufferView: 2, componentType: 5123, count: 36, type: "SCALAR", min: [0], max: [23] },
  ],
  bufferViews: [
    { buffer: 0, byteOffset: 0, byteLength: positionBytes.length, target: 34962 },
    { buffer: 0, byteOffset: positionBytes.length, byteLength: normalBytes.length, target: 34962 },
    { buffer: 0, byteOffset: positionBytes.length + normalBytes.length, byteLength: indexBytes.length, target: 34963 },
  ],
  buffers: [{ byteLength: bin.length }],
});
const jsonBytes = Buffer.from(json.padEnd(Math.ceil(json.length / 4) * 4, " "));
const header = Buffer.alloc(12);
header.writeUInt32LE(0x46546c67, 0);
header.writeUInt32LE(2, 4);
header.writeUInt32LE(12 + 8 + jsonBytes.length + 8 + bin.length, 8);
const jsonHeader = Buffer.alloc(8);
jsonHeader.writeUInt32LE(jsonBytes.length, 0);
jsonHeader.writeUInt32LE(0x4e4f534a, 4);
const binHeader = Buffer.alloc(8);
binHeader.writeUInt32LE(bin.length, 0);
binHeader.writeUInt32LE(0x004e4942, 4);
await mkdir(dirname(output), { recursive: true });
await writeFile(output, Buffer.concat([header, jsonHeader, jsonBytes, binHeader, bin]));
