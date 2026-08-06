import { createClient } from '/sdk/client.js';

const host = document.getElementById('arm3d-scene');
const status = document.getElementById('arm3d-status');
const cycle = document.getElementById('arm3d-cycle');
const readout = document.getElementById('arm3d-nodes');
const client = createClient();
let scene;

function renderReadout(component) {
  scene = component;
  cycle.textContent = String(component.revision || 0);
  readout.replaceChildren();
  for (const node of component.data.nodes || []) {
    const item = document.createElement('p');
    item.textContent = `${node.id}: ${node.status} (${node.position.map((value) => value.toFixed(2)).join(', ')})`;
    readout.appendChild(item);
  }
}

async function render(component) {
  renderReadout(component);
  try {
    const renderer = await import('/sdk/runtime3d.js');
    await renderer.reconcileScene3d(component, host, {
      reducedMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
      onLoadState: (state) => { status.textContent = state === 'loaded' ? 'Online' : state; },
      onSelection: (selection) => selection
    });
  } catch (error) {
    status.textContent = 'Fallback';
    host.textContent = `3D renderer unavailable: ${error.message}`;
  }
}

host.addEventListener('scene3dselect', (event) => {
  status.textContent = event.detail.selected ? `${event.detail.nodeId} selected` : 'Online';
});
client.subscribe((snapshot) => {
  const components = (snapshot?.cards || []).flatMap((card) => card.components || []);
  const next = components.find((component) => component.type === 'scene3d');
  if (next) render(next);
});
client.start();
