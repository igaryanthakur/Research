import React, { useMemo, useEffect, useRef } from 'react';

/**
 * Optimised Background:
 * - No external video (was causing 30s+ timeout → page lag)
 * - Canvas neural network (60 nodes reduced to 40, 150px max link distance)
 * - Static CSS glow orbs (no framer-motion → fully GPU composited)
 * - CSS-only scan lines & radar sweep (no JS animation for these)
 * - Hex grid via inline CSS background-image (zero JS, zero paint)
 */
const Background: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Canvas neural network — CPU efficient (40 nodes, O(n²/2) links with dist gate)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let W = (canvas.width  = window.innerWidth);
    let H = (canvas.height = window.innerHeight);

    const nodes = Array.from({ length: 40 }, () => ({
      x:  Math.random() * W,
      y:  Math.random() * H,
      vx: (Math.random() - 0.5) * 0.5,
      vy: (Math.random() - 0.5) * 0.5,
    }));

    const MAX_DIST = 150;

    const draw = () => {
      ctx.clearRect(0, 0, W, H);
      ctx.lineWidth   = 0.7;

      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i];
        n.x += n.vx; n.y += n.vy;
        if (n.x < 0 || n.x > W) n.vx *= -1;
        if (n.y < 0 || n.y > H) n.vy *= -1;

        for (let j = i + 1; j < nodes.length; j++) {
          const o  = nodes[j];
          const dx = n.x - o.x, dy = n.y - o.y;
          const d2 = dx * dx + dy * dy;
          if (d2 < MAX_DIST * MAX_DIST) {
            ctx.globalAlpha  = (1 - Math.sqrt(d2) / MAX_DIST) * 0.18;
            ctx.strokeStyle  = '#22d3ee';
            ctx.beginPath(); ctx.moveTo(n.x, n.y); ctx.lineTo(o.x, o.y); ctx.stroke();
          }
        }
        ctx.globalAlpha = 0.45;
        ctx.fillStyle   = '#22d3ee';
        ctx.beginPath(); ctx.arc(n.x, n.y, 1.1, 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalAlpha = 1;
      animId = requestAnimationFrame(draw);
    };

    const onResize = () => {
      W = canvas.width  = window.innerWidth;
      H = canvas.height = window.innerHeight;
    };
    window.addEventListener('resize', onResize);
    draw();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', onResize);
    };
  }, []);

  return (
    <div className="fixed inset-0 z-[-1] overflow-hidden bg-[#020c18]">

      {/* Static hex-grid via CSS — zero JS, zero repaint */}
      <div
        className="absolute inset-0 opacity-[0.04] pointer-events-none"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='56' height='100'%3E%3Cpath d='M28 66L0 50V17L28 1l28 16v33L28 66zm0 34L0 84V51l28-17 28 17v33L28 100z' fill='none' stroke='%2300d4ff' stroke-width='0.5'/%3E%3C/svg%3E")`,
          backgroundSize: '56px 100px',
        }}
      />

      {/* Radar sweep — CSS animation only, GPU composited */}
      <div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[140vmax] h-[140vmax] rounded-full pointer-events-none"
        style={{
          background: 'conic-gradient(from 0deg, rgba(6,182,212,0.12) 0%, transparent 18%)',
          animation: 'spin 9s linear infinite',
        }}
      />

      {/* Static ambient glow orbs — CSS blur, GPU composited */}
      <div className="absolute top-[8%] left-[18%] w-[360px] h-[360px] rounded-full bg-cyan-600/8 blur-[110px] pointer-events-none" />
      <div className="absolute bottom-[18%] right-[12%] w-[420px] h-[420px] rounded-full bg-indigo-700/8 blur-[130px] pointer-events-none" />

      {/* Two subtle CSS-animated scan lines — transform-only = GPU composited */}
      <div className="absolute left-0 right-0 h-px bg-cyan-400/5 pointer-events-none"
        style={{ animation: 'scanline 12s linear infinite' }} />
      <div className="absolute left-0 right-0 h-px bg-cyan-400/4 pointer-events-none"
        style={{ animation: 'scanline 18s linear infinite', animationDelay: '6s' }} />

      {/* Neural network canvas */}
      <canvas
        ref={canvasRef}
        className="absolute inset-0 pointer-events-none opacity-35"
      />

      <style>{`
        @keyframes spin {
          from { transform: translate(-50%,-50%) rotate(0deg); }
          to   { transform: translate(-50%,-50%) rotate(360deg); }
        }
        @keyframes scanline {
          from { top: -1px; opacity: 0; }
          10%  { opacity: 1; }
          90%  { opacity: 1; }
          to   { top: 100vh; opacity: 0; }
        }
      `}</style>
    </div>
  );
};

export default Background;
