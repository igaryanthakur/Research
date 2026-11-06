/**
 * ThreatAnalysis.tsx
 * ───────────────────
 * Live Threat Intelligence Hub — all charts are powered by real Firestore
 * incident data via useFirestoreAnalytics. Charts update automatically the
 * moment a new scan is saved.
 */
import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, PieChart, Pie, Cell, AreaChart, Area,
} from 'recharts';
import {
  BarChart3, LineChart as LineChartIcon, PieChart as PieChartIcon,
  Clock, AlertTriangle, Activity, Mail, Link2, Database, ShieldAlert,
  Wifi, WifiOff, RefreshCw, Zap, Shield,
} from 'lucide-react';
import { useFirestoreAnalytics } from '@/hooks/useFirestoreAnalytics';
import { useAuth } from '@/hooks/useAuth';

// ── Static engine info ────────────────────────────────────────────────────────
const ENGINE_CARDS = [
  {
    id:          'phishing',
    title:       'Phishing Detection',
    description: 'AI scans for deceptive language, sender mismatches, and psychological urgency triggers missed by traditional filters.',
    color:       'text-cyan-400', bg: 'bg-cyan-500/10', border: 'border-cyan-500/20',
    icon:        Mail,
  },
  {
    id:          'url',
    title:       'Link Analysis',
    description: 'Dissects URLs to find malicious redirects, fake domains (typosquatting), and watering-hole sites.',
    color:       'text-purple-400', bg: 'bg-purple-500/10', border: 'border-purple-500/20',
    icon:        Link2,
  },
  {
    id:          'prompt_injection',
    title:       'Injection Protection',
    description: 'Neutralizes SQL injection, XSS, and prompt injection attacks before they reach your databases.',
    color:       'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20',
    icon:        Database,
  },
  {
    id:          'anomaly',
    title:       'Behavioral Anomaly',
    description: 'Neural engine establishes a normal baseline and flags statistical deviations as potential insider threats.',
    color:       'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/20',
    icon:        ShieldAlert,
  },
];

