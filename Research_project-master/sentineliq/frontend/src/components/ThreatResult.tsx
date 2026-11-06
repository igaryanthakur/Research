import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ShieldAlert, Terminal, ChevronDown, ChevronUp } from 'lucide-react';

interface ShapToken {
  token: string;
  score: number;
}

interface ThreatResultProps {
  message?: string;
  onExpand?: () => void;
  data?: Record<string, unknown>;
  score?: number;
  verdict?: 'MALICIOUS' | 'SUSPICIOUS' | 'BENIGN';
  shapTokens?: ShapToken[];
}

export const ThreatResult: React.FC<ThreatResultProps> = ({ 
  message = "No threat analyzed.", 
  onExpand, 
  data = {}, 
  score = 0,
  verdict = 'BENIGN',
  shapTokens = []
}) => {
  const [internalExpand, setInternalExpand] = useState<boolean>(false);

  const handleExpand = (): void => {
    setInternalExpand(!internalExpand);
    if (onExpand) {
      onExpand();
    }
  };

  const getRiskColor = (v: string): string => {
    switch (v) {
      case 'MALICIOUS': return 'border-red-500 bg-red-500/10 text-red-500 shadow-[0_0_20px_rgba(239,68,68,0.3)]';
      case 'SUSPICIOUS': return 'border-yellow-500 bg-yellow-500/10 text-yellow-500 shadow-[0_0_20px_rgba(234,179,8,0.3)]';
      default: return 'border-green-500 bg-green-500/10 text-green-500 shadow-[0_0_20px_rgba(34,197,94,0.3)]';
    }
  };

  const renderWords = (): React.ReactNode => {
    if (shapTokens.length > 0) {
      return shapTokens.map((t: ShapToken, i: number) => {
        const isHighRisk = t.score > 0.5;
        return (
          <span 
            key={i} 
            className={`mr-1 px-1 rounded ${isHighRisk ? 'bg-red-500/30 text-red-200' : 'text-zinc-400'}`}
          >
            {t.token}
          </span>
        );
      });
    }

    return message.split(' ').map((word: string, i: number) => {
      // Just some subtle arbitrary styling to satisfy the h variables they had
      const h = Math.max(10, Math.random() * 20);
      return (
        <span key={i} className="mr-1 text-zinc-300 relative inline-block">
          {word}
        </span>
      );
    });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={`relative w-full rounded-2xl border-l-4 p-6 backdrop-blur-xl transition-all duration-300 ${getRiskColor(verdict).split(' ')[0]} bg-black/40`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ShieldAlert className={`h-6 w-6 ${getRiskColor(verdict).split(' ')[2]}`} />
          <div>
            <h3 className="text-sm font-bold uppercase tracking-widest text-white">Threat Verdict: {verdict}</h3>
            <p className="text-xs text-zinc-500">Confidence Score: {(score * 100).toFixed(1)}%</p>
          </div>
        </div>
        <button 
          onClick={handleExpand}
          className="rounded-full bg-white/5 p-2 transition-colors hover:bg-white/10"
        >
          {internalExpand ? <ChevronUp className="h-4 w-4 text-zinc-400" /> : <ChevronDown className="h-4 w-4 text-zinc-400" />}
        </button>
      </div>

      <AnimatePresence>
        {internalExpand && (
          <motion.div
            initial={{ height: 0, opacity: 0, marginTop: 0 }}
            animate={{ height: 'auto', opacity: 1, marginTop: 16 }}
            exit={{ height: 0, opacity: 0, marginTop: 0 }}
            className="overflow-hidden"
          >
            <div className="rounded-xl border border-white/5 bg-black/40 p-4">
              <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-zinc-400">
                <Terminal className="h-4 w-4 text-cyan-400" />
                Payload Analysis
              </div>
              <div className="text-sm font-mono leading-relaxed">
                {renderWords()}
              </div>

              {Object.keys(data).length > 0 && (
                <div className="mt-4 border-t border-white/10 pt-4">
                  <div className="mb-2 text-xs font-bold uppercase tracking-widest text-zinc-500">Metadata</div>
                  <pre className="text-[10px] text-zinc-400 overflow-x-auto p-2 bg-black/50 rounded">
                    {JSON.stringify(data, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default ThreatResult;
