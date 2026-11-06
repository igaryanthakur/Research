/**
 * IncidentDetailModal.tsx
 * ────────────────────────
 * Full-detail modal opened when the user clicks "View Deep Analysis →"
 * on an incident card. Pulls detailed data from Firestore in real-time.
 */
import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X, ShieldAlert, CheckCircle2, AlertTriangle, Activity,
  Clock, Cpu, Zap, Database, ChevronRight, BarChart3,
} from 'lucide-react';
import { doc, onSnapshot } from 'firebase/firestore';
import { db } from '@/lib/firebase';
import type { RecentIncident } from '@/hooks/useFirestoreAnalytics';

// ── Types ─────────────────────────────────────────────────────────────────────
interface Props {
  incidentId: string;
  uid: string;
  onClose: () => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const VERDICT_STYLE = {
  MALICIOUS:  { bg: 'bg-red-500/15 border-red-500/30',     text: 'text-red-400',    icon: AlertTriangle },
  SUSPICIOUS: { bg: 'bg-orange-500/15 border-orange-500/30', text: 'text-orange-400', icon: ShieldAlert },
  BENIGN:     { bg: 'bg-emerald-500/15 border-emerald-500/30', text: 'text-emerald-400', icon: CheckCircle2 },
};

const SHAP_COLOR = (w: number) =>
  w > 0.6 ? 'bg-red-500' : w > 0.3 ? 'bg-orange-500' : 'bg-cyan-500';

const THREAT_LABEL: Record<string, string> = {
  phishing:         'Phishing Detection',
  url:              'URL Analysis',
  prompt_injection: 'Prompt Injection',
  anomaly:          'Anomaly Detection',
};

// ── Component ─────────────────────────────────────────────────────────────────
const IncidentDetailModal: React.FC<Props> = ({ incidentId, uid, onClose }) => {
  const [incident, setIncident] = useState<RecentIncident | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const ref = doc(db, 'users', uid, 'incidents', incidentId);
    const unsub = onSnapshot(ref, snap => {
      if (!snap.exists()) { setLoading(false); return; }
      const d = snap.data() as Record<string, any>;
      setIncident({
        id:               d.incident_id || incidentId,
        threat_type:      d.threat_type || 'unknown',
        verdict:          (d.verdict || 'BENIGN').toUpperCase(),
        confidence:       d.confidence ?? 0,
        risk_band:        d.risk_band || '',
        riskLevel:        d.riskLevel || 'Low',
        explanation:      d.explanation || d.description || 'No explanation available.',
        action:           d.action || 'No action required.',
        detection_mode:   d.detection_mode || 'heuristic',
        shap_features:    Array.isArray(d.shap_features) ? d.shap_features : [],
        timestamp:        d.timestamp || new Date().toISOString(),
        processing_time_ms: d.processing_time_ms || 0,
      });
      setLoading(false);
    }, () => setLoading(false));
    return unsub;
  }, [incidentId, uid]);

  const vStyle = incident
    ? (VERDICT_STYLE[incident.verdict as keyof typeof VERDICT_STYLE] || VERDICT_STYLE.BENIGN)
    : VERDICT_STYLE.BENIGN;
  const VIcon = vStyle.icon;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
        onClick={e => { if (e.target === e.currentTarget) onClose(); }}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.92, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.92, y: 20 }}
          transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          className="relative w-full max-w-3xl max-h-[90vh] overflow-y-auto custom-scrollbar bg-zinc-950 border border-white/10 rounded-[32px] shadow-[0_40px_80px_rgba(0,0,0,0.8)]"
        >
          {/* Close button */}
          <button
            onClick={onClose}
            className="absolute top-6 right-6 z-10 p-2 rounded-xl bg-white/5 border border-white/10 text-zinc-400 hover:text-white hover:bg-white/10 transition-all"
          >
            <X className="h-5 w-5" />
          </button>

          {/* Loading state */}
          {loading && (
            <div className="p-12 flex items-center justify-center">
              <div className="h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
            </div>
          )}

          {!loading && !incident && (
            <div className="p-12 text-center text-zinc-500 font-bold uppercase tracking-widest text-sm">
              Incident data not found
            </div>
          )}

          {!loading && incident && (() => {
            const conf = Math.round(incident.confidence * 100);
            return (
              <div className="p-8 space-y-8">
                {/* ── Header ── */}
                <div className={`flex items-start justify-between p-6 rounded-2xl border ${vStyle.bg}`}>
                  <div className="flex items-center gap-4">
                    <div className={`p-4 rounded-2xl bg-white/5 border border-white/10`}>
                      <VIcon className={`h-8 w-8 ${vStyle.text}`} />
                    </div>
                    <div>
                      <div className={`text-[10px] font-black uppercase tracking-[0.3em] mb-1 ${vStyle.text}`}>
                        {THREAT_LABEL[incident.threat_type] || incident.threat_type}
                      </div>
                      <h2 className={`text-3xl font-black uppercase tracking-tighter ${vStyle.text}`}>
                        {incident.verdict}
                      </h2>
                      <div className="flex items-center gap-3 mt-2">
                        <span className="text-[10px] text-zinc-500 font-black uppercase tracking-widest flex items-center gap-1.5">
                          <Clock className="h-3 w-3" />
                          {new Date(incident.timestamp).toLocaleString()}
                        </span>
                        <span className="text-zinc-700">•</span>
                        <span className="text-[10px] text-zinc-500 font-black uppercase tracking-widest">
                          {incident.id}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className={`text-5xl font-black tabular-nums ${vStyle.text}`}>{conf}%</div>
                    <div className="text-[10px] text-zinc-500 font-black uppercase tracking-widest mt-1">Confidence</div>
                    <div className={`mt-2 px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-widest border ${vStyle.bg} ${vStyle.text}`}>
                      {incident.riskLevel} Severity
                    </div>
                  </div>
                </div>

                {/* ── Meta tiles ── */}
                <div className="grid grid-cols-3 gap-4">
                  {[
                    { label: 'Detection Mode', value: incident.detection_mode, icon: Cpu },
                    { label: 'Risk Band',       value: incident.risk_band || 'N/A', icon: ShieldAlert },
                    { label: 'Processing Time', value: `${incident.processing_time_ms}ms`, icon: Zap },
                  ].map(({ label, value, icon: Icon }) => (
                    <div key={label} className="p-4 rounded-2xl bg-white/3 border border-white/5 space-y-2">
                      <div className="flex items-center gap-2 text-zinc-500">
                        <Icon className="h-4 w-4" />
                        <span className="text-[9px] font-black uppercase tracking-widest">{label}</span>
                      </div>
                      <div className="text-sm font-black text-white uppercase tracking-tight">{value}</div>
                    </div>
                  ))}
                </div>

                {/* ── AI Explanation ── */}
                <div className="space-y-3">
                  <h3 className="text-[10px] font-black text-cyan-400 uppercase tracking-[0.3em] flex items-center gap-2">
                    <Activity className="h-4 w-4" /> AI Threat Assessment
                  </h3>
                  <div className="p-6 rounded-2xl bg-black/60 border border-white/5">
                    <p className="text-zinc-300 text-sm leading-relaxed font-mono">{incident.explanation}</p>
                  </div>
                </div>

                {/* ── Recommended Action ── */}
                <div className="space-y-3">
                  <h3 className="text-[10px] font-black text-orange-400 uppercase tracking-[0.3em] flex items-center gap-2">
                    <ChevronRight className="h-4 w-4" /> Recommended Action
                  </h3>
                  <div className="p-6 rounded-2xl bg-orange-500/5 border border-orange-500/10">
                    <p className="text-zinc-300 text-sm leading-relaxed">{incident.action || 'No specific action recommended.'}</p>
                  </div>
                </div>

                {/* ── SHAP Feature Importance ── */}
                {incident.shap_features.length > 0 && (
                  <div className="space-y-3">
                    <h3 className="text-[10px] font-black text-purple-400 uppercase tracking-[0.3em] flex items-center gap-2">
                      <BarChart3 className="h-4 w-4" /> Signal Attribution (SHAP)
                    </h3>
                    <div className="space-y-3">
                      {incident.shap_features
                        .slice()
                        .sort((a, b) => b.weight - a.weight)
                        .map((f, i) => {
                          const w = typeof f.weight === 'number' ? f.weight : 0;
                          const pct = Math.round(w * 100);
                          return (
                            <div key={i} className="space-y-1.5">
                              <div className="flex items-center justify-between">
                                <span className="text-[10px] font-black text-zinc-300 uppercase tracking-tight flex items-center gap-2">
                                  <Database className="h-3 w-3 text-zinc-600" />
                                  {f.feature}
                                </span>
                                <span className="text-[10px] font-black text-zinc-400 tabular-nums">{pct}%</span>
                              </div>
                              <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
                                <motion.div
                                  initial={{ width: 0 }}
                                  animate={{ width: `${pct}%` }}
                                  transition={{ delay: i * 0.06, duration: 0.5 }}
                                  className={`h-full rounded-full ${SHAP_COLOR(w)}`}
                                />
                              </div>
                            </div>
                          );
                        })}
                    </div>
                  </div>
                )}
              </div>
            );
          })()}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};

export default IncidentDetailModal;
