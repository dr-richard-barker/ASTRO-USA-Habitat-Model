// Two-client protocol test against a running relay (default: wrangler dev on 127.0.0.1:8797).
//   RELAY=http://127.0.0.1:8797 node test/smoke.mjs
// Checks: origin gate, bad room code, hello/welcome/join, pose relay (not echoed), pin add/persist/delete with
// author-only deletion, oversized/invalid frames refused, leave on close. Exits 1 on any failure.
const RELAY = process.env.RELAY || "http://127.0.0.1:8797";
const ORIGIN = process.env.ORIGIN || "http://localhost:8422";
const room = "test" + Math.random().toString(36).slice(2, 12);
const wsURL = (r = room) => RELAY.replace(/^http/, "ws") + `/room/${r}/ws?scene=testdigest`;
let failures = 0;
const ok = (cond, what) => { console.log(`${cond ? "PASS" : "FAIL"}  ${what}`); if (!cond) failures++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));

function client(name, origin = ORIGIN, r = room) {
  const ws = new WebSocket(wsURL(r), { headers: { Origin: origin } });
  const inbox = [];
  ws.addEventListener("message", e => inbox.push(JSON.parse(e.data)));
  const opened = new Promise((res, rej) => { ws.addEventListener("open", res); ws.addEventListener("error", rej); });
  const next = async (t, ms = 3000) => {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) { const i = inbox.findIndex(m => m.t === t); if (i >= 0) return inbox.splice(i, 1)[0]; await sleep(20); }
    return null;
  };
  return { ws, inbox, opened, next, send: m => ws.send(typeof m === "string" ? m : JSON.stringify(m)), name };
}

const h = await fetch(RELAY + "/health"); ok(h.ok && (await h.text()) === "ok", "health endpoint");
const refused = async c => { try { await c.opened; c.ws.close(); return false; } catch { return true; } };
ok(await refused(client("Eve", "https://evil.example")), "socket from a foreign origin refused");
ok(await refused(client("Rex", ORIGIN, "x")), "socket to a too-short room code refused");

const A = client("Ana"), B = client("Ben");
await Promise.all([A.opened, B.opened]);
A.send({ t: "pose", p: [0, 0, 0], q: [0, 0, 0, 1] });
ok((await A.next("error"))?.reason === "say hello first", "messages before hello are refused");
A.send({ t: "hello", name: "Ana", color: "#ff0000", scene: "testdigest" });
const wA = await A.next("welcome");
ok(wA && wA.peers.length === 0 && Array.isArray(wA.pins), "A welcomed into an empty room");
B.send({ t: "hello", name: "Ben\u0007<script>", color: "not-a-colour" });
const wB = await B.next("welcome");
ok(wB && wB.peers.length === 1 && wB.peers[0].name === "Ana", "B sees A in the peer list");
const j = await A.next("join");
ok(j && j.peer.name === "Ben<script>" && j.peer.color === "#3fb6a8", "A told of B's join; control chars stripped, bad colour defaulted");

A.send({ t: "pose", p: [1, 1.6, -1], q: [0, 0, 0, 1], xr: false });
const pB = await B.next("pose");
ok(pB && pB.id === wA.id && pB.p[1] === 1.6, "pose relayed A -> B");
ok((await A.next("pose", 400)) === null, "pose not echoed to its sender");
A.send({ t: "pose", p: [1e9, 0, 0], q: [0, 0, 0, 1] });
ok((await A.next("error"))?.reason === "bad pose", "non-finite / out-of-range pose refused");

A.send({ t: "pin:add", p: [5.2, 1.0, -1.9], text: "Check grille throw here", element: "hvac_supply" });
const pa = await A.next("pin:add"), pb = await B.next("pin:add");
ok(pa && pb && pa.pin.id === pb.pin.id && pb.pin.author === "Ana", "pin broadcast to both, once each");
ok(pa.mine === true && !pb.mine, "only the author's copy is flagged mine");
ok((await A.next("pin:add", 400)) === null, "author does not receive the pin twice");
B.send({ t: "pin:del", id: pa.pin.id });
ok((await B.next("error"))?.reason === "only the author's session can delete a pin", "non-author cannot delete");

const C = client("Cy"); await C.opened; C.send({ t: "hello", name: "Cy" });
const wC = await C.next("welcome");
ok(wC && wC.pins.some(p => p.id === pa.pin.id) && wC.peers.length === 2, "late joiner receives stored pins + 2 peers");

A.send({ t: "pin:del", id: pa.pin.id });
ok((await B.next("pin:del"))?.id === pa.pin.id && (await A.next("pin:del"))?.id === pa.pin.id, "author deletes; all told");

A.send("x".repeat(5000)); ok((await A.next("error"))?.reason.startsWith("frame too large"), "oversized frame refused");
A.send("{not json"); ok((await A.next("error"))?.reason === "invalid JSON", "invalid JSON refused");
A.send({ t: "pin:add", p: [0, 0, 0], text: "   " }); ok((await A.next("error"))?.reason === "empty pin text", "empty pin refused");

B.ws.close(); await sleep(300);
ok((await A.next("leave"))?.id === wB.id, "close -> leave broadcast");
A.ws.close(); C.ws.close();
console.log(failures ? `\n${failures} FAILED` : "\nALL PASS");
process.exit(failures ? 1 : 0);
