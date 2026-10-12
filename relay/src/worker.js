// ASTRO-USA habitat relay: WebSocket rooms for shared walk-throughs of the habitat model.
//
//   GET /health                      -> "ok"
//   GET /room/<roomId>/ws?scene=<d>  -> WebSocket (Origin must be in ALLOWED_ORIGINS)
//
// Protocol (JSON text frames, <= 4 KB each):
//   client -> server  {t:"hello", name, color, scene}            once, first message
//                     {t:"pose", p:[x,y,z], q:[x,y,z,w], xr:bool} <= 20 / s, relayed, never stored
//                     {t:"pin:add", p:[x,y,z], text, element}    stored (SQLite), max 500 per room
//                     {t:"pin:del", id}                           only the pin's author session may delete
//   server -> client  {t:"welcome", id, peers:[...], pins:[...], scene}
//                     {t:"join", peer} {t:"leave", id} {t:"pose", id, p, q, xr} {t:"pin:add", pin} {t:"pin:del", id}
//                     {t:"error", reason}
//
// Privacy: no accounts, no IPs, no cookies. A display name is kept in memory for presence and stored only as
// the author of a pin the user chose to create. Rooms are addressed by an unguessable code shared in the
// URL fragment, which the client turns into the path (fragments never reach the server's logs otherwise).

import { DurableObject } from "cloudflare:workers";

const MAX_FRAME = 4096, MAX_PINS = 500, MAX_TEXT = 280, MAX_NAME = 40, POSE_PER_S = 20;
const ROOM_RE = /^[A-Za-z0-9_-]{8,64}$/;

const num = v => typeof v === "number" && Number.isFinite(v) && Math.abs(v) < 1e4;
const vec = (v, n) => Array.isArray(v) && v.length === n && v.every(num);
const clean = (s, n) => (typeof s === "string" ? s : "").replace(/[\u0000-\u001f\u007f]/g, "").slice(0, n);
const color = c => (typeof c === "string" && /^#[0-9a-fA-F]{6}$/.test(c) ? c : "#3fb6a8");

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (url.pathname === "/health") return new Response("ok", { headers: { "content-type": "text/plain" } });
    const m = url.pathname.match(/^\/room\/([^/]+)\/ws$/);
    if (!m) return new Response("not found", { status: 404 });
    if (!ROOM_RE.test(m[1])) return new Response("bad room code", { status: 400 });
    const allowed = (env.ALLOWED_ORIGINS || "").split(",").map(s => s.trim()).filter(Boolean);
    const origin = req.headers.get("Origin") || "";
    if (!allowed.includes(origin)) return new Response("origin not allowed", { status: 403 });
    if (req.headers.get("Upgrade") !== "websocket") return new Response("expected websocket", { status: 426 });
    const stub = env.ROOM.get(env.ROOM.idFromName(m[1]));
    return stub.fetch(req);
  },
};

