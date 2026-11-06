import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Upload, 
  FileText, 
  AlertTriangle, 
  CheckCircle2, 
  ArrowRight, 
  Info,
  ShieldAlert,
  Terminal,
  Cpu
} from 'lucide-react';
import { useDropzone } from 'react-dropzone';
import { Threat, ShapData } from '@/types/security';
import { securityService } from '@/services/securityService';

const TypewriterText: React.FC<{ text: string }> = ({ text }) => {
  const [displayedText, setDisplayedText] = useState('');
  
  useEffect(() => {
    let i = 0;
    const interval = setInterval(() => {
      setDisplayedText(text.slice(0, i));
      i++;
      if (i > text.length) clearInterval(interval);
    }, 20);
    return () => clearInterval(interval);
  }, [text]);

  return <span>{displayedText}</span>;
};

// --- SHAP Chart Component ---
export const ShapChart: React.FC<{ data: ShapData[] }> = ({ data }) => {
  return (
    <div className="space-y-4 p-4 rounded-2xl border border-white/5 bg-white/5 backdrop-blur-md">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
          <Cpu className="h-4 w-4 text-cyan-400" />
          Feature Importance (SHAP)
        </h3>
        <span className="text-[10px] text-zinc-500">Log Analysis Mode</span>
      </div>
      <div className="space-y-3">
        {data?.map((item, index) => (
          <div key={index} className="space-y-1">
            <div className="flex justify-between text-[10px] text-zinc-400">
              <span>{item.feature}</span>
              <span className="font-mono">{item.value}%</span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-white/5 overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${item.value}%` }}
                transition={{ duration: 1, delay: index * 0.1, ease: "easeOut" }}
                className="h-full bg-gradient-to-r from-cyan-500 to-purple-500 shadow-[0_0_10px_rgba(6,182,212,0.5)]"
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// --- Threat Result Card Component ---
export const ThreatCard: React.FC<{ threat: Threat }> = ({ threat }) => {
  const getRiskColor = (level: string) => {
    switch (level) {
      case 'Critical': return 'border-red-500 shadow-[0_0_20px_rgba(239,68,68,0.3)]';
      case 'High': return 'border-orange-500 shadow-[0_0_20px_rgba(249,115,22,0.3)]';
      case 'Medium': return 'border-yellow-500 shadow-[0_0_20px_rgba(234,179,8,0.3)]';
      default: return 'border-green-500 shadow-[0_0_20px_rgba(34,197,94,0.3)]';
    }
  };

  const getRiskTextColor = (level: string) => {
    switch (level) {
      case 'Critical': return 'text-red-400';
      case 'High': return 'text-orange-400';
      case 'Medium': return 'text-yellow-400';
      default: return 'text-green-400';
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: -20, scale: 0.95 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      className={`relative mb-6 max-w-2xl rounded-2xl border-l-4 bg-black/40 p-6 backdrop-blur-xl ${getRiskColor(threat.riskLevel)}`}
      whileHover={{ scale: 1.02 }}
    >
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`rounded-lg bg-black/50 px-3 py-1 text-[10px] font-bold uppercase tracking-widest ${getRiskTextColor(threat.riskLevel)}`}>
            {threat.type}
          </div>
          <span className="text-[10px] text-zinc-500 tabular-nums">{new Date(threat.timestamp).toLocaleTimeString()}</span>
        </div>
        <div className="text-right">
          <div className={`text-2xl font-black ${getRiskTextColor(threat.riskLevel)}`}>
            {threat.riskScore}
          </div>
          <div className="text-[10px] font-bold text-zinc-500 uppercase">Risk Score</div>
        </div>
      </div>

      <div className="mb-4">
        <h4 className="text-xs font-bold text-zinc-400 uppercase tracking-widest mb-2 flex items-center gap-2">
          <Terminal className="h-4 w-4 text-cyan-400" />
          AI Explanation
        </h4>
        <div className="text-sm leading-relaxed text-zinc-300">
          <TypewriterText text={threat.explanation} />
        </div>
      </div>

      <div className="mb-6 flex flex-wrap gap-2">
        {threat?.shapTokens?.map((token, i) => (
          <span 
            key={i} 
            className="rounded-full bg-red-500/10 px-3 py-1 text-[10px] font-medium text-red-400 border border-red-500/20 shadow-[0_0_10px_rgba(239,68,68,0.1)]"
          >
            {token.token}
          </span>
        ))}
      </div>

      <div className="rounded-xl bg-cyan-500/5 p-4 border border-cyan-500/10">
        <div className="flex items-center gap-2 text-xs font-bold text-cyan-400 uppercase tracking-widest mb-2">
          <ShieldAlert className="h-4 w-4" />
          Recommended Action
        </div>
        <p className="text-sm text-zinc-400">{threat.recommendedAction}</p>
        <motion.button
          whileHover={{ x: 5 }}
          className="mt-3 flex items-center gap-2 text-xs font-bold text-white transition-colors hover:text-cyan-400"
        >
          Execute Mitigation <ArrowRight className="h-4 w-4" />
        </motion.button>
      </div>
    </motion.div>
  );
};

// --- Upload Box Component ---
export const UploadBox: React.FC<{ onUpload: (file: File) => void }> = ({ onUpload }) => {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (acceptedFiles) => acceptedFiles[0] && onUpload(acceptedFiles[0]),
    multiple: false
  });

  return (
    <div 
      {...getRootProps()} 
      className={`group relative mt-auto rounded-3xl border-2 border-dashed p-8 transition-all duration-300 ${
        isDragActive ? 'border-cyan-500 bg-cyan-500/10' : 'border-white/10 bg-white/5'
      }`}
    >
      <input {...getInputProps()} />
      <div className="flex flex-col items-center justify-center gap-4 text-center">
        <motion.div 
          animate={isDragActive ? { scale: 1.2, rotate: 180 } : {}}
          className={`flex h-16 w-16 items-center justify-center rounded-2xl bg-white/5 shadow-inner ${
            isDragActive ? 'text-cyan-400' : 'text-zinc-500'
          }`}
        >
          <Upload className="h-8 w-8" />
        </motion.div>
        <div>
          <h3 className="text-lg font-bold text-white">Ingest Security Logs</h3>
          <p className="text-sm text-zinc-400">Drag & drop files to analyze threat vectors</p>
        </div>
        <div className="flex gap-4">
          {['.eml', '.json', '.csv', '.txt', '.pdf'].map(ext => (
            <span key={ext} className="text-[10px] font-bold text-zinc-600 uppercase tracking-tighter">
              {ext}
            </span>
          ))}
        </div>
      </div>
      {isDragActive && (
        <div className="absolute inset-0 rounded-3xl bg-cyan-500/5 blur-xl pointer-events-none" />
      )}
    </div>
  );
};

// --- Main Chat Interface ---
export const ChatInterface: React.FC<{ threats: Threat[], isAnalyzing: boolean }> = ({ threats, isAnalyzing }) => {
  return (
    <div className="flex h-full flex-col p-8 overflow-y-auto custom-scrollbar">
      {threats.length === 0 && !isAnalyzing && (
        <div className="flex flex-1 flex-col items-center justify-center text-center">
          <div className="relative mb-8">
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
              className="absolute -inset-8 opacity-20"
            >
              <svg viewBox="0 0 100 100" className="h-48 w-48 text-cyan-500">
                <circle cx="50" cy="50" r="48" fill="none" stroke="currentColor" strokeWidth="0.5" strokeDasharray="4 4" />
              </svg>
            </motion.div>
            <div className="h-20 w-20 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center relative overflow-hidden">
              <div className="absolute inset-0 bg-[linear-gradient(transparent_0%,rgba(6,182,212,0.1)_50%,transparent_100%)] animate-scanline bg-[length:100%_4px]" />
              <Terminal className="h-10 w-10 text-cyan-400" />
            </div>
          </div>
          <h2 className="text-2xl font-black text-white uppercase tracking-tighter mb-2">Awaiting Telemetry</h2>
          <p className="max-w-sm text-zinc-500 text-xs font-bold uppercase tracking-widest leading-relaxed">
            Drag and drop security logs, EML files, or raw text below to initiate AI deep packet inspection.
          </p>
          
          <div className="mt-8 flex flex-col gap-2 max-w-sm w-full text-left bg-black/40 border border-white/5 p-4 rounded-xl font-mono text-[10px] text-zinc-600 uppercase tracking-widest">
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-1.5 rounded-full bg-cyan-500 animate-pulse" />
              <span className="text-cyan-400/80">Neural Engines Online</span>
            </div>
            <div>&gt; _ Ready for input...</div>
          </div>
        </div>
      )}

      <div className="flex-1 space-y-6">
        {threats?.map((threat) => (
          <ThreatCard key={threat.id} threat={threat} />
        ))}
        
        {isAnalyzing && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-4 p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-md max-w-md"
          >
            <div className="relative h-12 w-12 flex items-center justify-center">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                className="absolute inset-0 rounded-full border-2 border-cyan-500 border-t-transparent"
              />
              <ShieldAlert className="h-6 w-6 text-cyan-400" />
            </div>
            <div>
              <div className="text-sm font-bold text-white uppercase tracking-widest">Analyzing Patterns...</div>
              <div className="text-xs text-zinc-500">Cross-referencing global threat intelligence</div>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
};
