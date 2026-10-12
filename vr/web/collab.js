// Shared sessions for the habitat viewer: presence avatars + design-review pins over the relay (relay/).
// Room codes live in the URL fragment (#room=...) so they are never sent as a query string or logged by
// static hosts; the code becomes the WebSocket path. Names and pin text are only ever rendered as text
// (canvas drawing / textContent), never as HTML.
import * as THREE from "three";

const PROD_RELAY = "wss://astro-usa-habitat-relay.astrobotany.workers.dev";   // set at deploy time
const LOCAL_RELAY = "ws://127.0.0.1:8797";
const POSE_HZ = 10;

function relayBase() {
  const q = new URLSearchParams(location.search).get("relay");
  if (q) return q.replace(/^http/, "ws");
  return ["localhost", "127.0.0.1"].includes(location.hostname) ? LOCAL_RELAY : PROD_RELAY;
}
const randomCode = () => Array.from(crypto.getRandomValues(new Uint8Array(9)), b => "abcdefghjkmnpqrstuvwxyz23456789"[b % 31]).join("");
const roomFromHash = () => new URLSearchParams(location.hash.slice(1)).get("room");
const palette = ["#e0a33a", "#3fb6a8", "#d1495b", "#6a4c93", "#2f9e44", "#1c7ed6", "#f76707"];

function label(text, color) {
  const c = document.createElement("canvas"); c.width = 256; c.height = 64;
  const g = c.getContext("2d");
  g.fillStyle = "rgba(20,24,30,0.75)"; g.fillRect(0, 0, 256, 64);
  g.fillStyle = color; g.fillRect(0, 0, 8, 64);
  g.fillStyle = "#fff"; g.font = "28px system-ui, sans-serif"; g.textBaseline = "middle";
  g.fillText(text.slice(0, 18), 18, 34);                     // canvas text: no HTML interpretation
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), depthTest: false }));
  s.scale.set(0.5, 0.125, 1);
  return s;
}

