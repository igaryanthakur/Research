import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Settings, Shield, User, Trash2, LogOut, CheckCircle2, AlertTriangle, ShieldOff } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { signOut } from 'firebase/auth';
import { auth } from '@/lib/firebase';
import { useNavigate } from 'react-router-dom';

const SettingsView: React.FC = () => {
  const [consentEnabled, setConsentEnabled] = useState(true);
  const { uid, displayName, email, photoURL } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="p-8 space-y-8 h-full overflow-y-auto custom-scrollbar max-w-4xl">
      <div>
        <h2 className="text-2xl font-black text-white uppercase tracking-tighter">System Settings</h2>
        <p className="text-zinc-500 text-sm font-bold uppercase tracking-widest mt-1">Manage your account preferences and security protocols</p>
      </div>

      <div className="space-y-6">
        {/* Profile Section */}
        <section className="p-8 rounded-[32px] border border-white/10 bg-white/5 backdrop-blur-xl">
          <div className="flex items-center gap-6 mb-8">
            {photoURL ? (
              <img src={photoURL} alt="Avatar" className="h-20 w-20 rounded-3xl object-cover ring-2 ring-cyan-500/50" />
            ) : (
              <div className="h-20 w-20 rounded-3xl bg-gradient-to-br from-cyan-500 to-purple-500 p-[1px]">
                <div className="h-full w-full rounded-[23px] bg-zinc-900 flex items-center justify-center">
                  <User className="h-10 w-10 text-zinc-500" />
                </div>
              </div>
            )}
            <div>
              <h3 className="text-xl font-black text-white uppercase tracking-tight">{displayName || email?.split('@')[0] || 'User'}</h3>
              <p className="text-cyan-400 text-xs font-black uppercase tracking-widest">{uid ? 'Authenticated User' : 'Guest Mode'}</p>
            </div>
          </div>
          
          <div className="grid grid-cols-2 gap-4">
            <div className="p-4 rounded-2xl bg-white/5 border border-white/5">
              <label className="text-[10px] font-black text-zinc-500 uppercase tracking-widest block mb-2">Display Name</label>
              <input type="text" value={displayName || 'Not Set'} readOnly className="w-full bg-transparent text-sm font-bold text-white focus:outline-none" />
            </div>
            <div className="p-4 rounded-2xl bg-white/5 border border-white/5">
              <label className="text-[10px] font-black text-zinc-500 uppercase tracking-widest block mb-2">Email Address</label>
              <input type="email" value={email || 'Not Available'} readOnly className="w-full bg-transparent text-sm font-bold text-white focus:outline-none" />
            </div>
          </div>
        </section>

        {/* Consent Section */}
        <section className="p-8 rounded-[32px] border border-white/10 bg-white/5 backdrop-blur-xl">
          <div className="flex items-start justify-between">
            <div className="flex gap-4">
              <div className="h-10 w-10 rounded-xl bg-cyan-500/10 flex items-center justify-center border border-cyan-500/20">
                <Shield className="h-5 w-5 text-cyan-400" />
              </div>
              <div>
                <h3 className="text-lg font-black text-white uppercase tracking-tight">Remove Consent</h3>
                <p className="text-zinc-500 text-xs font-bold uppercase tracking-widest mt-1">Revoke AI permissions to analyze and process security logs</p>
              </div>
            </div>
            
            <button 
              onClick={() => setConsentEnabled(!consentEnabled)}
              className={`relative h-6 w-12 rounded-full transition-colors duration-300 ${consentEnabled ? 'bg-cyan-500' : 'bg-zinc-800'}`}
            >
              <motion.div 
                animate={{ x: consentEnabled ? 24 : 4 }}
                className="absolute top-1 h-4 w-4 rounded-full bg-white shadow-lg"
              />
            </button>
          </div>
          
          <div className="mt-6 p-4 rounded-2xl border border-dashed border-white/10">
            <div className="flex items-center gap-3 mb-2">
              <CheckCircle2 className={`h-4 w-4 ${consentEnabled ? 'text-emerald-400' : 'text-zinc-700'}`} />
              <span className={`text-[10px] font-black uppercase tracking-widest ${consentEnabled ? 'text-zinc-300' : 'text-zinc-600'}`}>
                Active Monitoring Enabled
              </span>
            </div>
            <p className="text-[10px] text-zinc-500 font-bold uppercase leading-relaxed">
              By disabling this, you revoke the automated system's ability to scan for vulnerabilities and anomalous patterns. You can re-enable this at any time.
            </p>
          </div>
          
          {!consentEnabled && (
            <motion.div 
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              className="mt-6 p-4 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center gap-4"
            >
              <ShieldOff className="h-5 w-5 text-red-400" />
              <p className="text-xs font-black text-red-400 uppercase tracking-widest">
                WARNING: Disabling consent will pause all active threat detection and real-time analysis.
              </p>
            </motion.div>
          )}
        </section>

        {/* Danger Zone */}
        <section className="p-8 rounded-[32px] border border-red-500/20 bg-red-500/5 backdrop-blur-xl">
          <div className="flex items-center gap-4 mb-6">
            <AlertTriangle className="h-6 w-6 text-red-500" />
            <h3 className="text-lg font-black text-red-500 uppercase tracking-tight">Danger Zone</h3>
          </div>
          
          <div className="flex flex-col gap-4">
            <button 
              onClick={() => {
                if (window.confirm("Are you sure you want to delete your account? This action is irreversible.")) {
                  alert("Account deletion initiated.");
                }
              }}
              className="w-full flex items-center justify-between p-6 rounded-2xl border border-red-500/20 bg-red-500/10 hover:bg-red-500/20 transition-all group"
            >
              <div className="text-left">
                <div className="text-sm font-black text-white uppercase tracking-widest mb-1 group-hover:text-red-400 transition-colors">Delete System Account</div>
                <p className="text-[10px] text-red-500/60 font-black uppercase tracking-widest">Permanently erase all data and security logs</p>
              </div>
              <Trash2 className="h-6 w-6 text-red-500" />
            </button>

            <button 
              onClick={async () => {
                await signOut(auth);
                navigate('/auth');
              }}
              className="w-full flex items-center justify-between p-6 rounded-2xl border border-white/5 bg-white/5 hover:bg-white/10 transition-all group"
            >
              <div className="text-left">
                <div className="text-sm font-black text-white uppercase tracking-widest mb-1">Sign Out of Session</div>
                <p className="text-[10px] text-zinc-500 font-black uppercase tracking-widest">Securely terminate the current session</p>
              </div>
              <LogOut className="h-6 w-6 text-zinc-500" />
            </button>
          </div>
        </section>
      </div>
    </div>
  );
};

export default SettingsView;
