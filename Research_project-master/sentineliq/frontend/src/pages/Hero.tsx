import React, { useRef, useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, ShieldCheck, Zap, Eye } from 'lucide-react';

import { CyberCore3D } from '../components/CyberCore3D';

// ─── HOW IT WORKS — Code card ──────────────────────────────────────────────────
const CODE_STEPS = [
  {
    step: '01', label: 'DETECT',
    color: 'cyan',
    lang: 'python',
    code: [
      '# ML Traffic Analysis',
      'score = sentinel.predict(',
      '  packet_features,',
      '  model="threat-v4.2"',
      ')',
      'if score > THRESHOLD:',
      '  alert(severity="HIGH",',
      '    confidence=score  # → 97.4%',
      '  )',
    ],
  },
  {
    step: '02', label: 'ANALYZE',
    color: 'purple',
    lang: 'json',
    code: [
      '{',
      '  "threat_type": "SQL_INJECTION",',
      '  "confidence": 97.4,',
      '  "source":  "203.0.113.77",',
      '  "target":  "/api/auth",',
      '  "technique": "OWASP-A03",',
      '  "actor": "APT-28"',
      '}',
    ],
  },
  {
    step: '03', label: 'NEUTRALIZE',
    color: 'emerald',
    lang: 'bash',
    code: [
      '> QUARANTINE 203.0.113.77',
      '> BLOCK /api/auth ← SQLi',
      '> SIGNATURE deployed',
      '> NOTIFY admin@corp.io',
      '',
      '✓ Threat contained in 8ms',
      '✓ Network status: SECURE',
    ],
  },
];

const colorMap: Record<string, string> = {
  cyan:    'from-cyan-500/20 via-transparent border-cyan-500/20 text-cyan-400',
  purple:  'from-purple-500/20 via-transparent border-purple-500/20 text-purple-400',
  emerald: 'from-emerald-500/20 via-transparent border-emerald-500/20 text-emerald-400',
};

// ─── Cycling word ──────────────────────────────────────────────────────────────
const WORDS = ['DEFENDED.', 'MONITORED.', 'SECURED.', 'PROTECTED.'];
const WordCycle: React.FC = () => {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI(x => (x + 1) % WORDS.length), 2600);
    return () => clearInterval(t);
  }, []);
  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={i}
        initial={{ opacity: 0, y: 14, filter: 'blur(6px)' }}
        animate={{ opacity: 1, y: 0,  filter: 'blur(0px)' }}
        exit={{   opacity: 0, y: -14, filter: 'blur(6px)' }}
        transition={{ duration: 0.38 }}
        className="inline-block text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-blue-400 to-purple-500"
      >
        {WORDS[i]}
      </motion.span>
    </AnimatePresence>
  );
};

