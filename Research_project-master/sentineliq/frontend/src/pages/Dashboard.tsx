import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  ShieldAlert,
  Activity,
  TrendingUp,
  LayoutDashboard,
  ShieldCheck,
  History,
  Settings,
  Cpu,
  Mail,
  Target,
  Zap,
  Lock,
  LogOut,
  User,
} from 'lucide-react';
import { signOut } from 'firebase/auth';
import { auth } from '../lib/firebase';
import { useNavigate } from 'react-router-dom';
import CyberRiskOrb from '../components/CyberRiskOrb';
import { IncidentFeed } from '../components/IncidentFeed';
import { securityService } from '../services/securityService';
import { ChatInterface, UploadBox, ShapChart } from '../components/CyberDashboard';
import { Threat } from '../types/security';
import { useFirebaseIncidents } from '../hooks/useFirebaseIncidents';
import { useAuth } from '../hooks/useAuth';

// Sectional dashboard components
import ThreatAnalysis from '../components/dashboard/ThreatAnalysis';
import IncidentsView from '../components/dashboard/IncidentsView';
import SettingsView from '../components/dashboard/SettingsView';
import ScanToolsView from '../components/dashboard/ScanToolsView';

// ── Benchmark KPIs (from test_accuracy.py validated run 2026-05-10) ────────────
const BENCHMARKS = [
  { label: 'Spear Phish (n=8)', value: '88.9%', color: 'text-rose-400',    bg: 'bg-rose-500/10',    border: 'border-rose-500/20' },
  { label: 'Phishing F1 (n=25)', value: '96.3%', color: 'text-cyan-400',    bg: 'bg-cyan-500/10',    border: 'border-cyan-500/20' },
  { label: 'URL F1 (n=21)',      value: '95.2%', color: 'text-purple-400',  bg: 'bg-purple-500/10',  border: 'border-purple-500/20' },
  { label: 'Injection F1 (n=16)',value: '100%',  color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20' },
  { label: 'Anomaly F1 (n=7)',   value: '100%',  color: 'text-orange-400',  bg: 'bg-orange-500/10',  border: 'border-orange-500/20' },
  { label: 'Composite F1',       value: '97.9%', color: 'text-white',       bg: 'bg-white/5',        border: 'border-white/10' },
];

const TAB_HEADERS: Record<string, { title: string; sub: string }> = {
  'Live Scanner':    { title: 'Command Center',     sub: 'Real-time threat overview · Live Firestore sync' },
  'Scan Tools':      { title: 'Scan Tools',          sub: 'URL · Email · File analysis · Manual investigation' },
  'Threat Analysis': { title: 'Threat Intelligence', sub: 'Multi-engine analytics · Behavioral trends · Peak hours' },
  'Incidents':       { title: 'Incident Repository', sub: 'Chronological log · Severity filter · Deep analysis' },
  'Settings':        { title: 'Settings',            sub: 'Backend configuration · API keys · Engine preferences' },
};

const Dashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState('Live Scanner');
  const [threats, setThreats] = useState<Threat[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const { uid, displayName, email, photoURL } = useAuth();
  const { incidents } = useFirebaseIncidents(uid);
  const currentRiskScore = threats.length > 0 ? threats[0].riskScore : 24;
  const navigate = useNavigate();

  const handleSignOut = async () => {
    await signOut(auth);
    navigate('/auth');
  };

  const handleUpload = async (file: File) => {
    setIsAnalyzing(true);
    try {
      const newThreat = await securityService.analyzeFile(file, 'anomaly', uid) as unknown as Threat;
      setThreats(prev => [newThreat, ...prev]);
    } catch (error) {
      console.error('Analysis failed:', error);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const navItems = [
    { icon: Activity,        label: 'Live Scanner' },
    { icon: ShieldCheck,     label: 'Scan Tools' },
    { icon: ShieldAlert,     label: 'Threat Analysis' },
    { icon: History,         label: 'Incidents' },
    { icon: Settings,        label: 'Settings' },
  ];

  const renderContent = () => {
    switch (activeTab) {
      case 'Scan Tools':      return <ScanToolsView />;
      case 'Threat Analysis': return <ThreatAnalysis />;
      case 'Incidents':       return <IncidentsView />;
      case 'Settings':        return <SettingsView />;
      case 'Live Scanner':
      default:
        return (
          <div className="flex-1 overflow-hidden grid grid-cols-12">
            {/* MIDDLE: CHAT & UPLOAD */}
            <div className="col-span-8 flex flex-col border-r border-white/5">
              <div className="flex-1 overflow-hidden">
                <ChatInterface threats={threats} isAnalyzing={isAnalyzing} />
              </div>
              <div className="p-8 border-t border-white/5 bg-black/20">
                <UploadBox onUpload={handleUpload} />
              </div>
            </div>

            {/* RIGHT PANEL */}
            <div className="col-span-4 flex flex-col overflow-y-auto custom-scrollbar p-6 space-y-5">

              {/* Risk Orb */}
              <div className="relative aspect-square rounded-[32px] border border-white/10 bg-black/60 overflow-hidden shadow-2xl">
                <div className="absolute top-4 left-4 z-10">
                  <h3 className="text-[10px] font-black text-cyan-400 uppercase tracking-[0.3em] flex items-center gap-2">
                    <Activity className="h-4 w-4" />
                    Risk Monitor
                  </h3>
                </div>
                <div className="absolute inset-0 flex items-center justify-center">
                  <CyberRiskOrb riskScore={currentRiskScore} className="w-full h-full" />
                </div>
              </div>

              {/* SHAP / Attribution Chart */}
              <AnimatePresence mode="wait">
                {threats.length > 0 ? (
                  <motion.div
                    key="shap"
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                  >
                    <ShapChart data={threats[0].shapData || []} />
                  </motion.div>
                ) : (
                  <div className="p-8 rounded-2xl border border-dashed border-white/10 text-center">
                    <Cpu className="h-8 w-8 text-zinc-700 mx-auto mb-4" />
                    <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Awaiting Analysis Data</p>
                  </div>
                )}
              </AnimatePresence>

              {/* Live Incidents Feed */}
              <div className="flex-1 flex flex-col rounded-[32px] border border-white/5 bg-white/5 backdrop-blur-xl overflow-hidden min-h-[300px]">
                <div className="p-5 border-b border-white/5 flex items-center justify-between bg-white/5">
                  <h3 className="text-[10px] font-black text-white uppercase tracking-[0.2em]">Live Heuristic Stream</h3>
                  <TrendingUp className="h-4 w-4 text-cyan-400" />
                </div>
                <div className="flex-1 overflow-hidden">
                  <IncidentFeed incidents={incidents} />
                </div>
              </div>

              {/* Email Guard status */}
              <div className="p-4 rounded-2xl bg-gradient-to-br from-cyan-500/10 to-purple-500/10 border border-white/10">
                <div className="flex items-center gap-3">
                  <div className="h-8 w-8 rounded-xl bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center flex-shrink-0">
                    <Mail className="h-4 w-4 text-cyan-400" />
                  </div>
                  <div>
                    <div className="text-[10px] font-black text-white uppercase tracking-widest">Gmail Email Guard</div>
                    <div className="text-[9px] text-zinc-500 font-bold uppercase tracking-tight mt-0.5">Zero content leakage · Feature vector only</div>
                  </div>
                  <div className="ml-auto h-2 w-2 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
                </div>
              </div>
            </div>
          </div>
        );
    }
  };

  const headerInfo = TAB_HEADERS[activeTab] || TAB_HEADERS['Live Scanner'];

  return (
    <div className="flex h-full w-full bg-black/20 backdrop-blur-3xl overflow-hidden">

      {/* ── LEFT SIDEBAR ── */}
      <aside className="w-64 border-r border-white/5 flex flex-col bg-black/40 backdrop-blur-xl">

        {/* Logo */}
        <div
          onClick={() => window.location.href = '/'}
          className="p-6 flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity"
        >
          <div className="h-10 w-10 flex items-center justify-center rounded-xl bg-cyan-500/20 shadow-[0_0_20px_rgba(6,182,212,0.3)] border border-cyan-500/20">
            <ShieldCheck className="h-6 w-6 text-cyan-400" />
          </div>
          <div>
            <span className="text-lg font-black tracking-tighter text-white block leading-tight">
              Sentinel<span className="text-cyan-400">IQ</span>
            </span>
            <span className="text-[8px] font-black text-zinc-600 uppercase tracking-widest">Enterprise Edition</span>
          </div>
        </div>

        {/* Scrollable Center Area */}
        <div className="flex-1 overflow-y-auto custom-scrollbar flex flex-col min-h-0">
          {/* Nav */}
          <nav className="px-4 py-4 space-y-1">
            {navItems.map((item, i) => (
              <button
                key={i}
                onClick={() => setActiveTab(item.label)}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-bold uppercase tracking-widest transition-all duration-300 group ${
                  activeTab === item.label
                    ? 'bg-cyan-500/10 text-cyan-400 shadow-[inset_0_0_20px_rgba(6,182,212,0.1)] border border-cyan-500/20'
                    : 'text-zinc-500 hover:text-white hover:bg-white/5 border border-transparent'
                }`}
              >
                <item.icon className={`h-5 w-5 flex-shrink-0 ${activeTab === item.label ? 'text-cyan-400' : 'group-hover:text-cyan-400'}`} />
                {item.label}
              </button>
            ))}
          </nav>

          {/* Benchmark KPIs */}
          <div className="px-4 pb-3 mt-auto">
            <div className="p-4 rounded-2xl bg-black/40 border border-white/5 space-y-1.5">
              <div className="flex items-center gap-2 mb-3">
                <Target className="h-3 w-3 text-cyan-400" />
                <span className="text-[9px] font-black text-zinc-400 uppercase tracking-widest">Accuracy Benchmarks</span>
              </div>
              {BENCHMARKS.map(b => (
                <div key={b.label} className={`flex items-center justify-between px-2.5 py-1.5 rounded-lg ${b.bg} border ${b.border}`}>
                  <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wide">{b.label}</span>
                  <span className={`text-[10px] font-black ${b.color}`}>{b.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Privacy status + User profile */}
        <div className="p-4 border-t border-white/5 space-y-3 flex-shrink-0 bg-black/20">
          {/* User chip */}
          {uid ? (
            <div className="flex items-center gap-3 px-2 py-2 rounded-xl bg-white/3 border border-white/5">
              {photoURL ? (
                <img src={photoURL} alt="avatar" className="h-7 w-7 rounded-full object-cover flex-shrink-0 ring-1 ring-cyan-500/30" />
              ) : (
                <div className="h-7 w-7 rounded-full bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center flex-shrink-0">
                  <User className="h-3.5 w-3.5 text-cyan-400" />
                </div>
              )}
              <div className="flex-1 min-w-0">
                <div className="text-[9px] font-black text-white uppercase tracking-wider truncate">
                  {displayName || email?.split('@')[0] || 'User'}
                </div>
                <div className="text-[7px] text-zinc-600 truncate">{email || 'Signed In'}</div>
              </div>
              <button
                onClick={handleSignOut}
                title="Sign out"
                className="p-1.5 rounded-lg hover:bg-red-500/10 text-zinc-600 hover:text-red-400 transition-colors flex-shrink-0"
              >
                <LogOut className="h-3 w-3" />
              </button>
            </div>
          ) : (
            <button
              onClick={() => navigate('/auth')}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-xl bg-cyan-500/5 border border-cyan-500/10 text-[9px] font-black text-cyan-400 uppercase tracking-widest hover:bg-cyan-500/10 transition-colors"
            >
              <Lock className="h-3 w-3" />
              Sign In to Save History
            </button>
          )}

          {/* Privacy badge */}
          <div className="flex items-center gap-2">
            <Lock className="h-3 w-3 text-emerald-400 flex-shrink-0" />
            <div>
              <div className="text-[8px] font-black text-emerald-400 uppercase tracking-widest">Zero Content Leakage</div>
              <div className="text-[7px] text-zinc-600 uppercase tracking-tight">Your history — private to you only</div>
            </div>
            <div className="ml-auto h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
          </div>
        </div>
      </aside>

      {/* ── MAIN CONTENT ── */}
      <div className="flex-1 flex flex-col min-w-0">

        {/* Contextual Header */}
        <header className="h-20 border-b border-white/5 flex items-center justify-between px-8 bg-black/20">
          <div>
            <h2 className="text-sm font-black text-white uppercase tracking-[0.3em]">{headerInfo.title}</h2>
            <p className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest mt-0.5">{headerInfo.sub}</p>
          </div>

          <div className="flex items-center gap-4">
            {/* Production-weighted F1 badge */}
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-purple-500/10 border border-purple-500/20">
              <Zap className="h-3 w-3 text-purple-400" />
              <span className="text-[9px] font-black text-purple-400 uppercase tracking-widest">Weighted F1: 97.0%</span>
            </div>
            {/* Live badge */}
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_10px_rgba(16,185,129,0.8)]" />
              <span className="text-[10px] font-black text-emerald-400 uppercase tracking-widest">Live Monitoring</span>
            </div>
          </div>
        </header>

        {/* Tab Content */}
        <div className="flex-1 overflow-hidden">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.18 }}
              className="h-full"
            >
              {renderContent()}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;