export class Room extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.sql.exec(`CREATE TABLE IF NOT EXISTS pins (
      id TEXT PRIMARY KEY, x REAL, y REAL, z REAL, text TEXT, element TEXT,
      author TEXT, author_session TEXT, created INTEGER)`);
  }

  async fetch(req) {
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    const scene = clean(new URL(req.url).searchParams.get("scene"), 32);
    // hibernation API: the DO can sleep between messages without dropping sockets
    this.ctx.acceptWebSocket(server);
    server.serializeAttachment({ id: crypto.randomUUID().slice(0, 8), name: "", color: "#3fb6a8", scene,
                                 hello: false, win: 0, n: 0 });
    return new Response(null, { status: 101, webSocket: client });
  }

  peers(exceptWs) {
    return this.ctx.getWebSockets().filter(w => w !== exceptWs).map(w => w.deserializeAttachment())
      .filter(a => a.hello).map(({ id, name, color, scene }) => ({ id, name, color, scene }));
  }

  broadcast(msg, exceptWs) {
    const s = JSON.stringify(msg);
    for (const w of this.ctx.getWebSockets()) {
      if (w === exceptWs) continue;
      const a = w.deserializeAttachment();
      if (!a.hello) continue;
      try { w.send(s); } catch { /* socket closing */ }
    }
  }

  pins() {
    return this.sql.exec("SELECT id, x, y, z, text, element, author, created FROM pins ORDER BY created").toArray()
      .map(r => ({ id: r.id, p: [r.x, r.y, r.z], text: r.text, element: r.element, author: r.author, created: r.created }));
  }

  async webSocketMessage(ws, data) {
    const a = ws.deserializeAttachment();
    const fail = reason => { try { ws.send(JSON.stringify({ t: "error", reason })); } catch { } };
    if (typeof data !== "string" || data.length > MAX_FRAME) return fail("frame too large or not text");
    let msg;
    try { msg = JSON.parse(data); } catch { return fail("invalid JSON"); }
    if (!msg || typeof msg.t !== "string") return fail("missing type");

    if (msg.t === "hello") {
      if (a.hello) return fail("already joined");
      a.hello = true; a.name = clean(msg.name, MAX_NAME) || "guest"; a.color = color(msg.color);
      a.scene = clean(msg.scene, 32) || a.scene;
      ws.serializeAttachment(a);
      ws.send(JSON.stringify({ t: "welcome", id: a.id, peers: this.peers(ws), pins: this.pins(), scene: a.scene }));
      this.broadcast({ t: "join", peer: { id: a.id, name: a.name, color: a.color, scene: a.scene } }, ws);
      return;
    }
    if (!a.hello) return fail("say hello first");

    if (msg.t === "pose") {
      const now = Date.now();                       // simple 1-second window rate limit
      if (now - a.win > 1000) { a.win = now; a.n = 0; }
      if (++a.n > POSE_PER_S) { ws.serializeAttachment(a); return; }   // drop silently, no echo storm
      ws.serializeAttachment(a);
      if (!vec(msg.p, 3) || !vec(msg.q, 4)) return fail("bad pose");
      this.broadcast({ t: "pose", id: a.id, p: msg.p, q: msg.q, xr: !!msg.xr }, ws);
      return;
    }
    if (msg.t === "pin:add") {
      if (!vec(msg.p, 3)) return fail("bad pin position");
      const text = clean(msg.text, MAX_TEXT).trim();
      if (!text) return fail("empty pin text");
      const count = this.sql.exec("SELECT COUNT(*) AS n FROM pins").one().n;
      if (count >= MAX_PINS) return fail("pin limit reached for this room");
      const pin = { id: crypto.randomUUID().slice(0, 12), p: msg.p, text, element: clean(msg.element, 64),
                    author: a.name, created: Date.now() };
      this.sql.exec("INSERT INTO pins VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", pin.id, pin.p[0], pin.p[1], pin.p[2],
                    pin.text, pin.element, pin.author, a.id, pin.created);
      this.broadcast({ t: "pin:add", pin }, ws);   // everyone else...
      ws.send(JSON.stringify({ t: "pin:add", pin, mine: true }));   // ...and the sender once, flagged as its own
      return;
    }
    if (msg.t === "pin:del") {
      const id = clean(msg.id, 16);
      const row = this.sql.exec("SELECT author_session FROM pins WHERE id = ?", id).toArray()[0];
      if (!row) return fail("no such pin");
      if (row.author_session !== a.id) return fail("only the author's session can delete a pin");
      this.sql.exec("DELETE FROM pins WHERE id = ?", id);
      this.broadcast({ t: "pin:del", id }, ws);
      ws.send(JSON.stringify({ t: "pin:del", id }));
      return;
    }
    fail("unknown type");
  }

  async webSocketClose(ws) { this.leave(ws); }
  async webSocketError(ws) { this.leave(ws); }

  leave(ws) {
    const a = ws.deserializeAttachment();
    if (a && a.hello) this.broadcast({ t: "leave", id: a.id }, ws);
  }
}
