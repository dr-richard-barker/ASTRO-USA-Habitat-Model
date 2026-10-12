# Habitat relay (multi-user presence + review pins)

Cloudflare Worker + one Durable Object per room (SQLite backend, Workers Free plan compatible).
Protocol and limits are documented at the top of `src/worker.js`.

    npm install          # pinned wrangler 4.129.1
    npm run dev          # local relay on 127.0.0.1:8797 (the viewer on localhost uses it automatically)
    npm test             # two-client protocol test against the running relay (20 checks)
    npm run deploy       # publish (needs the account owner's OK)

What is stored: pins only (position, note text <= 280 chars, the author's display name, the element clicked,
timestamp), per room, max 500. Poses are relayed in memory and never stored. No accounts, cookies or IPs.
Rooms are reachable by anyone holding the room code; only listed origins (`ALLOWED_ORIGINS`) can open sockets.
Remove everything with `npx wrangler delete`.
