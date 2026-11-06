import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { 
  ShieldCheck, 
  ArrowRight, 
  Mail, 
  Lock, 
  Github, 
  Eye, 
  EyeOff,
  AlertCircle,
  Loader2
} from 'lucide-react';
import { 
  signInWithEmailAndPassword, 
  createUserWithEmailAndPassword, 
  signInWithPopup 
} from 'firebase/auth';
import { auth, googleProvider } from '../lib/firebase';

const Auth = () => {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const navigate = useNavigate();

  const handleEmailAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Email and password are required');
      return;
    }
    
    setError(null);
    setLoading(true);
    
    try {
      if (isLogin) {
        await signInWithEmailAndPassword(auth, email, password);
      } else {
        await createUserWithEmailAndPassword(auth, email, password);
      }
      navigate('/dashboard');
    } catch (err: any) {
      console.error('Auth error:', err);
      // Clean up Firebase error messages for the UI
      const msg = err.message || 'Authentication failed';
      if (msg.includes('user-not-found') || msg.includes('wrong-password') || msg.includes('invalid-credential')) {
        setError('Invalid email or password');
      } else if (msg.includes('email-already-in-use')) {
        setError('An account with this email already exists');
      } else if (msg.includes('weak-password')) {
        setError('Password should be at least 6 characters');
      } else {
        setError(msg.replace('Firebase:', '').trim());
      }
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleAuth = async () => {
    setError(null);
    setLoading(true);
    try {
      await signInWithPopup(auth, googleProvider);
      navigate('/dashboard');
    } catch (err: any) {
      console.error('Google Auth error:', err);
      // user-closed-popup is common and not really an error to show the user aggressively, 
      // but we'll show it if they need feedback
      if (err.code !== 'auth/popup-closed-by-user' && err.code !== 'auth/cancelled-popup-request') {
         setError(err.message?.replace('Firebase:', '').trim() || 'Google sign-in failed');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#020813] flex flex-col justify-center relative overflow-hidden font-sans selection:bg-cyan-500/30">
      
      {/* Background grids and glows */}
      <div className="absolute inset-0 z-0">
        <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.03)_1px,transparent_1px)] bg-[size:40px_40px] [mask-image:radial-gradient(ellipse_60%_60%_at_50%_50%,#000_10%,transparent_100%)]" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-cyan-500/10 rounded-full blur-[120px] opacity-50" />
      </div>

      <div className="relative z-10 w-full max-w-[440px] mx-auto px-6">
        
        {/* Logo Header */}
        <motion.div 
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col items-center mb-10"
        >
          <div className="flex items-center gap-2 mb-6 cursor-pointer" onClick={() => navigate('/')}>
            <ShieldCheck className="h-8 w-8 text-cyan-400" />
            <span className="text-2xl font-black text-white tracking-tight">
              Sentinel<span className="text-cyan-400">IQ</span>
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white mb-2">
            {isLogin ? 'Access Command Center' : 'Initialize Defense Grid'}
          </h1>
          <p className="text-sm text-zinc-400 text-center">
            {isLogin 
              ? 'Enter your credentials to access the intelligence platform.' 
              : 'Create an administrator account to begin monitoring.'}
          </p>
        </motion.div>

        {/* Main Auth Card */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="backdrop-blur-xl bg-black/40 border border-white/10 rounded-3xl p-8 shadow-[0_0_50px_rgba(0,0,0,0.5)] relative overflow-hidden"
        >
          {/* Top border glowing highlight */}
          <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent" />

          {/* Toggle Login/Register */}
          <div className="flex p-1 bg-white/5 rounded-xl mb-8">
            <button
              onClick={() => { setIsLogin(true); setError(null); }}
              className={`flex-1 py-2.5 text-sm font-bold rounded-lg transition-all ${
                isLogin ? 'bg-white/10 text-white shadow-sm' : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => { setIsLogin(false); setError(null); }}
              className={`flex-1 py-2.5 text-sm font-bold rounded-lg transition-all ${
                !isLogin ? 'bg-white/10 text-white shadow-sm' : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              Register
            </button>
          </div>

          <form onSubmit={handleEmailAuth} className="space-y-5">
            
            {/* Error Message */}
            <AnimatePresence>
              {error && (
                <motion.div 
                  initial={{ opacity: 0, height: 0, marginBottom: 0 }}
                  animate={{ opacity: 1, height: 'auto', marginBottom: 20 }}
                  exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                  className="bg-red-500/10 border border-red-500/20 rounded-xl p-3 flex items-start gap-3 items-center overflow-hidden"
                >
                  <AlertCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
                  <span className="text-xs text-red-200 leading-snug">{error}</span>
                </motion.div>
              )}
            </AnimatePresence>

            <div>
              <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider mb-2">
                Operational Email
              </label>
              <div className="relative">
                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@sentineliq.io"
                  className="w-full bg-black/50 border border-white/10 rounded-xl py-3 pl-11 pr-4 text-sm text-white focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/50 transition-all placeholder:text-zinc-700"
                  required
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider">
                  Access Key
                </label>
                {isLogin && (
                  <a href="#" className="text-[10px] font-bold text-cyan-400 hover:text-cyan-300 transition-colors">
                    Forged password?
                  </a>
                )}
              </div>
              <div className="relative">
                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full bg-black/50 border border-white/10 rounded-xl py-3 pl-11 pr-11 text-sm text-white focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/50 transition-all placeholder:text-zinc-700 font-mono tracking-widest"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full relative group overflow-hidden rounded-xl p-px mt-6"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-cyan-500 via-purple-500 to-cyan-500 bg-[length:200%_auto] animate-gradient-fast" />
              <div className="relative bg-black rounded-[11px] px-4 py-3 transition-colors group-hover:bg-transparent">
                <div className="flex items-center justify-center gap-2">
                  {loading ? (
                    <Loader2 className="h-4 w-4 text-white animate-spin" />
                  ) : (
                    <>
                      <span className="text-sm font-bold text-white uppercase tracking-wider">
                        {isLogin ? 'Authenticate' : 'Initialize'}
                      </span>
                      <ArrowRight className="h-4 w-4 text-white transition-transform group-hover:translate-x-1" />
                    </>
                  )}
                </div>
              </div>
            </button>
          </form>

          <div className="mt-8 relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-white/10" />
            </div>
            <div className="relative flex justify-center text-[10px] uppercase font-bold tracking-widest">
              <span className="bg-[#0b101b] px-3 text-zinc-500">Or authenticate via</span>
            </div>
          </div>

          <div className="mt-6 flex gap-3">
            <button
              onClick={handleGoogleAuth}
              disabled={loading}
              className="flex-1 flex items-center justify-center gap-2 py-3 px-4 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 transition-colors text-sm font-bold text-white"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
              </svg>
              Google
            </button>
            <button
              disabled={true}
              className="flex-1 flex items-center justify-center gap-2 py-3 px-4 rounded-xl border border-white/10 bg-white/5 text-sm font-bold text-zinc-500 cursor-not-allowed"
            >
              <Github className="w-4 h-4" />
              Github
            </button>
          </div>

        </motion.div>
        
        {/* Footer */}
        <p className="mt-8 text-center text-[10px] text-zinc-600 font-mono">
          SECURE CONNECTION ESTABLISHED • ENCRYPTED VIA ECDHE-RSA-AES256-GCM-SHA384
        </p>
      </div>
    </div>
  );
};

export default Auth;
