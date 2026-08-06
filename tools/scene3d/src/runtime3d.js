import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const assets = new Map();
const scenes = new Map();

function statusColor(status) {
  return status === "danger" ? 0xf06b6b : status === "warning" ? 0xf5bd57 : 0x55d6a5;
}

function setFallback(host, message, data, state) {
  host.classList.add("sdk-scene3d-fallback");
  const fallback = host.querySelector(".sdk-scene3d-fallback-text");
  if (fallback) {
    fallback.hidden = false;
    fallback.textContent = message;
  }
  const list = host.querySelector("[role=listbox]");
  if (list && data) renderList(list, data, state);
}

function hasVisibleFrame(renderer) {
  const gl = renderer?.getContext();
  if (!gl || gl.isContextLost()) return false;
  const pixel = new Uint8Array(4);
  gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
  return pixel.some((value) => value !== 0);
}

function renderList(list, data, state) {
  list.replaceChildren();
  const activeId = state?.selected || data.nodes?.[0]?.id;
  for (const node of data.nodes || []) {
    const option = document.createElement("div");
    option.id = `${data.asset}-${node.id}`.replace(/[^A-Za-z0-9_-]/g, "_");
    option.setAttribute("role", "option");
    option.tabIndex = activeId === node.id ? 0 : -1;
    option.setAttribute("aria-selected", String(state && state.selected === node.id));
    option.setAttribute("aria-label", `${node.id}, ${node.status}, ${node.visible ? "visible" : "hidden"}`);
    option.textContent = `${node.id} - ${node.status}`;
    option.dataset.nodeId = node.id;
    option.addEventListener("click", () => select(state, node.id));
    option.addEventListener("keydown", (event) => {
      const options = [...list.querySelectorAll('[role="option"]')];
      const index = options.indexOf(option);
      let next = index;
      if (event.key === "ArrowDown") next = Math.min(options.length - 1, index + 1);
      else if (event.key === "ArrowUp") next = Math.max(0, index - 1);
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = options.length - 1;
      else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        select(state, node.id);
        return;
      } else return;
      event.preventDefault();
      options[next]?.focus();
    });
    list.appendChild(option);
  }
}

function select(state, nodeId) {
  if (!state) return;
  state.selected = state.selected === nodeId ? null : nodeId;
  for (const option of state.host.querySelectorAll('[role="option"]')) {
    const selected = option.dataset.nodeId === state.selected;
    option.setAttribute("aria-selected", String(selected));
    option.tabIndex = selected ? 0 : -1;
  }
  state.host.dispatchEvent(new CustomEvent("scene3dselect", {
    bubbles: true,
    detail: { componentId: state.componentId, nodeId, selected: state.selected === nodeId }
  }));
  state.onSelection?.({ componentId: state.componentId, nodeId, selected: state.selected === nodeId });
  const live = state.host.querySelector(".sdk-scene3d-live");
  if (live) live.textContent = state.selected ? `${nodeId} selected` : `${nodeId} deselected`;
  if (state.root) {
    state.root.traverse((object) => {
      if (!object.isMesh || !object.userData.scene3dNodeId) return;
      object.material.emissive?.setHex(object.userData.scene3dNodeId === state.selected ? 0xffffff : 0x000000);
    });
  }
}

function pathObject(root, path) {
  let current = root;
  for (const raw of path.split("/")) {
    const name = raw.replaceAll("~1", "/").replaceAll("~0", "~");
    current = [...current.children].find((child) => child.name === name);
    if (!current) return null;
  }
  return current;
}

function disposeObject(root) {
  root?.traverse((object) => {
    object.geometry?.dispose();
    if (Array.isArray(object.material)) object.material.forEach((material) => material.dispose());
    else object.material?.dispose();
  });
}

function zoomToModel(state) {
  if (!state.root || !state.camera || !state.controls) return;
  const bounds = new THREE.Box3().setFromObject(state.root);
  const sphere = bounds.getBoundingSphere(new THREE.Sphere());
  const distance = Math.max(sphere.radius * 2.8, state.controls.minDistance * 2);
  const direction = state.camera.position.clone().sub(state.controls.target).normalize();
  state.controls.target.copy(sphere.center);
  state.camera.position.copy(sphere.center).add(direction.multiplyScalar(distance));
  state.controls.update();
}

