import React, { useRef, useEffect } from 'react';

const TAU = Math.PI * 2;
const LABELS = ['PHISHING','SQL INJECT','XSS','DDoS','BRUTE FORCE','RANSOMWARE','0-DAY EXPLOIT','MALWARE','C2 BEACON','DATA EXFIL','BOT NET','MITM','ROOTKIT'];

interface Spark { x: number; y: number; vx: number; vy: number; life: number }
interface Packet {
  x: number; y: number; vx: number; vy: number;
  label: string; phase: 'fly' | 'explode';
  sparks: Spark[]; labelAlpha: number; active: boolean;
}

export interface LiveDefenseRef { blocked: number }

const LiveDefenseCanvas = React.forwardRef<LiveDefenseRef, { className?: string }>(
  ({ className }, ref) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const stateRef = useRef({
      blocked: 0, lastSpawn: 0, scanAngle: 0, shieldPulse: 0,
      nodePhases: [0, 1.05, 2.1, 3.15, 4.2, 5.25],
      packets: [] as Packet[], animId: 0,
    });

    // Expose blocked count via ref
    useEffect(() => {
      if (!ref) return;
      const interval = setInterval(() => {
        if (typeof ref === 'function') return;
        if (ref.current) ref.current.blocked = stateRef.current.blocked;
      }, 100);
      return () => clearInterval(interval);
    }, [ref]);

    useEffect(() => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const st = stateRef.current;

      const resize = () => {
        const p = canvas.parentElement;
        if (!p) return;
        const r = p.getBoundingClientRect();
        canvas.width = Math.floor(r.width);
        canvas.height = Math.floor(r.height);
      };
      resize();
      const ro = new ResizeObserver(resize);
      if (canvas.parentElement) ro.observe(canvas.parentElement);

      const frame = () => {
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        const W = canvas.width, H = canvas.height;
        if (!W || !H) { st.animId = requestAnimationFrame(frame); return; }
        const cx = W / 2, cy = H / 2;
        const shieldR = Math.min(W, H) * 0.24;
        const nodeR   = Math.min(W, H) * 0.41;

        const nodes = Array.from({ length: 6 }, (_, i) => {
          const a = (i / 6) * TAU - Math.PI / 6;
          return { x: cx + Math.cos(a) * nodeR, y: cy + Math.sin(a) * nodeR };
        });

        // ── Clear ──
        ctx.clearRect(0, 0, W, H);
        ctx.fillStyle = '#020c18';
        ctx.fillRect(0, 0, W, H);

        // ── Hex grid ──
        const S = 24;
        ctx.strokeStyle = 'rgba(0,160,220,0.055)';
        ctx.lineWidth = 0.5;
        for (let row = -1; row < H / (S * 1.73) + 1; row++) {
          for (let col = -1; col < W / (S * 1.5) + 1; col++) {
            const ox = row % 2 === 0 ? 0 : S * 0.75;
            const hx = col * S * 1.5 + ox, hy = row * S * Math.sqrt(3);
            ctx.beginPath();
            for (let k = 0; k < 6; k++) {
              const a = (k / 6) * TAU;
              const px = hx + S * 0.5 * Math.cos(a), py = hy + S * 0.5 * Math.sin(a);
              k === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
            }
            ctx.closePath(); ctx.stroke();
          }
        }

        // ── Spokes + ring ──
        ctx.strokeStyle = 'rgba(0,180,255,0.07)';
        ctx.lineWidth = 0.5;
        nodes.forEach(n => {
          ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(n.x, n.y); ctx.stroke();
        });
        for (let k = 0; k < 6; k++) {
          ctx.beginPath();
          ctx.moveTo(nodes[k].x, nodes[k].y);
          ctx.lineTo(nodes[(k + 1) % 6].x, nodes[(k + 1) % 6].y);
          ctx.stroke();
        }

        // ── Shield ──
        st.shieldPulse += 0.022;
        const pulse = 1 + Math.sin(st.shieldPulse) * 0.032;
        st.scanAngle += 0.016;

        // Dashed outer ring
        ctx.save();
        ctx.strokeStyle = 'rgba(0,200,255,0.32)';
        ctx.lineWidth = 1;
        ctx.setLineDash([5, 10]);
        ctx.lineDashOffset = -st.scanAngle * 28;
        ctx.beginPath(); ctx.arc(cx, cy, shieldR * pulse, 0, TAU); ctx.stroke();
        ctx.setLineDash([]); ctx.restore();

        // Background glow fill
        const bg = ctx.createRadialGradient(cx, cy, shieldR * 0.1, cx, cy, shieldR);
        bg.addColorStop(0, 'rgba(0,120,255,0.16)');
        bg.addColorStop(0.65,'rgba(0,90,200,0.05)');
        bg.addColorStop(1,   'rgba(0,60,180,0)');
        ctx.fillStyle = bg; ctx.beginPath(); ctx.arc(cx, cy, shieldR, 0, TAU); ctx.fill();

        // Radar sweep wedge
        ctx.save(); ctx.translate(cx, cy); ctx.rotate(st.scanAngle);
        const sw = ctx.createLinearGradient(0, 0, shieldR, 0);
        sw.addColorStop(0, 'rgba(0,220,255,0.28)');
        sw.addColorStop(1, 'rgba(0,220,255,0)');
        ctx.fillStyle = sw;
        ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, shieldR, -0.26, 0.26); ctx.closePath(); ctx.fill();
        ctx.restore();

        // Core orb
        const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, shieldR * 0.2 * pulse);
        core.addColorStop(0,    'rgba(210,245,255,1)');
        core.addColorStop(0.35, 'rgba(0,190,255,0.9)');
        core.addColorStop(0.7,  'rgba(0,100,230,0.45)');
        core.addColorStop(1,    'rgba(0,60,200,0)');
        ctx.fillStyle = core; ctx.beginPath(); ctx.arc(cx, cy, shieldR * 0.2 * pulse, 0, TAU); ctx.fill();

        // Hex symbol
        ctx.save(); ctx.translate(cx, cy);
        ctx.strokeStyle = 'rgba(255,255,255,0.8)'; ctx.lineWidth = 1.5;
        const hs = shieldR * 0.115;
        ctx.beginPath();
        for (let k = 0; k < 6; k++) {
          const a = (k / 6) * TAU;
          k === 0 ? ctx.moveTo(hs * Math.cos(a), hs * Math.sin(a)) : ctx.lineTo(hs * Math.cos(a), hs * Math.sin(a));
        }
        ctx.closePath(); ctx.stroke(); ctx.restore();

        // ── Nodes ──
        nodes.forEach((n, i) => {
          st.nodePhases[i] += 0.022;
          const np = 1 + Math.sin(st.nodePhases[i]) * 0.12;
          const ng = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, 14 * np);
          ng.addColorStop(0, 'rgba(0,200,255,0.35)'); ng.addColorStop(1, 'rgba(0,200,255,0)');
          ctx.fillStyle = ng; ctx.beginPath(); ctx.arc(n.x, n.y, 14 * np, 0, TAU); ctx.fill();
          ctx.fillStyle = '#091a2e'; ctx.strokeStyle = 'rgba(0,200,255,0.75)'; ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.arc(n.x, n.y, 8, 0, TAU); ctx.fill(); ctx.stroke();
          ctx.fillStyle = 'rgba(0,210,255,0.9)';
          [-2.5, 0, 2.5].forEach(dy => ctx.fillRect(n.x - 3.5, n.y + dy - 0.7, 7, 1.4));
        });

        // ── Spawn ──
        const now = performance.now();
        const active = st.packets.filter(p => p.active).length;
        if (now - st.lastSpawn > 520 && active < 14) {
          st.lastSpawn = now;
          const edge = Math.floor(Math.random() * 4);
          let sx = 0, sy = 0;
          if (edge === 0) { sx = Math.random() * W; sy = -16; }
          else if (edge === 1) { sx = W + 16; sy = Math.random() * H; }
          else if (edge === 2) { sx = Math.random() * W; sy = H + 16; }
          else { sx = -16; sy = Math.random() * H; }
          const tNode = nodes[Math.floor(Math.random() * 6)];
          const dx = tNode.x - sx, dy = tNode.y - sy;
          const d = Math.sqrt(dx * dx + dy * dy) || 1;
          const spd = 1.3 + Math.random() * 0.9;
          const pk: Packet = {
            x: sx, y: sy, vx: dx / d * spd, vy: dy / d * spd,
            label: LABELS[Math.floor(Math.random() * LABELS.length)],
            phase: 'fly', sparks: [], labelAlpha: 0, active: true,
          };
          const slot = st.packets.findIndex(p => !p.active);
          if (slot >= 0) st.packets[slot] = pk; else st.packets.push(pk);
        }

        // ── Packets ──
        st.packets.forEach(p => {
          if (!p.active) return;
          if (p.phase === 'fly') {
            p.x += p.vx; p.y += p.vy;
            const ddx = p.x - cx, ddy = p.y - cy;
            if (Math.sqrt(ddx * ddx + ddy * ddy) < shieldR) {
              p.phase = 'explode'; p.labelAlpha = 1; st.blocked++;
              for (let k = 0; k < 16; k++) {
                const a = (k / 16) * TAU + Math.random() * 0.3;
                const spd2 = 1.8 + Math.random() * 2.2;
                p.sparks.push({ x: p.x, y: p.y, vx: Math.cos(a) * spd2, vy: Math.sin(a) * spd2, life: 1 });
              }
            }
            if (p.x < -40 || p.x > W + 40 || p.y < -40 || p.y > H + 40) p.active = false;
            // Draw trail
            ctx.globalAlpha = 0.45; ctx.strokeStyle = '#FF1744'; ctx.lineWidth = 1.2;
            ctx.shadowBlur = 5; ctx.shadowColor = '#FF1744';
            ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x - p.vx * 9, p.y - p.vy * 9); ctx.stroke();
            ctx.shadowBlur = 0; ctx.globalAlpha = 1;
            // Draw dot
            const pg = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, 4.5);
            pg.addColorStop(0, '#FFFFFF'); pg.addColorStop(0.3, '#FF4444'); pg.addColorStop(1, 'rgba(255,0,0,0)');
            ctx.fillStyle = pg; ctx.beginPath(); ctx.arc(p.x, p.y, 4.5, 0, TAU); ctx.fill();
          } else {
            p.labelAlpha -= 0.012;
            let alive = false;
            p.sparks.forEach(sp => {
              sp.x += sp.vx; sp.y += sp.vy; sp.vx *= 0.91; sp.vy *= 0.91; sp.life -= 0.028;
              if (sp.life > 0) {
                alive = true;
                ctx.globalAlpha = sp.life * 0.85;
                ctx.fillStyle = sp.life > 0.5 ? '#00FF88' : '#00AAFF';
                ctx.beginPath(); ctx.arc(sp.x, sp.y, 2.5 * sp.life, 0, TAU); ctx.fill();
                ctx.globalAlpha = 1;
              }
            });
            if (p.labelAlpha > 0) {
              ctx.globalAlpha = Math.min(p.labelAlpha, 1);
              ctx.font = 'bold 9px "Courier New",monospace'; ctx.textAlign = 'center';
              ctx.fillStyle = '#00FF88'; ctx.fillText('✓ ' + p.label, p.x, p.y - 16);
              ctx.globalAlpha = 1;
            }
            if (!alive && p.labelAlpha <= 0) p.active = false;
          }
        });

        // ── Stats overlay ──
        const fly = st.packets.filter(p => p.active && p.phase === 'fly').length;
        ctx.textAlign = 'left'; ctx.font = 'bold 10px "Courier New",monospace';
        ctx.fillStyle = 'rgba(0,255,136,0.85)'; ctx.fillText(`BLOCKED: ${st.blocked.toLocaleString()}`, 10, 18);
        ctx.fillStyle = fly > 0 ? 'rgba(255,80,80,0.8)' : 'rgba(0,255,136,0.5)';
        ctx.fillText(`THREATS: ${fly}`, 10, 34);
        ctx.fillStyle = 'rgba(0,180,255,0.6)'; ctx.fillText('SHIELD: ACTIVE', 10, 50);

        st.animId = requestAnimationFrame(frame);
      };
      st.animId = requestAnimationFrame(frame);

      return () => {
        cancelAnimationFrame(st.animId);
        ro.disconnect();
        st.packets = [];
      };
    }, []);

    return (
      <canvas
        ref={canvasRef}
        className={className}
        style={{ display: 'block', width: '100%', height: '100%' }}
      />
    );
  }
);

LiveDefenseCanvas.displayName = 'LiveDefenseCanvas';
export default LiveDefenseCanvas;