// ─── Hero ──────────────────────────────────────────────────────────────────────
const Hero: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="relative w-full text-white overflow-x-hidden">

      {/* ══ SECTION 1: Above-fold — Perspective Network Grid ══ */}
      <section className="relative min-h-screen overflow-hidden flex flex-col justify-center">

        {/* ── Background Elements ── */}
        {/* Subtle grid pattern overlay */}
        <div className="absolute inset-x-0 bottom-0 h-[60vh] opacity-20"
          style={{ backgroundImage: 'linear-gradient(rgba(34,211,238,0.1) 1px,transparent 1px),linear-gradient(90deg,rgba(34,211,238,0.1) 1px,transparent 1px)', backgroundSize: '64px 64px', perspective: '1000px', transform: 'rotateX(75deg)', transformOrigin: '50% 100%' }}
        />
        
        {/* Glow behind the core */}
        <div className="absolute right-[5%] top-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-cyan-500/10 rounded-full blur-[120px] pointer-events-none" />
        <div className="absolute right-[15%] top-1/2 -translate-y-1/2 w-[400px] h-[400px] bg-purple-500/10 rounded-full blur-[100px] pointer-events-none" />

        {/* ── Content Grid (Left: Text, Right: 3D Core) ── */}
        <div className="relative z-20 mx-auto w-full max-w-[1400px] px-8 lg:px-16 pt-[12vh] pb-32">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
            
            {/* Left: Typography & CTAs (No box, clean text) */}
            <div className="max-w-[620px]">
              {/* Badge */}
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
                className="inline-flex items-center gap-2 mb-8 px-3 py-1.5 rounded-full border border-cyan-500/20 bg-cyan-500/5 text-[10px] font-black uppercase tracking-[0.3em] text-cyan-400"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-pulse" />
                SentinelIQ AI v4.2 — All Systems Operational
              </motion.div>

              {/* Main headline */}
              <motion.div
                initial={{ opacity: 0, y: 24 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.65, delay: 0.1 }}
                className="mb-8"
              >
                <h1 className="text-[clamp(54px,6.5vw,90px)] font-black tracking-tighter leading-[0.88]">
                  <span className="block text-white">YOUR NETWORK.</span>
                  <span className="block text-white">EVERY NODE.</span>
                  <span className="block">
                    ALWAYS <WordCycle />
                  </span>
                </h1>
              </motion.div>

              {/* Sub-copy */}
              <motion.p
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.55, delay: 0.25 }}
                className="text-[16px] text-zinc-400 leading-relaxed mb-10 max-w-[480px]"
              >
                SentinelIQ's autonomous AI monitors every connection in your
                infrastructure — detecting and neutralizing threats in
                {' '}<span className="text-cyan-400 font-bold">under 10ms</span>,
                24/7/365, across every vector.
              </motion.p>

              {/* CTAs */}
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.35 }}
                className="flex flex-wrap items-center gap-5"
              >
                <button
                  onClick={() => navigate('/auth')}
                  className="group relative flex items-center gap-2.5 px-9 py-4 rounded-xl font-black uppercase tracking-wider text-[13px] text-black overflow-hidden shadow-[0_0_30px_rgba(34,211,238,0.3)] transition-all hover:shadow-[0_0_40px_rgba(34,211,238,0.5)]"
                  style={{ background: 'linear-gradient(135deg,#22d3ee,#818cf8)' }}
                >
                  <span className="relative z-10 flex items-center gap-2.5">
                    Open Operations Center
                    <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
                  </span>
                  <div className="absolute inset-0 bg-white/20 opacity-0 group-hover:opacity-100 transition-opacity" />
                </button>

                <button className="flex items-center gap-2 px-8 py-4 rounded-xl border border-white/10 bg-white/5 text-white font-black uppercase tracking-wider text-[13px] hover:bg-white/10 transition-colors">
                  Live Threat Demo
                </button>
              </motion.div>

              {/* Certification strip */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.5 }}
                className="flex items-center gap-6 mt-10"
              >
                {['NIST FIPS 205', 'SOC 2 TYPE II', 'ISO 27001', 'ZERO TRUST'].map((c, i) => (
                  <span key={i} className="text-[10px] font-black text-zinc-600 uppercase tracking-[0.2em]">{c}</span>
                ))}
              </motion.div>
            </div>

            {/* Right: 3D Cyber Core Visualization */}
            <motion.div 
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 1, delay: 0.2 }}
              className="relative w-full aspect-square max-w-[700px] ml-auto"
            >
              {/* The native Canvas 3D Core */}
              <CyberCore3D className="w-full h-full" />
            </motion.div>

          </div>
        </div>

        {/* Bottom ops strip */}
        <div className="absolute bottom-0 left-0 right-0 z-30 border-t border-white/5 bg-black/70 backdrop-blur-xl px-8 py-2 flex items-center gap-6 text-[9px] font-black font-mono uppercase overflow-hidden">
          <span className="flex items-center gap-1.5 text-emerald-400 shrink-0">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            OPERATIONAL
          </span>
          <span className="text-zinc-600">|</span>
          {[
            { l: 'PHISHING', v: '847',   c: '#ef4444' },
            { l: 'DDoS',     v: '23',    c: '#f97316' },
            { l: 'MALWARE',  v: '1,284', c: '#eab308' },
            { l: 'INJECT',   v: '456',   c: '#22d3ee' },
            { l: '0-DAY',    v: '12',    c: '#a855f7' },
          ].map((it, i) => (
            <span key={i} className="shrink-0" style={{ color: it.c }}>
              {it.l}: <span className="text-white/60">{it.v} blocked</span>
            </span>
          ))}
          <span className="ml-auto text-zinc-600 shrink-0">LATENCY: 7ms</span>
          <span className="text-zinc-600 shrink-0">UPTIME: 99.99%</span>
        </div>
      </section>

      {/* ══ SECTION 2: HOW IT WORKS — Animated code cards ══ */}
      <section className="relative border-t border-white/5 bg-zinc-950/90 py-28">
        <div className="mx-auto max-w-[1400px] px-8">
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center mb-16 space-y-3"
          >
            <div className="text-[9px] font-black text-cyan-400 uppercase tracking-[0.4em]">
              AI Intelligence Pipeline
            </div>
            <h2 className="text-4xl font-black tracking-tighter">
              FROM PACKET TO PATCH IN{' '}
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-purple-500">
                8 MILLISECONDS.
              </span>
            </h2>
            <p className="text-zinc-500 max-w-xl mx-auto text-sm">
              Three autonomous stages. One unified outcome: your network stays impenetrable.
            </p>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {CODE_STEPS.map((step, i) => {
              const cls = colorMap[step.color];
              return (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 28 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.12 }}
                  className={`relative rounded-[32px] border border-white/10 bg-gradient-to-b p-0 overflow-hidden shadow-2xl transition-all duration-500 hover:scale-[1.02] ${
                    step.color === 'cyan' ? 'hover:shadow-[0_0_40px_rgba(34,211,238,0.2)] hover:border-cyan-500/30' : 
                    step.color === 'purple' ? 'hover:shadow-[0_0_40px_rgba(168,85,247,0.2)] hover:border-purple-500/30' : 
                    'hover:shadow-[0_0_40px_rgba(16,185,129,0.2)] hover:border-emerald-500/30'
                  } ${cls}`}
                >
                  {/* Card header */}
                  <div className={`flex items-center gap-3 px-5 py-4 border-b border-white/5`}>
                    <span className={`text-xs font-black ${cls.split(' ').pop()}`}>{step.step}</span>
                    <div className="flex gap-1.5">
                      <div className="h-2 w-2 rounded-full bg-red-500/60" />
                      <div className="h-2 w-2 rounded-full bg-yellow-500/60" />
                      <div className="h-2 w-2 rounded-full bg-green-500/60" />
                    </div>
                    <span className={`text-[10px] font-black uppercase tracking-widest ml-2 ${cls.split(' ').pop()}`}>{step.label}</span>
                    <span className="ml-auto text-[10px] text-zinc-500 font-mono tracking-wider">{step.lang}</span>
                  </div>

                  {/* Code */}
                  <div className="px-6 py-6 font-mono text-[13px] leading-[1.8] text-zinc-300 min-h-[220px]">
                    {step.code.map((line, j) => (
                      <motion.div
                        key={j}
                        initial={{ opacity: 0, x: -8 }}
                        whileInView={{ opacity: 1, x: 0 }}
                        viewport={{ once: true }}
                        transition={{ delay: i * 0.12 + j * 0.045 }}
                        className={
                          line.startsWith('#') ? 'text-zinc-600' :
                          line.startsWith('>') ? `font-bold ${cls.split(' ').pop()}` :
                          line.startsWith('✓') ? 'text-emerald-400 font-bold' :
                          line.includes('"') ? 'text-yellow-300' :
                          'text-zinc-300'
                        }
                      >
                        {line || '\u00A0'}
                      </motion.div>
                    ))}
                  </div>

                  {/* Arrow between cards */}
                  {i < CODE_STEPS.length - 1 && (
                    <div className="hidden md:flex absolute -right-5 top-1/2 -translate-y-1/2 z-10 h-8 w-8 rounded-full bg-zinc-950 border border-white/10 items-center justify-center">
                      <ArrowRight className="h-3.5 w-3.5 text-zinc-500" />
                    </div>
                  )}
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ══ SECTION 3: Capability pillars ══ */}
      <section className="relative py-24 bg-black border-t border-white/5">
        <div className="mx-auto max-w-[1400px] px-8">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {[
              { icon: Eye,         title: 'Full-Spectrum Visibility',   color: 'cyan',    desc: 'Every packet, session, and behavioral signal — analyzed in real time across all 7 OSI layers.' },
              { icon: Zap,         title: 'Autonomous Response at Edge', color: 'purple',  desc: 'Distributed edge inference engines fire in <10ms before threats complete their initial handshake.' },
              { icon: ShieldCheck, title: 'Post-Quantum Hardened',       color: 'emerald', desc: 'CRYSTALS-Kyber lattice-based encryption shields your data against current and quantum-era threats.' },
            ].map((p, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className="group p-7 rounded-3xl border border-white/5 bg-white/2 hover:border-white/10 hover:bg-white/4 transition-all"
              >
                <div className={`h-11 w-11 rounded-2xl mb-5 flex items-center justify-center ${
                  p.color === 'cyan'    ? 'bg-cyan-500/10    text-cyan-400'    :
                  p.color === 'purple'  ? 'bg-purple-500/10  text-purple-400'  :
                                          'bg-emerald-500/10 text-emerald-400'
                }`}>
                  <p.icon className="h-5 w-5" />
                </div>
                <h3 className="text-sm font-black text-white mb-2 uppercase tracking-tight">{p.title}</h3>
                <p className="text-xs text-zinc-500 leading-relaxed">{p.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ══ SECTION 4: CTA ══ */}
      <section className="relative py-20 border-t border-white/5">
        <div className="mx-auto max-w-[1400px] px-8">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="relative overflow-hidden rounded-[40px] border border-white/8 p-14 text-center"
            style={{ background: 'linear-gradient(135deg,rgba(6,182,212,0.12),rgba(124,58,237,0.12),rgba(239,68,68,0.06))' }}
          >
            <div className="absolute inset-0 opacity-[0.05]"
              style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,0.3) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.3) 1px,transparent 1px)', backgroundSize: '28px 28px' }} />
            <div className="relative z-10 space-y-6">
              <p className="text-[9px] font-black text-cyan-400 uppercase tracking-[0.5em]">Trusted by 500+ Enterprise Security Teams</p>
              <h2 className="text-5xl font-black tracking-tighter">
                THE ONLY PLATFORM
                <br />
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-purple-500">
                  THAT SEES EVERYTHING.
                </span>
              </h2>
              <div className="flex flex-wrap justify-center gap-4 pt-2">
                <button
                  onClick={() => navigate('/dashboard')}
                  className="px-10 py-4 rounded-2xl bg-white text-black font-black uppercase tracking-widest text-sm hover:bg-zinc-100 transition-colors shadow-2xl"
                >
                  Deploy Free — No Card
                </button>
                <button className="px-10 py-4 rounded-2xl border border-white/20 bg-white/8 text-white font-black uppercase tracking-widest text-sm backdrop-blur-xl hover:bg-white/12 transition-colors">
                  Talk to Intelligence Team
                </button>
              </div>
            </div>
          </motion.div>
        </div>
      </section>
    </div>
  );
};

export default Hero;
