import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  ShieldAlert, 
  Search, 
  Upload, 
  Zap, 
  Mail, 
  Link2, 
  Database, 
  ChevronRight,
  FileText,
  AlertTriangle,
  CheckCircle2,
  X,
  Loader2
} from 'lucide-react';
import { securityService } from '@/services/securityService';
import { useAuth } from '@/hooks/useAuth';
import { cn } from '@/lib/utils';

type InputType = 'unknown' | 'email' | 'url' | 'injection' | 'anomaly';
type Operation = 'phishing' | 'url-analysis' | 'injection' | 'anomaly';

const ScanTools: React.FC = () => {
  const [input, setInput] = useState('');
  const [inputType, setInputType] = useState<InputType>('unknown');
  const [operation, setOperation] = useState<Operation>('phishing');
  const [file, setFile] = useState<File | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [fileResult, setFileResult] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const anomalyFileInputRef = useRef<HTMLInputElement>(null);
  const { uid } = useAuth();  // uid=null if not signed in — scans still work

  // Real-time client-side validation
  useEffect(() => {
    const trimmedInput = input.trim();
    if (!trimmedInput) {
      if (operation !== 'anomaly') setInputType('unknown');
      return;
    }

    // Basic URL detection
    const urlRegex = /^(https?:\/\/)?([\da-z.-]+)\.([a-z.]{2,6})([\/\w .-]*)*\/?$/;
    if (urlRegex.test(trimmedInput)) {
      setInputType('url');
      setOperation('url-analysis');
      return;
    }

    // Basic Email/Phishing detection
    const emailKeywords = ['subject:', 'from:', 'to:', 'dear customer', 'verify your account', 'urgent action'];
    if (trimmedInput.includes('@') && (trimmedInput.includes('\n') || emailKeywords.some(k => trimmedInput.toLowerCase().includes(k)))) {
      setInputType('email');
      setOperation('phishing');
      return;
    }

    // Basic Injection detection
    const injectionKeywords = ['select * from', 'drop table', '<script>', 'union select', 'ignore previous instructions', 'system prompt:'];
    if (injectionKeywords.some(k => trimmedInput.toLowerCase().includes(k))) {
      setInputType('injection');
      setOperation('injection');
      return;
    }

    setInputType('unknown');
  }, [input, operation]);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>, type: 'normal' | 'anomaly') => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      if (type === 'anomaly') {
        setOperation('anomaly');
        setInputType('anomaly');
      }
    }
  };

  const handleAnalyze = async () => {
    setIsAnalyzing(true);
    setResult(null);
    if (operation === 'anomaly') setFileResult(null);

    try {
      let analysisResult;

      if (file) {
        analysisResult = await securityService.analyzeFile(file, operation, uid);
        
        if (operation === 'anomaly') {
          setFileResult(analysisResult);
        } else {
          setResult(analysisResult);
        }
      } else {
        analysisResult = await securityService.analyzeText(input, operation, inputType, uid);
        setResult(analysisResult);
      }
    } catch (error) {
      console.error('Analysis error:', error);
      setResult({ status: 'error', details: 'Analysis failed. Please try again later.' });
    } finally {
      setIsAnalyzing(false);
    }
  };

  const getInputTypeIcon = () => {
    switch (inputType) {
      case 'url': return <Link2 className="h-5 w-5 text-purple-400" />;
      case 'email': return <Mail className="h-5 w-5 text-cyan-400" />;
      case 'injection': return <Database className="h-5 w-5 text-emerald-400" />;
      case 'anomaly': return <ShieldAlert className="h-5 w-5 text-orange-400" />;
      default: return <Search className="h-5 w-5 text-zinc-500" />;
    }
  };

  const getInputTypeLabel = () => {
    switch (inputType) {
      case 'url': return 'URL Detected';
      case 'email': return 'Email Content Detected';
      case 'injection': return 'Possible Injection Payload';
      case 'anomaly': return 'Anomaly Analysis Mode';
      default: return 'Type to identify...';
    }
  };

  return (
    <div className="h-full p-8 overflow-y-auto custom-scrollbar bg-black/40 backdrop-blur-3xl">
      <div className="max-w-4xl mx-auto space-y-10 pb-20 relative">
        {/* Subtle grid backdrop */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff05_1px,transparent_1px),linear-gradient(to_bottom,#ffffff05_1px,transparent_1px)] bg-[size:40px_40px] pointer-events-none" />

        {/* Header */}
        <div className="space-y-3 relative">
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 shadow-[0_0_30px_rgba(6,182,212,0.2)] backdrop-blur-md">
              <ShieldAlert className="h-8 w-8 text-cyan-400" />
            </div>
            <h1 className="text-4xl font-black text-white tracking-tighter uppercase">Security Scan Tools</h1>
          </div>
          <p className="text-zinc-500 font-bold uppercase tracking-[0.2em] text-[10px] ml-1">
            Autonomous Diagnostic Interface // v4.2
          </p>
        </div>

        {/* Main Content Area */}
        <div className="space-y-8 relative">
          {/* Analysis Mode Switcher */}
          <div className="flex bg-zinc-900/80 p-1.5 rounded-2xl border border-white/10 w-fit backdrop-blur-xl shadow-2xl">
            <button 
              onClick={() => setOperation('phishing')}
              className={`px-6 py-2.5 rounded-xl text-[11px] font-black uppercase tracking-widest transition-all duration-300 ${operation !== 'anomaly' ? 'bg-cyan-500 text-white shadow-[0_0_20px_rgba(6,182,212,0.4)]' : 'text-zinc-500 hover:text-zinc-300'}`}
            >
              Standard Scan
            </button>
            <button 
              onClick={() => {
                setOperation('anomaly');
                setInputType('anomaly');
              }}
              className={`px-6 py-2.5 rounded-xl text-[11px] font-black uppercase tracking-widest transition-all duration-300 ${operation === 'anomaly' ? 'bg-orange-500 text-white shadow-[0_0_20px_rgba(249,115,22,0.4)]' : 'text-zinc-500 hover:text-zinc-300'}`}
            >
              Anomaly Detection
            </button>
          </div>

          <div className="bg-zinc-900/90 border border-white/10 rounded-[32px] p-8 shadow-[0_20px_50px_rgba(0,0,0,0.5)] backdrop-blur-3xl space-y-8">
            {operation !== 'anomaly' ? (
              <div className="space-y-8">
                {/* Text Input Area */}
                <div className="space-y-4">
                  <label className="text-[10px] font-black text-cyan-500 uppercase tracking-[0.3em] ml-2">Enter Input Payload</label>
                  <div className="relative group">
                    <div className="absolute -inset-1 bg-gradient-to-r from-cyan-500/10 to-purple-500/10 rounded-[24px] blur-xl opacity-50 group-focus-within:opacity-100 transition duration-500"></div>
                    <div className="relative bg-black/80 border border-white/10 rounded-3xl p-6 shadow-2xl">
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                          {getInputTypeIcon()}
                          <span className="text-[10px] font-black text-zinc-300 uppercase tracking-[0.2em]">
                            {getInputTypeLabel()}
                          </span>
                        </div>
                        {input && (
                          <button onClick={() => setInput('')} className="p-2 hover:bg-white/5 rounded-full text-zinc-500 hover:text-white transition-all">
                            <X className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                      <textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder="Paste URL, Email Content, or Script Injection here..."
                        className="w-full h-56 bg-transparent border-none text-white placeholder:text-zinc-800 focus:outline-none resize-none font-mono text-sm leading-relaxed custom-scrollbar"
                      />
                    </div>
                  </div>
                </div>

                {/* File Upload Area */}
                <AnimatePresence>
                  {input && (
                    <motion.div
                      initial={{ opacity: 0, y: -20 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -20 }}
                      className="space-y-4"
                    >
                      <label className="text-[10px] font-black text-purple-500 uppercase tracking-[0.3em] ml-2">Verify with Document (Optional)</label>
                      <div className="relative group">
                        <input type="file" ref={fileInputRef} onChange={(e) => handleFileUpload(e, 'normal')} className="hidden" />
                        <button
                          onClick={() => fileInputRef.current?.click()}
                          className={`w-full p-8 rounded-3xl border-2 border-dashed transition-all duration-500 flex flex-col items-center justify-center gap-4 ${file 
                              ? 'border-cyan-500/50 bg-cyan-500/5 text-cyan-400 shadow-[0_0_30px_rgba(6,182,212,0.1)]' 
                              : 'border-white/5 hover:border-white/20 hover:bg-white/5 text-zinc-600 hover:text-zinc-400'
                          }`}
                        >
                          {file ? (
                            <>
                              <div className="p-4 rounded-2xl bg-cyan-500/10">
                                <FileText className="h-10 w-10" />
                              </div>
                              <div className="text-center">
                                <p className="text-sm font-black uppercase tracking-widest text-white">{file.name}</p>
                                <p className="text-[10px] font-bold opacity-60 mt-1 uppercase tracking-tighter">{(file.size / 1024).toFixed(2)} KB • System Scanned</p>
                              </div>
                            </>
                          ) : (
                            <>
                              <Upload className="h-10 w-10 opacity-30" />
                              <span className="text-[11px] font-black uppercase tracking-[0.2em]">Drop file for context analysis</span>
                            </>
                          )}
                        </button>
                        {file && (
                          <button 
                            onClick={(e) => { e.stopPropagation(); setFile(null); }} 
                            className="absolute top-6 right-6 p-2 bg-black/40 rounded-xl hover:bg-red-500/20 text-zinc-500 hover:text-red-400 transition-all border border-white/5"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Vector Selection & Analyze Action */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4 border-t border-white/5">
                  <div className="space-y-4">
                    <label className="text-[10px] font-black text-zinc-500 uppercase tracking-widest ml-1">Analysis Vector</label>
                    <div className="flex flex-wrap gap-2">
                      {[ 
                        { id: 'phishing', label: 'Phishing', icon: Mail, color: 'text-cyan-400', active: 'bg-cyan-500/20 border-cyan-500/40 text-cyan-400' },
                        { id: 'url-analysis', label: 'URL Scan', icon: Link2, color: 'text-purple-400', active: 'bg-purple-500/20 border-purple-500/40 text-purple-400' },
                        { id: 'injection', label: 'Injection', icon: Database, color: 'text-emerald-400', active: 'bg-emerald-500/20 border-emerald-500/40 text-emerald-400' },
                      ].map((op) => (
                        <button
                          key={op.id}
                          onClick={() => setOperation(op.id as Operation)}
                          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl border text-[10px] font-black uppercase tracking-widest transition-all ${operation === op.id
                              ? op.active
                              : 'bg-white/2 border-white/5 text-zinc-500 hover:border-white/10 hover:text-zinc-400'
                          }`}
                        >
                          <op.icon className="h-3.5 w-3.5" />
                          {op.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="flex items-end">
                    <button
                      onClick={handleAnalyze}
                      disabled={(!input && !file) || isAnalyzing}
                      className={`w-full py-4 rounded-2xl flex items-center justify-center gap-3 transition-all duration-500 relative group ${(!input && !file) || isAnalyzing
                          ? 'bg-zinc-800/50 text-zinc-600 cursor-not-allowed border border-white/5'
                          : 'bg-cyan-500 text-white shadow-[0_0_30px_rgba(6,182,212,0.3)] hover:shadow-[0_0_50px_rgba(6,182,212,0.5)] hover:-translate-y-1 border border-cyan-400/50'
                      }`}
                    >
                      {isAnalyzing ? (
                        <>
                          <Loader2 className="h-5 w-5 animate-spin" />
                          <span className="text-[11px] font-black uppercase tracking-[0.2em]">Engaging...</span>
                        </>
                      ) : (
                        <>
                          <Zap className="h-5 w-5 transition-transform duration-500 group-hover:scale-110" />
                          <span className="text-[11px] font-black uppercase tracking-[0.2em]">Launch Analysis</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              /* Anomaly Section */
              <div className="space-y-8">
                <div className="space-y-4">
                  <label className="text-[10px] font-black text-orange-500 uppercase tracking-[0.3em] ml-2">Anomaly Detection Engine</label>
                  <div className="relative group">
                    <div className="absolute -inset-1 bg-gradient-to-r from-orange-500/20 to-red-500/20 rounded-[32px] blur-xl opacity-50 transition duration-500"></div>
                    <div className="relative bg-black/80 border border-white/10 rounded-[32px] p-12 flex flex-col items-center justify-center text-center space-y-8 shadow-2xl">
                      <div className="p-8 rounded-3xl bg-orange-500/10 border border-orange-500/20 shadow-[0_0_50px_rgba(249,115,22,0.1)]">
                        <Upload className="h-16 w-16 text-orange-400" />
                      </div>
                      <div className="space-y-3">
                        <h2 className="text-3xl font-black text-white uppercase tracking-tighter">Log Analysis</h2>
                        <p className="text-zinc-500 text-xs font-bold uppercase tracking-[0.2em] max-w-xs mx-auto leading-relaxed">
                          Structural deviations & malicious entropy detection
                        </p>
                      </div>
                      
                      <input type="file" ref={anomalyFileInputRef} onChange={(e) => handleFileUpload(e, 'anomaly')} className="hidden" />
                      <div className="flex flex-col items-center gap-4 w-full max-w-sm">
                        <button
                          onClick={() => anomalyFileInputRef.current?.click()}
                          className={`w-full py-5 rounded-2xl border-2 border-dashed transition-all duration-300 flex items-center justify-center gap-3 ${file 
                              ? 'border-orange-500/50 bg-orange-500/10 text-orange-400 shadow-[0_0_20px_rgba(249,115,22,0.1)]' 
                              : 'border-white/10 hover:border-white/20 hover:bg-white/5 text-zinc-500 hover:text-white'
                          }`}
                        >
                          {file ? (
                            <>
                              <CheckCircle2 className="h-5 w-5" />
                              <span className="text-[11px] font-black uppercase tracking-[0.1em] truncate max-w-[200px]">{file.name}</span>
                            </>
                          ) : (
                            <>
                              <Upload className="h-5 w-5" />
                              <span className="text-[11px] font-black uppercase tracking-[0.1em]">Select Log File</span>
                            </>
                          )}
                        </button>

                        <button
                          onClick={handleAnalyze}
                          disabled={!file || isAnalyzing}
                          className={`w-full py-5 rounded-2xl flex items-center justify-center gap-3 transition-all duration-500 ${!file || isAnalyzing
                              ? 'bg-zinc-800/50 text-zinc-700 cursor-not-allowed'
                              : 'bg-orange-600 text-white shadow-[0_0_40px_rgba(249,115,22,0.3)] hover:shadow-[0_0_60px_rgba(249,115,22,0.5)] hover:-translate-y-1 active:scale-95'
                          }`}
                        >
                          {isAnalyzing ? (
                            <Loader2 className="h-5 w-5 animate-spin" />
                          ) : (
                            <Zap className="h-5 w-5" />
                          )}
                          <span className="text-[11px] font-black uppercase tracking-[0.2em]">Engage Engine</span>
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Anomaly Result Board */}
                <AnimatePresence>
                  {fileResult && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.95, y: 20 }}
                      animate={{ opacity: 1, scale: 1, y: 0 }}
                      className="bg-zinc-900/90 border border-white/10 rounded-[32px] p-8 shadow-[0_30px_60px_rgba(0,0,0,0.6)] backdrop-blur-3xl space-y-8"
                    >
                      <div className="flex items-center justify-between pb-6 border-white/5 border-b">
                        <div className="flex items-center gap-4">
                          <div className={`h-14 w-14 rounded-2xl flex items-center justify-center ${fileResult.riskScore > 50 ? 'bg-red-500/20 text-red-400 shadow-[0_0_30px_rgba(239,68,68,0.2)]' : 'bg-emerald-500/20 text-emerald-400 shadow-[0_0_30px_rgba(16,185,129,0.2)]'}`}>
                            <ShieldAlert className="h-8 w-8" />
                          </div>
                          <div>
                            <h3 className="text-lg font-black text-white uppercase tracking-tighter">Inspection Result</h3>
                            <p className="text-[10px] text-zinc-500 font-black uppercase tracking-widest mt-1">Diagnostic Report: {file?.name}</p>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className={`text-4xl font-black tabular-nums ${fileResult.riskScore > 50 ? 'text-red-400' : 'text-emerald-400'}`}>{fileResult.riskScore}%</div>
                          <div className="text-[10px] text-zinc-600 font-bold uppercase tracking-widest">Anomaly Index</div>
                        </div>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="p-6 rounded-2xl bg-black/40 border border-white/5 space-y-2">
                          <span className="text-[10px] font-black text-zinc-500 uppercase tracking-widest">Heuristic Status</span>
                          <div className="flex items-center gap-2">
                            <div className={`h-2.5 w-2.5 rounded-full ${fileResult.riskLevel === 'Low' ? 'bg-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.5)]' : 'bg-red-400 shadow-[0_0_10px_rgba(239,68,68,0.5)]'} animate-pulse`} />
                            <span className="text-sm font-black text-white uppercase tracking-widest">{fileResult.riskLevel}</span>
                          </div>
                        </div>
                        <div className="p-6 rounded-2xl bg-black/40 border border-white/5 space-y-2">
                          <span className="text-[10px] font-black text-zinc-500 uppercase tracking-widest">Analysis Timestamp</span>
                          <div className="text-sm font-black text-white uppercase tracking-widest font-mono">{new Date().toLocaleTimeString()}</div>
                        </div>
                      </div>

                      <div className="p-8 rounded-2xl bg-black/60 border border-white/5 space-y-4">
                        <span className="text-[10px] font-black text-zinc-500 uppercase tracking-widest">AI Assessment Summary</span>
                        <p className="text-xs text-zinc-400 font-mono leading-relaxed">{fileResult.explanation}</p>
                      </div>

                      {fileResult.shapData && fileResult.shapData.length > 0 && (
                        <div className="space-y-4">
                          <span className="text-[10px] font-black text-red-400 uppercase tracking-widest ml-1">Critical Signatures Identified</span>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {fileResult.shapData.map((t: any, i: number) => (
                              <div key={i} className="flex items-center justify-between p-5 rounded-2xl bg-red-500/5 border border-red-500/10 shadow-lg">
                                <div className="flex items-center gap-3">
                                  <div className="h-1.5 w-1.5 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)]" />
                                  <span className="text-[10px] font-black text-zinc-300 uppercase tracking-widest">{t.feature}</span>
                                </div>
                                <span className="text-[10px] font-black text-red-400 uppercase tracking-widest bg-red-500/10 px-3 py-1.5 rounded-lg border border-red-500/20">{t.value}% Impact</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}
          </div>
        </div>

        {/* Standard Results Section */}
        <AnimatePresence>
          {result && operation !== 'anomaly' && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 20 }}
              className={`rounded-[40px] border-2 p-10 space-y-8 shadow-3xl backdrop-blur-2xl ${result.riskLevel === 'Critical' || result.riskLevel === 'High' || result.riskLevel === 'Medium'
                  ? 'bg-red-500/10 border-red-500/30'
                  : 'bg-emerald-500/10 border-emerald-500/30'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-5">
                  <div className={`p-4 rounded-2xl ${result.riskLevel === 'Critical' || result.riskLevel === 'High' || result.riskLevel === 'Medium' ? 'bg-red-500/20 text-red-400 shadow-[0_0_20px_rgba(239,68,68,0.2)]' : 'bg-emerald-500/20 text-emerald-400 shadow-[0_0_20px_rgba(16,185,129,0.2)]'}`}>
                    {result.riskLevel === 'Critical' || result.riskLevel === 'High' || result.riskLevel === 'Medium' ? (
                      <AlertTriangle className="h-8 w-8" />
                    ) : (
                      <CheckCircle2 className="h-8 w-8" />
                    )}
                  </div>
                  <div>
                    <h3 className={`text-2xl font-black uppercase tracking-tighter ${result.riskLevel === 'Critical' || result.riskLevel === 'High' || result.riskLevel === 'Medium' ? 'text-red-400' : 'text-emerald-400'}`}>
                      {result.riskLevel === 'Critical' || result.riskLevel === 'High' || result.riskLevel === 'Medium' ? 'Threat Detected' : 'Payload Verified'}
                    </h3>
                    <p className="text-[10px] font-black text-zinc-500 uppercase tracking-[0.3em] mt-1">Global Database Scan: 100% Complete</p>
                  </div>
                </div>
                {result.riskScore !== undefined && (
                  <div className="text-right">
                    <div className={`text-4xl font-black ${result.riskScore > 50 ? 'text-red-400' : 'text-emerald-400'}`}>{result.riskScore}%</div>
                    <div className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest">Risk Confidence</div>
                  </div>
                )}
              </div>
              
              <div className="p-8 rounded-3xl bg-black/50 border border-white/10 shadow-inner">
                <p className="text-sm text-zinc-300 leading-relaxed font-mono">
                  {result.explanation || 'The scanning engine has completed its analysis. No malicious signatures were identified in the provided payload.'}
                </p>
              </div>

              {result.shapData && result.shapData.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {result.shapData.map((threat: any, i: number) => (
                    <div key={i} className="p-4 rounded-2xl bg-black/60 border border-red-500/20 flex items-center justify-between group hover:border-red-500/40 transition-all">
                      <div className="flex items-center gap-3">
                        <div className="h-2 w-2 rounded-full bg-red-400 shadow-[0_0_10px_rgba(248,113,113,0.8)]" />
                        <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">{threat.feature}</span>
                      </div>
                      <span className="text-[10px] font-black text-red-400 uppercase tracking-widest bg-red-500/10 px-2 py-1 rounded">{threat.value}%</span>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default ScanTools;
