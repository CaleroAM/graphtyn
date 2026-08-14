export function pulseLinkLen(link) {
      const s = link.source || {}, t = link.target || {};
      const dx = (s.x || 0) - (t.x || 0), dy = (s.y || 0) - (t.y || 0), dz = (s.z || 0) - (t.z || 0);
      return Math.sqrt(dx * dx + dy * dy + dz * dz) || 80;
    }

export function buildPulseSim(data) {
      const nodesById = new Map();
      (data.nodes || []).forEach(n => nodesById.set(n.id, n));
      const conns = new Map();
      (data.links || []).forEach(l => {
        if (!conns.has(l.source)) conns.set(l.source, []);
        conns.get(l.source).push({ to: l.target, link: l });
        if (!conns.has(l.target)) conns.set(l.target, []);
        conns.get(l.target).push({ to: l.source, link: l });
      });
      return {
        nodesById, conns,
        links: (data.links || []),
        pulses: [],
        pulseCountByLink: new Map(),
        lastFire: new Map(),
        energy: new Map(),
        lastHeartbeat: 0,
        fire(nodeId, now) {
          if (!nodesById.has(nodeId)) return;
          if (now - (this.lastFire.get(nodeId) || -1e9) < 600) return;
          this.lastFire.set(nodeId, now);
          this.energy.set(nodeId, 1);
          const cs = conns.get(nodeId) || [];
          for (const c of cs) {
            if (this.pulses.length >= 160) break;
            if ((this.pulseCountByLink.get(c.link) || 0) >= 2) continue;
            this.pulseCountByLink.set(c.link, (this.pulseCountByLink.get(c.link) || 0) + 1);
            this.pulses.push({ link: c.link, from: nodeId, to: c.to, t: 0 });
          }
        },
        update(dtMs, nowMs) {
          const dt = dtMs / 1000;
          const ids = Array.from(nodesById.keys());
          for (const id of ids) {
            if (nowMs - (this.lastFire.get(id) || -1e9) >= 600 && Math.random() < 0.00015 * dtMs) {
              this.fire(id, nowMs);
            }
          }
          for (const [id, e] of this.energy) {
            this.energy.set(id, Math.max(0, e - 2.2 * dt));
          }
          if (nowMs - this.lastHeartbeat > 5200) {
            this.lastHeartbeat = nowMs;
            for (let k = 0; k < 3; k++) this.fire(ids[(Math.random() * ids.length) | 0], nowMs);
          }
          for (const l of this.links) {
            if (l._activity) l._activity = Math.max(0, l._activity - 2.4 * dt);
          }
          const survivors = [];
          for (const p of this.pulses) {
            p.link._activity = 1;
            const len = pulseLinkLen(p.link);
            p.t += (90 * dt) / Math.max(1, len);
            if (p.t >= 1) {
              this.pulseCountByLink.set(p.link, Math.max(0, (this.pulseCountByLink.get(p.link) || 0) - 1));
              this.energy.set(p.to, Math.min(1, (this.energy.get(p.to) || 0) + 0.5));
              if (Math.random() < 0.15) this.fire(p.to, nowMs);
            } else {
              survivors.push(p);
            }
          }
          this.pulses = survivors;
        }
      };
    }

