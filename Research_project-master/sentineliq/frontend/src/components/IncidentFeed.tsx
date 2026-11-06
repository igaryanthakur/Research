import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Incident } from '@/types/security';

const IncidentItem: React.FC<{ incident: Incident }> = ({ incident }) => {
  const getRiskBadge = (level: string) => {
    switch (level) {
      case 'Critical': return 'bg-red-500/10 text-red-400 border-red-500/20';
      case 'High': return 'bg-orange-500/10 text-orange-400 border-orange-500/20';
      case 'Medium': return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20';
      default: return 'bg-green-500/10 text-green-400 border-green-500/20';
    }
  };

  return (
    <motion.div
      initial={{ x: 20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      className="group relative border-b border-white/5 p-4 transition-colors hover:bg-white/5"
    >
      <div className="flex items-center justify-between mb-1">
        <span className={`rounded px-1.5 py-0.5 text-[8px] font-black uppercase tracking-widest border ${getRiskBadge(incident.riskLevel)}`}>
          {incident.riskLevel}
        </span>
        <span className="text-[10px] tabular-nums text-zinc-600">
          {new Date(incident.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
      <div className="text-[11px] font-bold text-zinc-300 group-hover:text-cyan-400 transition-colors">
        {incident.type}
      </div>
      <div className="text-[9px] text-zinc-500 line-clamp-1 mt-0.5">
        {incident.description}
      </div>
      
      {/* Flash effect for new items */}
      <motion.div
        initial={{ opacity: 1 }}
        animate={{ opacity: 0 }}
        transition={{ duration: 1 }}
        className="absolute inset-0 bg-cyan-500/5 pointer-events-none"
      />
    </motion.div>
  );
};

export const IncidentFeed: React.FC<{ incidents: Incident[] }> = ({ incidents }) => {
  return (
    <div className="flex flex-col h-full bg-transparent">
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <AnimatePresence initial={false}>
          {incidents?.map((incident) => (
            <IncidentItem key={incident.id} incident={incident} />
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
};