function loadAsset(url) {
  let entry = assets.get(url);
  if (!entry) {
    entry = { refs: 0, promise: new Promise((resolve, reject) => new GLTFLoader().load(url, resolve, undefined, reject)) };
    assets.set(url, entry);
    entry.promise.catch(() => assets.delete(url));
  }
  entry.refs += 1;
  return entry.promise.then((gltf) => ({ gltf, release: () => releaseAsset(url, entry) }));
}

function releaseAsset(url, entry) {
  entry.refs -= 1;
  if (entry.refs > 0) return;
  assets.delete(url);
  entry.promise.then((gltf) => disposeObject(gltf.scene)).catch(() => {});
}

function makeHost(host) {
  host.className = "sdk-scene3d-host";
  host.replaceChildren();
  const toolbar = document.createElement("div");
  toolbar.className = "sdk-scene3d-toolbar";
  const reset = document.createElement("button");
  reset.type = "button"; reset.className = "sdk-button"; reset.textContent = "Reset camera";
  reset.dataset.action = "reset-camera";
  const zoom = document.createElement("button");
  zoom.type = "button"; zoom.className = "sdk-button"; zoom.textContent = "Zoom to model";
  zoom.dataset.action = "zoom-model";
  toolbar.append(reset, zoom);
  const body = document.createElement("div"); body.className = "sdk-scene3d-body";
  const viewport = document.createElement("div"); viewport.className = "sdk-scene3d-viewport";
  const canvas = document.createElement("canvas"); canvas.className = "sdk-scene3d-canvas";
  canvas.setAttribute("aria-label", "Interactive 3D scene");
  const loading = document.createElement("p"); loading.className = "sdk-scene3d-loading";
  loading.textContent = "Loading 3D model...";
  viewport.append(canvas, loading);
  const list = document.createElement("div"); list.className = "sdk-scene3d-list"; list.setAttribute("role", "listbox"); list.setAttribute("aria-label", "Scene nodes");
  const fallback = document.createElement("p"); fallback.className = "sdk-scene3d-fallback-text"; fallback.hidden = true;
  const live = document.createElement("p"); live.className = "sdk-scene3d-live"; live.setAttribute("aria-live", "polite");
  body.append(viewport, list, fallback, live); host.append(toolbar, body);
  return { canvas, list, fallback, live, loading, reset, zoom };
}

