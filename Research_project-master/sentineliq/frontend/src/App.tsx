import React, { useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Navbar, Footer } from './components/Navigation';
import Background from './components/Background';
import Dashboard from './pages/Dashboard';
import Hero from './pages/Hero';
import ScanTools from './pages/ScanTools';
import ThreatAnalysis from './components/dashboard/ThreatAnalysis';
import Auth from './pages/Auth';

// Placeholder components for routes
const Incidents = () => (
  <div className="flex-1 flex items-center justify-center text-zinc-500 font-bold uppercase tracking-[0.3em]">
    Incident Repository // Coming Soon
  </div>
);

const Settings = () => (
  <div className="flex-1 flex items-center justify-center text-zinc-500 font-bold uppercase tracking-[0.3em]">
    System Configuration // Coming Soon
  </div>
);

const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div className="relative flex h-screen w-full flex-col overflow-hidden text-white font-sans selection:bg-cyan-500/30">
      <Background />
      
      {/* Top Navigation Bar */}
      <Navbar />

      {/* Main Content Area */}
      <main className="relative flex flex-1 flex-col overflow-hidden min-h-0">
        {children}
      </main>

      {/* Status Footer */}
      <Footer />
    </div>
  );
};

const App: React.FC = () => {
  const [toast, setToast] = useState<{message: string, type: string} | null>(null);

  useEffect(() => {
    const handleToast = (e: Event) => {
      const customEvent = e as CustomEvent;
      setToast(customEvent.detail);
      setTimeout(() => setToast(null), 5000);
    };
    window.addEventListener('security-toast', handleToast);
    return () => window.removeEventListener('security-toast', handleToast);
  }, []);

  return (
    <Router>
      {toast && (
        <div className="fixed bottom-4 right-4 z-50 px-4 py-3 rounded bg-zinc-900/95 text-red-400 border border-red-500/30 shadow-2xl backdrop-blur flex items-center gap-3 animate-in fade-in slide-in-from-bottom-5">
          <div className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
          <span className="text-sm font-medium tracking-wide">{toast.message}</span>
          <button onClick={() => setToast(null)} className="ml-2 opacity-60 hover:opacity-100">&times;</button>
        </div>
      )}
      <Routes>
        <Route path="/auth" element={<Auth />} />
        
        {/* All other routes get the Layout with Navbar */}
        <Route path="*" element={
          <Layout>
            <Routes>
              <Route path="/" element={<Hero />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/scan-tools" element={<ScanTools />} />
              <Route path="/analysis" element={<ThreatAnalysis />} />
              <Route path="/incidents" element={<Incidents />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Layout>
        } />
      </Routes>
    </Router>
  );
};

export default App;