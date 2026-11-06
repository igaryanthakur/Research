import React, { useRef, useEffect } from 'react';

const TAU = Math.PI * 2;

interface CyberRiskOrbProps {
  riskScore: number; // 0-100
  className?: string;
}

/**
 * CyberRiskOrb — pure Canvas 2D replacement for the broken Three.js ThreatOrb.
 * Shows a premium gauge with arc fill, rotating rings, radar sweep, and particle field.
 * Zero WebGL dependency — renders on any device at 60fps.
 */
const CyberRiskOrb: React.FC<CyberRiskOrbProps> = ({ riskScore, className }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef   = useRef<number>(0);
  const stateRef  = useRef({
    ring1: 0, ring2: 0, ring3: 0, scan: 0, pulse: 0,
    currentScore: 0,
    particles: Array.from({ length: 40 }, () => ({
      angle: Math.random() * TAU,
      r: 0.7 + Math.random() * 0.25,
      speed: (Math.random() - 0.5) * 0.006,
      size: 1 + Math.random() * 1.5,
      alpha: 0.2 + Math.random() * 0.5,
    })),
  });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const st = stateRef.current;

    const resize = () => {
      const p = canvas.parentElement;
      if (!p) return;
      const s = Math.min(p.clientWidth, p.clientHeight);
      canvas.width  = s;
      canvas.height = s;
    };
    resize();
    const ro = new ResizeObserver(resize);
    if (canvas.parentElement) ro.observe(canvas.parentElement);

    const getColor = (score: number) => {
      if (score < 40) return { h: 160, s: 100, l: 55 }; // cyan-green
      if (score < 70) return { h: 38,  s: 100, l: 55 }; // amber
      return              { h: 0,   s: 100, l: 55 }; // red
    };

    const frame = () => {
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      const W = canvas.width, H = canvas.height;
      const cx = W / 2, cy = H / 2;
      const R  = Math.min(W, H) * 0.44;

      // Lerp score
      st.currentScore += (riskScore - st.currentScore) * 0.04;
      const score = st.currentScore;

      // Angle increments
      st.ring1 += 0.008;
      st.ring2 -= 0.005;
      st.ring3 += 0.012;
      st.scan  += 0.025;
      st.pulse += 0.035;

      const col = getColor(score);
      const hsl = `hsl(${col.h},${col.s}%,${col.l}%)`;
      const hslD= `hsl(${col.h},${col.s}%,${col.l - 15}%)`;

      // ── Clear ──
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = 'rgba(3,10,22,1)';
      ctx.fillRect(0, 0, W, H);

      // ── Outer ambient glow ──
      const glow = ctx.createRadialGradient(cx, cy, R * 0.4, cx, cy, R * 1.1);
      glow.addColorStop(0, `hsla(${col.h},${col.s}%,${col.l}%,0.08)`);
      glow.addColorStop(1, 'transparent');
      ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(cx, cy, R * 1.1, 0, TAU); ctx.fill();

      // ── Particles ──
      st.particles.forEach(p => {
        p.angle += p.speed;
        const px = cx + Math.cos(p.angle) * R * p.r;
        const py = cy + Math.sin(p.angle) * R * p.r;
        ctx.globalAlpha = p.alpha * (0.6 + Math.sin(st.pulse + p.angle) * 0.4);
        ctx.fillStyle = hsl;
        ctx.beginPath(); ctx.arc(px, py, p.size, 0, TAU); ctx.fill();
        ctx.globalAlpha = 1;
      });

      // ── Rotating rings ──
      const drawRing = (angle: number, r: number, dash: number[], opacity: number, lw: number) => {
        ctx.save();
        ctx.translate(cx, cy); ctx.rotate(angle);
        ctx.strokeStyle = `hsla(${col.h},${col.s}%,${col.l}%,${opacity})`;
        ctx.lineWidth = lw;
        ctx.setLineDash(dash);
        ctx.beginPath(); ctx.arc(0, 0, r, 0, TAU); ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();
      };
      drawRing(st.ring1, R * 1.0,  [3, 8],   0.25, 1);
      drawRing(st.ring2, R * 0.88, [6, 12],  0.18, 0.8);
      drawRing(st.ring3, R * 0.76, [2, 6],   0.15, 0.6);

      // ── Tick marks (outer ring) ──
      ctx.save(); ctx.translate(cx, cy);
      for (let i = 0; i < 60; i++) {
        const a = (i / 60) * TAU;
        const isMajor = i % 5 === 0;
        const r1 = R * (isMajor ? 0.96 : 0.98);
        const r2 = R * 1.04;
        ctx.strokeStyle = isMajor
          ? `hsla(${col.h},${col.s}%,${col.l + 10}%,0.7)`
          : `hsla(${col.h},80%,60%,0.2)`;
        ctx.lineWidth = isMajor ? 1.5 : 0.7;
        ctx.beginPath();
        ctx.moveTo(Math.cos(a) * r1, Math.sin(a) * r1);
        ctx.lineTo(Math.cos(a) * r2, Math.sin(a) * r2);
        ctx.stroke();
      }
      ctx.restore();

      // ── Arc gauge fill ──
      const startA = -Math.PI * 0.8;
      const endA   = startA + (score / 100) * TAU * 0.9; // 80% of circle = gauge range
      const gaugeR = R * 0.82;

      // Track (dim)
      ctx.strokeStyle = 'rgba(255,255,255,0.05)';
      ctx.lineWidth = 10;
      ctx.lineCap   = 'round';
      ctx.beginPath();
      ctx.arc(cx, cy, gaugeR, startA, startA + TAU * 0.9);
      ctx.stroke();

      // Fill
      const arcGrd = ctx.createLinearGradient(cx - gaugeR, cy, cx + gaugeR, cy);
      arcGrd.addColorStop(0, `hsla(${col.h + 30},100%,65%,1)`);
      arcGrd.addColorStop(1, hsl);
      ctx.strokeStyle = arcGrd;
      ctx.lineWidth   = 10;
      ctx.shadowBlur  = 16;
      ctx.shadowColor = hsl;
      ctx.beginPath();
      ctx.arc(cx, cy, gaugeR, startA, endA);
      ctx.stroke();
      ctx.shadowBlur = 0;

      // ── Radar sweep ──
      ctx.save(); ctx.translate(cx, cy); ctx.rotate(st.scan);
      const sweep = ctx.createLinearGradient(0, 0, R * 0.7, 0);
      sweep.addColorStop(0, `hsla(${col.h},100%,75%,0.35)`);
      sweep.addColorStop(1, `hsla(${col.h},100%,75%,0)`);
      ctx.fillStyle = sweep;
      ctx.beginPath(); ctx.moveTo(0, 0);
      ctx.arc(0, 0, R * 0.7, -0.25, 0.25); ctx.closePath(); ctx.fill();
      ctx.restore();

      // ── Center fill ──
      const coreR = R * 0.52;
      const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR);
      core.addColorStop(0, 'rgba(8,20,45,1)');
      core.addColorStop(1, 'rgba(4,12,28,1)');
      ctx.fillStyle = core; ctx.beginPath(); ctx.arc(cx, cy, coreR, 0, TAU); ctx.fill();

      // Inner ring
      ctx.strokeStyle = `hsla(${col.h},80%,60%,0.2)`;
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(cx, cy, coreR, 0, TAU); ctx.stroke();

      // ── Score text ──
      const disp = Math.round(score);
      ctx.textAlign = 'center';
      ctx.fillStyle = hsl;
      ctx.font = `900 ${R * 0.38}px -apple-system,sans-serif`;
      ctx.fillText(String(disp), cx, cy + R * 0.13);

      ctx.fillStyle = 'rgba(255,255,255,0.35)';
      ctx.font = `700 ${R * 0.1}px -apple-system,sans-serif`;
      ctx.fillText('RISK SCORE', cx, cy + R * 0.32);

      // Status label
      const label = disp < 40 ? 'SECURE' : disp < 70 ? 'ELEVATED' : 'CRITICAL';
      ctx.fillStyle = hsl;
      ctx.font = `800 ${R * 0.09}px -apple-system,sans-serif`;
      ctx.letterSpacing = '2px';
      ctx.fillText(label, cx, cy - R * 0.25);

      animRef.current = requestAnimationFrame(frame);
    };

    animRef.current = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(animRef.current);
      ro.disconnect();
    };
  }, [riskScore]);

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{ display: 'block', width: '100%', height: '100%' }}
    />
  );
};

export default CyberRiskOrb;