async function reconcileScene3d(component, host, context) {
  const data = component.data;
  let state = scenes.get(component.id);
  if (!state) {
    const elements = makeHost(host);
    state = { componentId: component.id, host, elements, selected: null, asset: null, assetUrl: null, loading: null, generation: 0, root: null, renderer: null, controls: null, animation: 0, targets: new Map(), onSelection: context.onSelection };
    scenes.set(component.id, state);
    elements.reset.addEventListener("click", () => state.controls?.reset());
    elements.zoom.addEventListener("click", () => zoomToModel(state));
  }
  state.onSelection = context.onSelection;
  renderList(state.elements.list, data, state);
  const showFailure = (error) => {
    context.onLoadState?.("failed");
    state.loading = null;
    cancelAnimationFrame(state.animation);
    state.resizeObserver?.disconnect();
    state.controls?.dispose();
    state.renderer?.dispose();
    state.asset?.release();
    disposeObject(state.root);
    state.renderer = null;
    state.controls = null;
    state.root = null;
    state.asset = null;
    state.elements.loading.hidden = true;
    setFallback(host, `3D model unavailable: ${error?.message || "WebGL rendering failed"}`, data, state);
    state.elements.live.textContent = "3D model failed to load";
    const retry = document.createElement("button");
    retry.type = "button"; retry.className = "sdk-button"; retry.textContent = "Retry model";
    retry.addEventListener("click", () => {
      state.generation += 1;
      state.assetUrl = null;
      reconcileScene3d(component, host, context);
    });
    state.elements.fallback.appendChild(retry);
  };
  if (state.assetUrl !== data.asset) {
    state.generation += 1;
    const generation = state.generation;
    state.asset?.release(); state.asset = null; state.root = null;
    state.assetUrl = data.asset;
    state.renderer?.dispose(); state.renderer = null; state.controls = null;
    try {
      state.loading = loadAsset(data.asset);
      const asset = await state.loading;
      state.loading = null;
      if (generation !== state.generation) { asset.release(); return; }
      state.asset = asset;
      const { gltf } = asset;
      state.root = gltf.scene.clone(true);
      state.root.traverse((object) => {
        if (object.isMesh) {
          object.material = Array.isArray(object.material) ? object.material.map((material) => material.clone()) : object.material.clone();
        }
      });
      const canvas = state.elements.canvas;
      state.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
      state.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      state.renderer.setClearColor(data.background);
      const scene = new THREE.Scene(); scene.background = new THREE.Color(data.background); scene.add(state.root);
      scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 2));
      const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 10000);
      camera.position.fromArray(data.camera.position);
      state.controls = new OrbitControls(camera, canvas); state.controls.target.fromArray(data.camera.target); state.controls.minDistance = data.camera.min_distance; state.controls.maxDistance = data.camera.max_distance; state.controls.update();
      state.controls.saveState();
      state.scene = scene; state.camera = camera;
      const resize = () => { const rect = canvas.getBoundingClientRect(); camera.aspect = Math.max(1, rect.width) / Math.max(1, rect.height); camera.updateProjectionMatrix(); state.renderer.setSize(Math.max(1, rect.width), Math.max(1, rect.height), false); };
      state.resize = resize; state.resizeObserver = new ResizeObserver(resize); state.resizeObserver.observe(canvas); resize();
      canvas.addEventListener("pointerdown", (event) => {
        if (!state.renderer || !state.scene || !state.camera) return;
        const rect = canvas.getBoundingClientRect();
        const pointer = new THREE.Vector2(
          ((event.clientX - rect.left) / rect.width) * 2 - 1,
          -((event.clientY - rect.top) / rect.height) * 2 + 1
        );
        const raycaster = new THREE.Raycaster();
        raycaster.setFromCamera(pointer, state.camera);
        const hit = raycaster.intersectObject(state.root, true)[0];
        const nodeId = hit?.object?.userData?.scene3dNodeId;
        if (nodeId) select(state, nodeId);
      });
      context.onLoadState?.("loaded");
      state.elements.loading.hidden = true;
      state.elements.live.textContent = "3D model loaded";
    } catch (error) {
      if (generation !== state.generation) return;
      showFailure(error);
      return;
    }
  }
  if (!state.root) return;
  host.classList.remove("sdk-scene3d-fallback");
  state.elements.fallback.hidden = true;
  for (const node of data.nodes || []) {
    const object = pathObject(state.root, node.path);
    if (!object) { setFallback(host, `Node path unavailable: ${node.path}`, data, state); continue; }
    object.userData.scene3dNodeId = node.id;
    object.visible = node.visible;
    const prior = state.targets.get(node.id);
    state.targets.set(node.id, { object, from: prior?.to || { position: object.position.clone(), quaternion: object.quaternion.clone(), scale: object.scale.clone() }, to: { position: new THREE.Vector3().fromArray(node.position), quaternion: new THREE.Quaternion().fromArray(node.rotation), scale: new THREE.Vector3().fromArray(node.scale) } });
    object.traverse((child) => { if (child.isMesh) { child.userData.scene3dNodeId = node.id; child.material.color.setHex(statusColor(node.status)); } });
  }
  for (const [nodeId, target] of state.targets) if (!data.nodes.some((node) => node.id === nodeId)) state.targets.delete(nodeId);
  cancelAnimationFrame(state.animation);
  const started = performance.now();
  const duration = Math.max(80, context.snapshotIntervalMs || 200);
  const animate = () => {
    const progress = context.reducedMotion ? 1 : Math.min(1, (performance.now() - started) / duration);
    for (const target of state.targets.values()) {
      target.object.position.lerpVectors(target.from.position, target.to.position, progress);
      target.object.quaternion.slerpQuaternions(target.from.quaternion, target.to.quaternion, progress);
      target.object.scale.lerpVectors(target.from.scale, target.to.scale, progress);
    }
    if (state.renderer && state.scene && state.camera) state.renderer.render(state.scene, state.camera);
    if (progress < 1 || state.renderer) state.animation = requestAnimationFrame(animate);
  };
  animate();
  if (state.renderer && !hasVisibleFrame(state.renderer)) {
    showFailure(new Error("WebGL context produced no visible frame"));
  }
}

function disposeScene3d(componentId) {
  const state = scenes.get(componentId); if (!state) return;
  state.generation += 1; cancelAnimationFrame(state.animation); state.resizeObserver?.disconnect(); state.controls?.dispose(); state.renderer?.dispose(); state.asset?.release(); disposeObject(state.root); scenes.delete(componentId);
}

export { reconcileScene3d, disposeScene3d };