// ── Custom tooltip ────────────────────────────────────────────────────────────
const DarkTooltip = {
  contentStyle: { backgroundColor: '#18181b', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '14px', padding: '10px 14px' },
  itemStyle:    { color: '#22d3ee', fontWeight: 700, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.1em' },
  labelStyle:   { color: '#71717a', fontWeight: 700, fontSize: 10, textTransform: 'uppercase' },
};

// ── Stat tile ────────────────────────────────────────────────────────────────
const StatTile: React.FC<{ label: string; value: string | number; icon: React.ReactNode; color: string }> =
  ({ label, value, icon, color }) => (
    <div className="p-4 rounded-2xl bg-white/3 border border-white/5 flex items-center justify-between gap-4">
      <div>
        <div className="text-[9px] font-black text-zinc-500 uppercase tracking-widest mb-1">{label}</div>
        <div className={`text-2xl font-black tabular-nums ${color}`}>{value}</div>
      </div>
      <div className={`h-10 w-10 rounded-xl flex items-center justify-center bg-white/5 ${color}`}>{icon}</div>
    </div>
  );

// ── Main Component ────────────────────────────────────────────────────────────
const ThreatAnalysis: React.FC = () => {
  const { uid } = useAuth();
  const [chartType, setChartType] = useState<'bar' | 'line' | 'pie'>('bar');
  const {
    threatFreq, peakHours, severityDist,
    totalScans, totalMalicious, avgConfidence,
    recentIncidents, loading, error,
  } = useFirestoreAnalytics(uid);

  // ── Peak hour window ──────────────────────────────────────────────────────
  const peakHour = peakHours.reduce(
    (best, h) => h.threats > best.threats ? h : best,
    { hour: '--:--', threats: 0 },
  );

  return (
    <div className="p-8 space-y-8 h-full overflow-y-auto custom-scrollbar bg-black/40 backdrop-blur-3xl relative">
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff05_1px,transparent_1px),linear-gradient(to_bottom,#ffffff05_1px,transparent_1px)] bg-[size:40px_40px] pointer-events-none" />

      {/* ── Header ── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative">
        <div className="space-y-1">
          <h2 className="text-3xl font-black text-white uppercase tracking-tighter">Threat Intelligence Hub</h2>
          <p className="text-zinc-500 text-xs font-black uppercase tracking-[0.2em] flex items-center gap-2">
            <Activity className="h-4 w-4 text-cyan-400" />
            {loading ? 'Loading live data...' : `${totalScans} total scans · ${totalMalicious} threats detected`}
            {/* Live badge */}
            {!loading && !error && (
              <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/15 border border-emerald-500/25 text-emerald-400 text-[9px] font-black uppercase tracking-widest">
                <Wifi className="h-3 w-3" /> Firebase Live
              </span>
            )}
            {error && (
              <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-red-500/15 border border-red-500/25 text-red-400 text-[9px] font-black uppercase tracking-widest">
                <WifiOff className="h-3 w-3" /> Offline
              </span>
            )}
          </p>
        </div>

        <div className="flex bg-zinc-900/80 p-1.5 rounded-2xl border border-white/10 backdrop-blur-xl">
          {([
            { key: 'bar',  icon: BarChart3 },
            { key: 'line', icon: LineChartIcon },
            { key: 'pie',  icon: PieChartIcon },
          ] as const).map(({ key, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setChartType(key)}
              className={`p-2.5 rounded-xl transition-all ${chartType === key ? 'bg-cyan-500 text-white shadow-[0_0_15px_rgba(6,182,212,0.4)]' : 'text-zinc-500 hover:text-white'}`}
            >
              <Icon className="h-5 w-5" />
            </button>
          ))}
        </div>
      </div>

      {/* ── KPI tiles ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 relative">
        <StatTile label="Total Scans"     value={totalScans}        icon={<Shield className="h-5 w-5" />}    color="text-cyan-400" />
        <StatTile label="Threats Found"   value={totalMalicious}    icon={<AlertTriangle className="h-5 w-5" />} color="text-red-400" />
        <StatTile label="Avg Confidence"  value={`${avgConfidence}%`} icon={<Zap className="h-5 w-5" />}     color="text-purple-400" />
        <StatTile label="Detection Rate"  value={totalScans > 0 ? `${Math.round((totalMalicious / totalScans) * 100)}%` : '0%'} icon={<Activity className="h-5 w-5" />} color="text-orange-400" />
      </div>

      {/* ── Loading / Error ── */}
      <AnimatePresence>
        {loading && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center justify-center py-20 gap-3 text-zinc-500">
            <RefreshCw className="h-5 w-5 animate-spin" />
            <span className="text-sm font-black uppercase tracking-widest">Loading Firestore data...</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Engine Cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 relative">
        {ENGINE_CARDS.map(e => (
          <motion.div
            key={e.id}
            whileHover={{ scale: 1.02, y: -4 }}
            transition={{ type: 'spring', stiffness: 300 }}
            className={`p-6 rounded-[28px] border-2 ${e.bg} ${e.border} space-y-4 bg-black/40 backdrop-blur-xl group`}
          >
            <div className="flex items-center justify-between">
              <div className={`p-3 rounded-2xl ${e.bg} border ${e.border}`}>
                <e.icon className={`h-6 w-6 ${e.color}`} />
              </div>
              {/* Show real count from incidents */}
              <span className={`text-sm font-black tabular-nums ${e.color}`}>
                {recentIncidents.filter(i => i.threat_type === e.id).length}
              </span>
            </div>
            <div>
              <h3 className={`text-sm font-black uppercase tracking-tighter ${e.color}`}>{e.title}</h3>
              <p className="text-[10px] text-zinc-400 leading-relaxed font-bold uppercase tracking-tight opacity-80 mt-1">{e.description}</p>
            </div>
          </motion.div>
        ))}
      </div>

      {/* ── Main Charts ── */}
      {!loading && (
        <div className="grid grid-cols-12 gap-6 relative">
          {/* Threat Distribution Chart */}
          <motion.div
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            className="col-span-12 lg:col-span-8 p-6 rounded-[32px] border border-white/10 bg-white/5 backdrop-blur-xl"
          >
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xs font-black text-cyan-400 uppercase tracking-[0.3em] flex items-center gap-2">
                <Activity className="h-4 w-4" /> Threat Distribution
              </h3>
              <span className="text-[9px] font-black text-zinc-600 uppercase tracking-widest">
                {totalScans > 0 ? 'Live Firestore data' : 'No scans yet — run a scan to see data'}
              </span>
            </div>

            <div className="h-[280px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                {chartType === 'bar' ? (
                  <BarChart data={threatFreq}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" vertical={false} />
                    <XAxis dataKey="name" stroke="#71717a" fontSize={10} fontWeight={700} tickLine={false} axisLine={false} />
                    <YAxis stroke="#71717a" fontSize={10} fontWeight={700} tickLine={false} axisLine={false} />
                    <Tooltip {...DarkTooltip} />
                    <Bar dataKey="frequency"    fill="#22d3ee" radius={[6, 6, 0, 0]} barSize={36} name="Frequency" />
                    <Bar dataKey="severityScore" fill="#8b5cf6" radius={[6, 6, 0, 0]} barSize={36} name="Avg Conf %" />
                  </BarChart>
                ) : chartType === 'line' ? (
                  <LineChart data={threatFreq}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" vertical={false} />
                    <XAxis dataKey="name" stroke="#71717a" fontSize={10} fontWeight={700} tickLine={false} axisLine={false} />
                    <YAxis stroke="#71717a" fontSize={10} fontWeight={700} tickLine={false} axisLine={false} />
                    <Tooltip {...DarkTooltip} />
                    <Line type="monotone" dataKey="frequency"    stroke="#22d3ee" strokeWidth={3} dot={{ fill: '#22d3ee', r: 5 }} name="Frequency" />
                    <Line type="monotone" dataKey="severityScore" stroke="#8b5cf6" strokeWidth={3} dot={{ fill: '#8b5cf6', r: 5 }} name="Avg Conf %" />
                  </LineChart>
                ) : (
                  <PieChart>
                    <Pie
                      data={severityDist} cx="50%" cy="50%"
                      innerRadius={60} outerRadius={110} paddingAngle={4}
                      dataKey="value" nameKey="name"
                    >
                      {severityDist.map((entry, i) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip {...DarkTooltip} formatter={(v) => v != null ? `${v}%` : ''} />
                  </PieChart>
                )}
              </ResponsiveContainer>
            </div>

            <div className="mt-4 flex items-center gap-6 justify-center">
              <div className="flex items-center gap-2">
                <div className="h-3 w-3 rounded-sm bg-cyan-400" />
                <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Frequency</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="h-3 w-3 rounded-sm bg-purple-500" />
                <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Avg Confidence %</span>
              </div>
            </div>
          </motion.div>

          {/* Peak Hours */}
          <motion.div
            initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}
            className="col-span-12 lg:col-span-4 p-6 rounded-[32px] border border-white/10 bg-white/5 backdrop-blur-xl"
          >
            <h3 className="text-xs font-black text-white uppercase tracking-[0.3em] flex items-center gap-2 mb-6">
              <Clock className="h-4 w-4 text-cyan-400" /> Activity By Hour
            </h3>

            <div className="h-[240px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={peakHours}>
                  <defs>
                    <linearGradient id="gradThreats" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#22d3ee" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#22d3ee" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="hour" stroke="#71717a" fontSize={8} fontWeight={700} tickLine={false} axisLine={false}
                    interval={3} />
                  <YAxis hide />
                  <Tooltip {...DarkTooltip} />
                  <Area type="monotone" dataKey="threats" stroke="#22d3ee" fillOpacity={1} fill="url(#gradThreats)" name="Scans" />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className="mt-4 p-4 rounded-2xl bg-white/5 border border-white/5">
              <div className="text-[10px] font-black text-cyan-400 uppercase tracking-widest mb-1">Peak Hour</div>
              <div className="text-xl font-black text-white">{peakHour.hour}</div>
              <p className="text-[10px] text-zinc-500 font-bold uppercase mt-1">
                {peakHour.threats > 0 ? `${peakHour.threats} scan${peakHour.threats > 1 ? 's' : ''} recorded` : 'No activity yet'}
              </p>
            </div>
          </motion.div>

          {/* Severity Distribution Bar */}
          <div className="col-span-12 grid grid-cols-2 md:grid-cols-4 gap-4">
            {severityDist.map((s, i) => (
              <div key={i} className="p-4 rounded-2xl border border-white/5 bg-white/3 flex items-center justify-between">
                <div>
                  <div className="text-[10px] font-black text-zinc-500 uppercase tracking-widest">{s.name} Incidents</div>
                  <div className="text-2xl font-black text-white tabular-nums">{s.value}%</div>
                </div>
                <div className="h-10 w-10 rounded-xl flex items-center justify-center bg-white/5">
                  <AlertTriangle className="h-5 w-5" style={{ color: s.color }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default ThreatAnalysis;