export function initCollab({ scene, camera, renderer, ui, getDigest }) {
  const state = { ws: null, id: null, peers: new Map(), pins: new Map(), mine: new Set(), pinMode: false,
                  name: "", color: palette[Math.floor(Math.random() * palette.length)], tries: 0, room: roomFromHash() };
  const root = new THREE.Group(); root.name = "collab"; scene.add(root);

  // ---- UI (built with DOM APIs; user text via textContent only)
  const box = document.createElement("div"); box.id = "collab";
  const title = document.createElement("strong"); title.textContent = "Shared session";
  const name = document.createElement("input"); name.placeholder = "Your name"; name.maxLength = 40;
  name.value = (() => { try { return localStorage.getItem("habitat.name") || ""; } catch { return ""; } })();
  const go = document.createElement("button"); go.textContent = state.room ? "Join session" : "Start shared session";
  const copy = document.createElement("button"); copy.textContent = "Copy invite link"; copy.hidden = true;
  const pinBtn = document.createElement("button"); pinBtn.textContent = "Add pin"; pinBtn.hidden = true;
  const status = document.createElement("div"); status.className = "collab-status";
  box.append(title, document.createElement("br"), name, go, copy, pinBtn, status);
  ui.append(box);
  const setStatus = t => { status.textContent = t; };
  setStatus(state.room ? "Invite link detected: enter a name and join." : "Walk through the model together.");

  go.onclick = () => {
    state.name = name.value.trim().slice(0, 40) || "guest";
    try { localStorage.setItem("habitat.name", state.name); } catch { /* storage may be blocked */ }
    if (!state.room) { state.room = randomCode(); history.replaceState(null, "", "#room=" + state.room); }
    go.hidden = true; name.disabled = true; copy.hidden = false; pinBtn.hidden = false;
    connect();
  };
  copy.onclick = async () => {
    const url = location.href;
    try { await navigator.clipboard.writeText(url); setStatus("Invite link copied."); }
    catch { setStatus("Copy this link: " + url); }
  };
  pinBtn.onclick = () => { state.pinMode = !state.pinMode; pinBtn.textContent = state.pinMode ? "Click the model to place…" : "Add pin"; };

  // ---- avatars
  function avatar(peer) {
    const g = new THREE.Group();
    const col = new THREE.Color(peer.color);
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.12, 16, 12), new THREE.MeshStandardMaterial({ color: col }));
    const nose = new THREE.Mesh(new THREE.ConeGeometry(0.05, 0.14, 12).rotateX(-Math.PI / 2).translate(0, 0, -0.16),
                                new THREE.MeshStandardMaterial({ color: col }));
    const tag = label(peer.name || "guest", peer.color); tag.position.set(0, 0.25, 0);
    g.add(head, nose, tag); g.visible = false; g.userData.meta = { element: "peer:" + peer.name, layer: "people" };
    root.add(g);
    return { ...peer, obj: g, target: new THREE.Vector3(), q: new THREE.Quaternion() };
  }
  function pinMesh(pin) {
    const g = new THREE.Group();
    const m = new THREE.Mesh(new THREE.ConeGeometry(0.05, 0.16, 12).rotateX(Math.PI).translate(0, 0.08, 0),
                             new THREE.MeshStandardMaterial({ color: 0xd1495b, emissive: 0x401010 }));
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.06, 0.08, 24).rotateX(-Math.PI / 2),
                                new THREE.MeshBasicMaterial({ color: 0xd1495b, side: THREE.DoubleSide }));
    g.add(m, ring); g.position.fromArray(pin.p);
    g.userData.pin = pin; m.userData.pin = pin; ring.userData.pin = pin;
    root.add(g);
    return g;
  }

  // ---- network
  function connect() {
    const sceneDigest = getDigest() || "";
    const url = `${relayBase()}/room/${state.room}/ws?scene=${encodeURIComponent(sceneDigest)}`;
    setStatus("Connecting…");
    const ws = new WebSocket(url);
    state.ws = ws;
    ws.onopen = () => { state.tries = 0; ws.send(JSON.stringify({ t: "hello", name: state.name, color: state.color, scene: sceneDigest })); };
    state.digest = sceneDigest;
    ws.onmessage = e => handle(JSON.parse(e.data));
    ws.onclose = () => {
      for (const p of state.peers.values()) root.remove(p.obj);
      state.peers.clear();
      const wait = Math.min(15000, 1000 * 2 ** state.tries++);
      setStatus(`Disconnected — retrying in ${Math.round(wait / 1000)} s`);
      setTimeout(connect, wait);
    };
  }
  function people() { setStatus(`Connected to room ${state.room} — ${state.peers.size + 1} ${state.peers.size ? "people" : "person (invite others)"}`); }
  function handle(m) {
    if (m.t === "welcome") {
      state.id = m.id;
      for (const p of m.peers) state.peers.set(p.id, avatar(p));
      for (const pin of state.pins.values()) root.remove(pin);
      state.pins.clear();
      for (const pin of m.pins) state.pins.set(pin.id, pinMesh(pin));
      people();
      if (m.peers.some(p => p.scene && p.scene !== state.digest)) setStatus(status.textContent + " (someone has a different model version)");
    } else if (m.t === "join") { state.peers.set(m.peer.id, avatar(m.peer)); people(); }
    else if (m.t === "leave") { const p = state.peers.get(m.id); if (p) root.remove(p.obj); state.peers.delete(m.id); people(); }
    else if (m.t === "pose") {
      const p = state.peers.get(m.id); if (!p) return;
      p.target.fromArray(m.p); p.q.fromArray(m.q);
      if (!p.obj.visible) { p.obj.position.copy(p.target); p.obj.quaternion.copy(p.q); p.obj.visible = true; }
    } else if (m.t === "pin:add") {
      if (!state.pins.has(m.pin.id)) state.pins.set(m.pin.id, pinMesh(m.pin));
      if (m.mine) state.mine.add(m.pin.id);
    } else if (m.t === "pin:del") { const g = state.pins.get(m.id); if (g) root.remove(g); state.pins.delete(m.id); }
    else if (m.t === "error") setStatus("Relay: " + m.reason);
  }

  // ---- per-frame: send own pose (10 Hz), ease peers toward their targets
  let last = 0;
  const pos = new THREE.Vector3(), quat = new THREE.Quaternion();
  function tick(now) {
    for (const p of state.peers.values()) { p.obj.position.lerp(p.target, 0.25); p.obj.quaternion.slerp(p.q, 0.25); }
    if (!state.ws || state.ws.readyState !== 1 || now - last < 1000 / POSE_HZ) return;
    last = now;
    const cam = renderer.xr.isPresenting ? renderer.xr.getCamera() : camera;
    cam.getWorldPosition(pos); cam.getWorldQuaternion(quat);
    state.ws.send(JSON.stringify({ t: "pose", p: pos.toArray().map(v => +v.toFixed(3)), q: quat.toArray().map(v => +v.toFixed(4)), xr: renderer.xr.isPresenting }));
  }

  // ---- clicks routed from the viewer: returns true when collab consumed the click
  function onClick(hit, meta, showText) {
    if (hit && hit.object.userData.pin) {
      const pin = hit.object.userData.pin;
      showText(`📍 ${pin.text} — ${pin.author}${pin.element ? " · " + pin.element : ""}`);
      if (state.mine.has(pin.id) && confirm("Delete this pin?")) state.ws?.send(JSON.stringify({ t: "pin:del", id: pin.id }));
      return true;
    }
    if (state.pinMode && hit) {
      const text = prompt("Pin note (max 280 characters):");
      state.pinMode = false; pinBtn.textContent = "Add pin";
      if (text && text.trim()) state.ws?.send(JSON.stringify({ t: "pin:add", p: hit.point.toArray().map(v => +v.toFixed(3)),
                                                              text: text.trim().slice(0, 280), element: meta?.element || "" }));
      return true;
    }
    return false;
  }
  window.__collab = state;
  return { tick, onClick };
}
