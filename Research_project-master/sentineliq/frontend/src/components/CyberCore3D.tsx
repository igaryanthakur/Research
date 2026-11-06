import React, { useRef, useEffect } from 'react';

// ─── Math Helpers for 3D ───────────────────────────────────────────────────────
const rotateY = (x: number, z: number, angle: number) => [
  x * Math.cos(angle) - z * Math.sin(angle),
  z * Math.cos(angle) + x * Math.sin(angle),
];
const rotateX = (y: number, z: number, angle: number) => [
  y * Math.cos(angle) - z * Math.sin(angle),
  z * Math.cos(angle) + y * Math.sin(angle),
];
const rotateZ = (x: number, y: number, angle: number) => [
  x * Math.cos(angle) - y * Math.sin(angle),
  y * Math.cos(angle) + x * Math.sin(angle),
];

interface Node3D {
  ix: number; iy: number; iz: number; // initial coords
  color: string;
  size: number;
  pulsePhase: number;
  pulseSpeed: number;
}
interface Edge {
  a: number; b: number;
}
interface Orbital {
  rx: number; rz: number;
  tiltZ: number; tiltX: number;
  speed: number; angle: number;
  color: string;
  packets: { a: number; speed: number; size: number }[];
}

interface RenderNode {
  x: number; y: number; z: number;
  color: string; size: number; alpha: number;
}

