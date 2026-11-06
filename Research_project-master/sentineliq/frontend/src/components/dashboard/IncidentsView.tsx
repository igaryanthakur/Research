import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  History,
  ShieldAlert,
  AlertCircle,
  Clock,
  Search,
  Filter,
  Wifi,
  WifiOff,
  RefreshCw,
  TrendingUp,
  Lock,
  Trash2,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useFirebaseIncidents } from '@/hooks/useFirebaseIncidents';
import { useAuth } from '@/hooks/useAuth';
import { securityService } from '@/services/securityService';
import IncidentDetailModal from './IncidentDetailModal';
import type { RiskLevel } from '@/types/security';

// ─── Shimmer Skeleton ────────────────────────────────────────────────────────
const IncidentSkeleton: React.FC<{ count?: number }> = ({ count = 5 }) => (
  <div className="space-y-4 animate-pulse">
    {Array.from({ length: count }).map((_, i) => (
      <div key={i} className="p-6 rounded-[24px] border border-white/5 bg-white/3 flex items-start gap-6">
        <div className="h-12 w-12 rounded-2xl bg-zinc-800 shrink-0" />
        <div className="flex-1 space-y-3">
          <div className="flex items-center gap-3">
            <div className="h-4 w-36 bg-zinc-800 rounded-full" />
            <div className="h-4 w-20 bg-zinc-800 rounded-full" />
          </div>
          <div className="h-3 w-full bg-zinc-900 rounded-full" />
          <div className="h-3 w-3/4 bg-zinc-900 rounded-full" />
        </div>
      </div>
    ))}
  </div>
);

// ─── Risk Badge ──────────────────────────────────────────────────────────────
const RISK_STYLES: Record<RiskLevel, { bg: string; text: string; icon: React.ReactNode }> = {
  Critical: {
    bg:   'bg-red-500/15 border-red-500/25 text-red-400',
    text: 'bg-red-500/20 text-red-400',
    icon: <AlertCircle className="h-6 w-6" />,
  },
  High: {
    bg:   'bg-orange-500/15 border-orange-500/25 text-orange-400',
    text: 'bg-orange-500/20 text-orange-400',
    icon: <ShieldAlert className="h-6 w-6" />,
  },
  Medium: {
    bg:   'bg-yellow-500/15 border-yellow-500/25 text-yellow-400',
    text: 'bg-yellow-500/20 text-yellow-400',
    icon: <ShieldAlert className="h-6 w-6" />,
  },
  Low: {
    bg:   'bg-cyan-500/15 border-cyan-500/25 text-cyan-400',
    text: 'bg-cyan-500/20 text-cyan-400',
    icon: <History className="h-6 w-6" />,
  },
};

