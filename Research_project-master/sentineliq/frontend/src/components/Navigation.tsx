import React from 'react';
import { NavLink } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  LayoutDashboard, 
  ShieldAlert, 
  ShieldCheck,
  Search
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const navItems = [
  { icon: LayoutDashboard, label: 'Dashboard', path: '/dashboard' },
  { icon: ShieldAlert, label: 'Scan Tools', path: '/scan-tools' },
  { icon: ShieldAlert, label: 'Threats', path: '/analysis' },
];

export const Navbar: React.FC = () => {
  return (
    <nav className="sticky top-0 z-50 w-full border-b border-white/10 bg-black/40 backdrop-blur-2xl">
      <div className="mx-auto flex h-16 max-w-[1600px] items-center justify-between px-6">
        {/* Logo */}
        <NavLink to="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-cyan-500/20 shadow-[0_0_15px_rgba(6,182,212,0.4)]">
            <ShieldCheck className="h-5 w-5 text-cyan-400" />
          </div>
          <span className="text-xl font-bold tracking-tighter text-white">
            Sentinel<span className="text-cyan-400">IQ</span>
          </span>
        </NavLink>

        {/* Navigation Items */}
        <div className="hidden items-center gap-1 md:flex">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) => cn(
                "group relative flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all duration-300",
                isActive 
                  ? "text-cyan-400" 
                  : "text-zinc-400 hover:bg-white/5 hover:text-white"
              )}
            >
              {({ isActive }) => (
                <>
                  <item.icon className={cn(
                    "h-4 w-4 transition-colors",
                    isActive ? "text-cyan-400" : "group-hover:text-cyan-400"
                  )} />
                  {item.label}
                  {isActive && (
                    <motion.div
                      layoutId="active-nav-bg"
                      className="absolute inset-0 z-[-1] rounded-lg bg-cyan-500/10 shadow-[inset_0_0_20px_rgba(6,182,212,0.1)] border border-cyan-500/20"
                    />
                  )}
                </>
              )}
            </NavLink>
          ))}
        </div>

        {/* Right Side Actions */}
        <div className="flex items-center gap-4">
          <div className="hidden h-9 w-9 items-center justify-center rounded-full border border-white/5 bg-white/5 md:flex">
            <ShieldCheck className="h-4 w-4 text-cyan-400" />
          </div>
        </div>
      </div>
    </nav>
  );
};

export const Footer: React.FC = () => {
  return (
    <footer className="mt-auto w-full border-t border-white/5 bg-black/20 p-6 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1600px] items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 animate-pulse rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.8)]" />
            <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">System Secure</span>
          </div>
          <span className="text-[10px] text-zinc-600">// NODE: ALPHA-1 // SHIELD-V4.2</span>
        </div>
        
        <div className="flex gap-6">
          <span className="text-[10px] font-bold text-zinc-500 hover:text-cyan-400 transition-colors cursor-pointer uppercase tracking-widest">Privacy</span>
          <span className="text-[10px] font-bold text-zinc-500 hover:text-cyan-400 transition-colors cursor-pointer uppercase tracking-widest">Terms</span>
          <span className="text-[10px] font-bold text-zinc-500 hover:text-cyan-400 transition-colors cursor-pointer uppercase tracking-widest">Documentation</span>
        </div>
      </div>
    </footer>
  );
};