export const CyberCore3D: React.FC<{ className?: string }> = ({ className }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    let animId = 0;
    
    // ─── Initialization ───
    const N = 180;
    const R = 180;
    const nodes: Node3D[] = [];
    const edges: Edge[] = [];
    const renderNodes: RenderNode[] = []; // Pre-allocated
    
    const goldenRatio = 1 + Math.sqrt(5);
    for (let i = 0; i < N; i++) {
      const phi = Math.acos(1 - 2 * (i + 0.5) / N);
      const theta = Math.PI * goldenRatio * i;
      const x = R * Math.sin(phi) * Math.cos(theta);
      const y = R * Math.cos(phi);
      const z = R * Math.sin(phi) * Math.sin(theta);
      
      const isThreat = Math.random() > 0.92;
      const isHub = Math.random() > 0.95;
      
      nodes.push({
        ix: x, iy: y, iz: z,
        color: isThreat ? '#ef4444' : isHub ? '#a855f7' : '#22d3ee',
        size: isHub ? 4.5 : isThreat ? 3.5 : 1.8,
        pulsePhase: Math.random() * Math.PI * 2,
        pulseSpeed: 0.02 + Math.random() * 0.05
      });
      renderNodes.push({ x: 0, y: 0, z: 0, color: '', size: 0, alpha: 0 });
    }

    for (let i = 0; i < N; i++) {
      let connections = 0;
      for (let j = i + 1; j < N; j++) {
        const dist = Math.hypot(nodes[i].ix - nodes[j].ix, nodes[i].iy - nodes[j].iy, nodes[i].iz - nodes[j].iz);
        if (dist < R * 0.42 && connections < 4) {
          edges.push({ a: i, b: j });
          connections++;
        }
      }
    }

    const orbitals: Orbital[] = [
      { rx: R * 1.5, rz: R * 1.5, tiltZ: 0.2, tiltX: -0.4, speed: 0.003, angle: 0, color: 'rgba(34,211,238,0.2)', packets: [{a: 0, speed: 0.02, size: 3}, {a: Math.PI, speed: 0.02, size: 3}] },
      { rx: R * 1.8, rz: R * 1.8, tiltZ: -0.5, tiltX: 0.3, speed: -0.002, angle: Math.PI/3, color: 'rgba(168,85,247,0.15)', packets: [{a: Math.PI/2, speed: -0.015, size: 2}] },
      { rx: R * 2.1, rz: R * 2.1, tiltZ: 0.8, tiltX: 0.1, speed: 0.0015, angle: Math.PI, color: 'rgba(239,68,68,0.1)', packets: [{a: 0, speed: 0.025, size: 4}] }
    ];

    let tY = 0;
    let tX = 0;

    const resize = () => {
      const p = canvas.parentElement!;
      canvas.width = p.offsetWidth * 2;
      canvas.height = p.offsetHeight * 2;
      canvas.style.width = `${p.offsetWidth}px`;
      canvas.style.height = `${p.offsetHeight}px`;
    };
    resize();
    window.addEventListener('resize', resize);

    // Math helpers optimized (no array allocation)
    const focal = 1000;
    
    const frame = () => {
      const w = canvas.width, h = canvas.height;
      const cx = w / 2, cy = h / 2;
      
      ctx.clearRect(0, 0, w, h);
      
      tY += 0.003;
      tX = Math.sin(tY * 0.5) * 0.2;
      
      const cy_cos = Math.cos(tY), cy_sin = Math.sin(tY);
      const cx_cos = Math.cos(tX), cx_sin = Math.sin(tX);

      // Transform nodes in-place
      for (let i = 0; i < N; i++) {
        const n = nodes[i];
        
        // rotateY
        const x1 = n.ix * cy_cos - n.iz * cy_sin;
        const z1 = n.iz * cy_cos + n.ix * cy_sin;
        
        // rotateX
        const y2 = n.iy * cx_cos - z1 * cx_sin;
        const z2 = z1 * cx_cos + n.iy * cx_sin;
        
        const zOff = focal / (focal - z2);
        n.pulsePhase += n.pulseSpeed;
        
        const rn = renderNodes[i];
        rn.x = cx + x1 * zOff;
        rn.y = cy + y2 * zOff;
        rn.z = z2;
        rn.color = n.color;
        rn.size = n.size * zOff * (1 + Math.sin(n.pulsePhase) * 0.4);
        rn.alpha = Math.max(0.15, Math.min(1, (z2 + R) / (R * 2) + 0.15));
      }

      // ─── 1. Draw Edges (Optimized) ───
      ctx.lineWidth = 1.5;
      const numEdges = edges.length;
      ctx.beginPath();
      // Draw standard edges in one path to save CPU instructions
      for (let i = 0; i < numEdges; i++) {
        const e = edges[i];
        const n1 = renderNodes[e.a];
        const n2 = renderNodes[e.b];
        
        const avgZ = (n1.z + n2.z) * 0.5;
        if (avgZ < -R * 0.6) continue;
        
        // skip red edges for now, draw cyan edges in batch
        if (n1.color === '#ef4444' || n2.color === '#ef4444') continue;

        ctx.moveTo(n1.x, n1.y);
        ctx.lineTo(n2.x, n2.y);
      }
      ctx.strokeStyle = 'rgba(34,211,238,0.25)';
      ctx.stroke();

      // Draw red edges separately
      ctx.beginPath();
      for (let i = 0; i < numEdges; i++) {
        const e = edges[i];
        const n1 = renderNodes[e.a];
        const n2 = renderNodes[e.b];
        const avgZ = (n1.z + n2.z) * 0.5;
        if (avgZ < -R * 0.6) continue;
        if (n1.color === '#ef4444' || n2.color === '#ef4444') {
           ctx.moveTo(n1.x, n1.y);
           ctx.lineTo(n2.x, n2.y);
        }
      }
      ctx.strokeStyle = 'rgba(239,68,68,0.4)';
      ctx.stroke();


      // ─── 2. Draw Orbitals (Optimized points) ───
      const orbPts = 45; // reduced points
      for (let o = 0; o < orbitals.length; o++) {
        const orb = orbitals[o];
        orb.angle += orb.speed;
        
        const cz_cos = Math.cos(orb.tiltZ), cz_sin = Math.sin(orb.tiltZ);
        const cbx_cos = Math.cos(orb.tiltX), cbx_sin = Math.sin(orb.tiltX);
        const cby_cos = Math.cos(orb.angle), cby_sin = Math.sin(orb.angle);

        ctx.beginPath();
        for(let i=0; i<=orbPts; i++) {
           const th = (i / orbPts) * Math.PI * 2;
           const ox = Math.cos(th) * orb.rx;
           const oz = Math.sin(th) * orb.rz;
           
           // tiltZ
           const px1 = ox * cz_cos;
           const py1 = ox * cz_sin;
           // tiltX
           const py2 = py1 * cbx_cos - oz * cbx_sin;
           const pz2 = oz * cbx_cos + py1 * cbx_sin;
           // orbit angle
           const px3 = px1 * cby_cos - pz2 * cby_sin;
           const pz3 = pz2 * cby_cos + px1 * cby_sin;
           
           const zOff = focal / (focal - pz3);
           const sx = cx + px3 * zOff;
           const sy = cy + py2 * zOff;
           
           if (i===0) ctx.moveTo(sx, sy);
           else ctx.lineTo(sx, sy);
        }
        ctx.strokeStyle = orb.color.replace('0.2', '0.4').replace('0.15', '0.3').replace('0.1', '0.2'); // boost orbital opacity
        ctx.lineWidth = 2;
        ctx.stroke();
        
        // Packets
        for (let pIdx = 0; pIdx < orb.packets.length; pIdx++) {
           const p = orb.packets[pIdx];
           p.a += p.speed;
           const ox = Math.cos(p.a) * orb.rx;
           const oz = Math.sin(p.a) * orb.rz;
           
           const px1 = ox * cz_cos;
           const py1 = ox * cz_sin;
           const py2 = py1 * cbx_cos - oz * cbx_sin;
           const pz2 = oz * cbx_cos + py1 * cbx_sin;
           const px3 = px1 * cby_cos - pz2 * cby_sin;
           const pz3 = pz2 * cby_cos + px1 * cby_sin;
           
           const zOff = focal / (focal - pz3);
           const sx = cx + px3 * zOff;
           const sy = cy + py2 * zOff;
           
           const isFront = pz3 > 0;
           const packetColor = orb.color.includes('239') ? '#ef4444' : orb.color.includes('168') ? '#a855f7' : '#22d3ee';
           
           ctx.fillStyle = packetColor;
           ctx.globalAlpha = isFront ? 1 : 0.2;
           ctx.beginPath();
           ctx.arc(sx, sy, p.size * zOff, 0, Math.PI*2);
           ctx.fill();
           
           // Faux glow (much faster than shadowBlur)
           if (isFront) {
             ctx.globalAlpha = 0.5;
             ctx.beginPath();
             ctx.arc(sx, sy, p.size * zOff * 3.5, 0, Math.PI*2);
             ctx.fill();
           }
        }
      }

      // ─── 3. Draw Nodes (In-place sort and draw) ───
      renderNodes.sort((a,b) => a.z - b.z);
      for (let i = 0; i < N; i++) {
        const n = renderNodes[i];
        if (n.alpha < 0.05) continue;
        
        ctx.globalAlpha = n.alpha;
        ctx.fillStyle = n.color;
        
        // Faux glow using layered arcs instead of expensive shadowBlur
        if (n.z > R * 0.2) {
           ctx.globalAlpha = n.alpha * 0.4;
           ctx.beginPath();
           ctx.arc(n.x, n.y, n.size * 3.5, 0, Math.PI * 2);
           ctx.fill();
           ctx.globalAlpha = n.alpha;
        }
        
        ctx.beginPath();
        ctx.arc(n.x, n.y, Math.max(0.1, n.size), 0, Math.PI * 2);
        ctx.fill();
      }
      
      ctx.globalAlpha = 1;
      animId = requestAnimationFrame(frame);
    };

    animId = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(animId); window.removeEventListener('resize', resize); };
  }, []);

  return <canvas ref={canvasRef} className={className} />;
};