// ─── Main Component ──────────────────────────────────────────────────────────
const IncidentsView: React.FC = () => {
  const { uid } = useAuth();
  const navigate = useNavigate();
  const { incidents, loading, error, isLive } = useFirebaseIncidents(uid);
  const [search, setSearch]   = useState('');
  const [filter, setFilter]   = useState<RiskLevel | 'All'>('All');
  const [showFilter, setShowFilter] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleDelete = async (incidentId: string) => {
    if (!uid) return;
    const confirmed = window.confirm('Permanently delete this incident from your history? This cannot be undone.');
    if (!confirmed) return;
    setDeletingId(incidentId);
    try {
      await securityService.deleteIncident(uid, incidentId);
    } catch (err) {
      console.error('Delete failed:', err);
      alert('Delete failed. Please try again.');
    } finally {
      setDeletingId(null);
    }
  };

  const filtered = useMemo(() => {
    let result = incidents;
    if (filter !== 'All') result = result.filter(i => i.riskLevel === filter);
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        i => i.type.toLowerCase().includes(q) || i.description.toLowerCase().includes(q)
      );
    }
    return result;
  }, [incidents, filter, search]);

  const counts = useMemo(() => ({
    critical: incidents.filter(i => i.riskLevel === 'Critical').length,
    high:     incidents.filter(i => i.riskLevel === 'High').length,
    medium:   incidents.filter(i => i.riskLevel === 'Medium').length,
    low:      incidents.filter(i => i.riskLevel === 'Low').length,
  }), [incidents]);


  return (
    <>
      {/* ── Sign-in gate for unauthenticated users ── */}
      {!uid && (
        <div className="h-full flex flex-col items-center justify-center gap-6 p-8 text-center">
          <div className="h-16 w-16 rounded-[24px] bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center shadow-[0_0_40px_rgba(6,182,212,0.15)]">
            <Lock className="h-8 w-8 text-cyan-400" />
          </div>
          <div className="space-y-2">
            <h3 className="text-xl font-black text-white uppercase tracking-tighter">Your Private History</h3>
            <p className="text-sm text-zinc-500 max-w-sm leading-relaxed font-medium">
              Sign in to access your scan history. Your data is stored privately —
              encrypted to your account, invisible to admins and other users.
            </p>
          </div>
          <button
            onClick={() => navigate('/auth')}
            className="px-8 py-3 rounded-2xl bg-cyan-500 text-white text-[11px] font-black uppercase tracking-[0.2em] shadow-[0_0_30px_rgba(6,182,212,0.3)] hover:shadow-[0_0_50px_rgba(6,182,212,0.5)] hover:-translate-y-0.5 transition-all"
          >
            Sign In / Register
          </button>
          <p className="text-[9px] text-zinc-700 font-bold uppercase tracking-widest">
            Scans work without login — sign in only required to save history
          </p>
        </div>
      )}

      {/* ── Main incidents view (signed in) ── */}
      {uid && (
      <div className="p-8 space-y-6 h-full flex flex-col overflow-hidden">

      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h2 className="text-2xl font-black text-white uppercase tracking-tighter">
              Incident Repository
            </h2>
            {/* Live / Offline badge */}
            {isLive ? (
              <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/15 border border-emerald-500/25 text-emerald-400 text-[9px] font-black uppercase tracking-widest">
                <Wifi className="h-3 w-3" />
                Firebase Live
              </span>
            ) : error ? (
              <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-red-500/15 border border-red-500/25 text-red-400 text-[9px] font-black uppercase tracking-widest">
                <WifiOff className="h-3 w-3" />
                Offline
              </span>
            ) : (
              <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-zinc-800 border border-white/5 text-zinc-400 text-[9px] font-black uppercase tracking-widest">
                <RefreshCw className="h-3 w-3 animate-spin" />
                Connecting
              </span>
            )}
          </div>
          <p className="text-zinc-500 text-sm font-bold uppercase tracking-widest">
            {isLive
              ? `${incidents.length} private events — visible only to you`
              : 'Your chronological log of detected security events'}
          </p>
        </div>

        {/* Search + Filter */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-4 py-2 rounded-xl border border-white/5 bg-white/5">
            <Search className="h-4 w-4 text-zinc-500" />
            <input
              type="text"
              placeholder="Search incidents..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="bg-transparent text-[11px] font-bold text-white placeholder:text-zinc-600 focus:outline-none w-44 uppercase tracking-widest"
            />
          </div>
          <div className="relative">
            <button
              onClick={() => setShowFilter(f => !f)}
              className={`p-2.5 rounded-xl border transition-colors ${
                filter !== 'All'
                  ? 'bg-cyan-500/10 border-cyan-500/20 text-cyan-400'
                  : 'bg-white/5 border-white/5 text-zinc-400 hover:text-white'
              }`}
            >
              <Filter className="h-4 w-4" />
            </button>
            <AnimatePresence>
              {showFilter && (
                <motion.div
                  initial={{ opacity: 0, y: 6, scale: 0.97 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 6, scale: 0.97 }}
                  transition={{ duration: 0.15 }}
                  className="absolute right-0 top-full mt-2 z-50 w-44 rounded-2xl border border-white/10 bg-zinc-950/95 backdrop-blur-xl overflow-hidden shadow-2xl"
                >
                  {(['All', 'Critical', 'High', 'Medium', 'Low'] as const).map(lvl => (
                    <button
                      key={lvl}
                      onClick={() => { setFilter(lvl); setShowFilter(false); }}
                      className={`w-full text-left px-4 py-2.5 text-[11px] font-black uppercase tracking-widest transition-colors ${
                        filter === lvl
                          ? 'bg-cyan-500/10 text-cyan-400'
                          : 'text-zinc-400 hover:bg-white/5 hover:text-white'
                      }`}
                    >
                      {lvl} {lvl !== 'All' && `(${counts[lvl.toLowerCase() as keyof typeof counts]})`}
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>

      {/* ── Summary Pills ── */}
      <div className="flex flex-wrap gap-3">
        {([
          { label: 'Critical', count: counts.critical, color: 'bg-red-500/10 border-red-500/20 text-red-400' },
          { label: 'High',     count: counts.high,     color: 'bg-orange-500/10 border-orange-500/20 text-orange-400' },
          { label: 'Medium',   count: counts.medium,   color: 'bg-yellow-500/10 border-yellow-500/20 text-yellow-400' },
          { label: 'Low',      count: counts.low,      color: 'bg-cyan-500/10 border-cyan-500/20 text-cyan-400' },
        ]).map(({ label, count, color }) => (
          <div key={label} className={`px-4 py-1.5 rounded-full border text-[10px] font-black uppercase tracking-widest ${color}`}>
            {label}: {count}
          </div>
        ))}
        <div className="ml-auto flex items-center gap-1.5 text-[10px] font-black text-zinc-500 uppercase tracking-widest">
          <TrendingUp className="h-3 w-3" />
          Total: {incidents.length}
        </div>
      </div>

      {/* ── Content ── */}
      <div className="flex-1 overflow-y-auto custom-scrollbar space-y-4 pr-2 min-h-0">

        {/* Loading */}
        {loading && <IncidentSkeleton count={6} />}

        {/* Error */}
        {!loading && error && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center gap-4 py-20 text-center"
          >
            <div className="h-14 w-14 rounded-2xl bg-red-500/10 flex items-center justify-center">
              <WifiOff className="h-7 w-7 text-red-400" />
            </div>
            <div>
              <p className="text-sm font-black text-white uppercase tracking-widest mb-2">
                {error.includes('not provisioned') ? 'Firestore Not Set Up' : 'Firebase Connection Failed'}
              </p>
              <p className="text-xs text-zinc-400 max-w-sm leading-relaxed">{error}</p>
              {error.includes('not provisioned') && (
                <a
                  href="https://console.firebase.google.com/project/cybershield-e57d9/firestore"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 inline-block px-5 py-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-xs font-black text-cyan-400 uppercase tracking-widest hover:bg-cyan-500/20 transition-colors"
                >
                  Open Firebase Console →
                </a>
              )}
            </div>
            <button
              onClick={() => window.location.reload()}
              className="px-5 py-2 rounded-xl bg-white/5 border border-white/10 text-xs font-black text-white uppercase tracking-widest hover:bg-white/10 transition-colors"
            >
              Retry Connection
            </button>
          </motion.div>
        )}

        {/* Empty state */}
        {!loading && !error && filtered.length === 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center gap-4 py-20 text-center"
          >
            <div className="h-14 w-14 rounded-2xl bg-white/5 flex items-center justify-center">
              <History className="h-7 w-7 text-zinc-600" />
            </div>
            <p className="text-sm font-black text-zinc-500 uppercase tracking-widest">
              {search || filter !== 'All' ? 'No matching incidents' : 'No incidents recorded yet'}
            </p>
            <p className="text-xs text-zinc-600 max-w-xs">
              {search || filter !== 'All'
                ? 'Try adjusting your search or filter.'
                : 'Incidents will appear here in real-time as they are detected and written to Firestore.'}
            </p>
          </motion.div>
        )}

        {/* Incident cards */}
        {!loading && (
          <AnimatePresence initial={false}>
            {filtered.map((incident, i) => {
              const styles = RISK_STYLES[incident.riskLevel];
              return (
                <motion.div
                  key={incident.id}
                  layout
                  initial={{ opacity: 0, x: -16 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 16, height: 0 }}
                  transition={{ delay: i * 0.04, duration: 0.25 }}
                  className={`p-6 rounded-[24px] border bg-white/3 hover:bg-white/6 transition-all group flex items-start gap-6 ${styles.bg}`}
                >
                  {/* Icon */}
                  <div className={`h-12 w-12 rounded-2xl flex items-center justify-center shrink-0 border ${styles.bg}`}>
                    {styles.icon}
                  </div>

                  <div className="flex-1 min-w-0">
                    {/* Title row */}
                    <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
                      <div className="flex items-center gap-3 flex-wrap">
                        <h4 className="text-base font-black text-white uppercase tracking-tight">{incident.type}</h4>
                        <span className={`px-3 py-0.5 rounded-full text-[9px] font-black uppercase tracking-widest border ${styles.bg}`}>
                          {incident.riskLevel} Severity
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 text-zinc-500">
                        <Clock className="h-3 w-3" />
                        <span className="text-[10px] font-bold uppercase tabular-nums">
                          {new Date(incident.timestamp).toLocaleString()}
                        </span>
                      </div>
                    </div>

                    <p className="text-zinc-400 text-sm font-medium line-clamp-2 mb-4">
                      {incident.description}
                    </p>

                    <div className="flex items-center gap-4">
                      <button
                        onClick={() => setSelectedId(incident.id)}
                        className="text-[10px] font-black text-cyan-400 uppercase tracking-[0.2em] hover:text-white transition-colors"
                      >
                        View Deep Analysis →
                      </button>
                      <div className="h-1 w-1 rounded-full bg-zinc-800" />
                      <button
                        onClick={() => handleDelete(incident.id)}
                        disabled={deletingId === incident.id}
                        className="flex items-center gap-1.5 text-[10px] font-black text-zinc-600 uppercase tracking-[0.2em] hover:text-red-400 transition-colors disabled:opacity-40"
                      >
                        <Trash2 className="h-3 w-3" />
                        {deletingId === incident.id ? 'Deleting…' : 'Delete'}
                      </button>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        )}
      </div>
      </div>
      )}

    {/* Detail modal — rendered as sibling to avoid scroll clipping */}
    {selectedId && uid && (
      <IncidentDetailModal
        incidentId={selectedId}
        uid={uid}
        onClose={() => setSelectedId(null)}
      />
    )}
  </>
  );
};

export default IncidentsView;
