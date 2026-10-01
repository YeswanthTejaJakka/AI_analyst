import React, { useState } from 'react';
import {
  X,
  Database,
  Upload,
  Server,
  AlertTriangle,
  Check,
  ShieldCheck,
  Sparkles,
  FileCode,
} from 'lucide-react';
import type { DatabaseConnectionResponse, PostgresConnectParams } from '../types/api';
import { connectSampleDatabase, uploadDatabase, connectPostgres } from '../services/api';

interface DatabaseConnectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConnected: (connection: DatabaseConnectionResponse) => void;
}

export const DatabaseConnectModal: React.FC<DatabaseConnectModalProps> = ({
  isOpen,
  onClose,
  onConnected,
}) => {
  const [activeTab, setActiveTab] = useState<'sample' | 'upload' | 'postgres'>('sample');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  // PostgreSQL state
  const [pgParams, setPgParams] = useState<PostgresConnectParams>({
    host: '',
    port: 5432,
    database: '',
    username: '',
    password: '',
    ssl: 'prefer',
  });

  if (!isOpen) return null;

  const handleConnectSample = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const conn = await connectSampleDatabase();
      onConnected(conn);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to connect sample database');
    } finally {
      setIsLoading(false);
    }
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;

    setIsLoading(true);
    setError(null);
    try {
      const conn = await uploadDatabase(selectedFile);
      onConnected(conn);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to upload database');
    } finally {
      setIsLoading(false);
    }
  };

  const handlePostgresSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pgParams.host.toLowerCase().includes('localhost') || pgParams.host.includes('127.0.0.1')) {
      setError(
        'Local databases cannot be accessed directly by the cloud server. Please run the backend locally or upload a SQLite .db file.'
      );
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const conn = await connectPostgres(pgParams);
      onConnected(conn);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to connect PostgreSQL database');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
      <div className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col">
        {/* Modal Header */}
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-slate-100">Connect Database</h2>
              <p className="text-xs text-slate-400">Select a database source to analyze</p>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white p-1 rounded-lg">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-slate-800 bg-slate-950/50 p-1.5 gap-1 text-xs">
          <button
            onClick={() => { setActiveTab('sample'); setError(null); }}
            className={`flex-1 py-2 px-3 rounded-lg font-medium flex items-center justify-center gap-1.5 transition-all ${
              activeTab === 'sample'
                ? 'bg-indigo-600 text-white shadow'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            Sample DB
          </button>
          <button
            onClick={() => { setActiveTab('upload'); setError(null); }}
            className={`flex-1 py-2 px-3 rounded-lg font-medium flex items-center justify-center gap-1.5 transition-all ${
              activeTab === 'upload'
                ? 'bg-indigo-600 text-white shadow'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <Upload className="w-3.5 h-3.5" />
            Upload SQLite
          </button>
          <button
            onClick={() => { setActiveTab('postgres'); setError(null); }}
            className={`flex-1 py-2 px-3 rounded-lg font-medium flex items-center justify-center gap-1.5 transition-all ${
              activeTab === 'postgres'
                ? 'bg-indigo-600 text-white shadow'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <Server className="w-3.5 h-3.5" />
            PostgreSQL
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 space-y-4">
          {error && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {/* Mode A: Sample DB */}
          {activeTab === 'sample' && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-sm text-slate-200">Sample E-Commerce Database</span>
                  <span className="text-[10px] bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded border border-emerald-500/20">
                    Ready Instant Access
                  </span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Pre-populated database containing 1,000+ customers, 5,000+ orders, 10,000+ order items, 500+ products, and 20 categories. Ideal for testing complex joins, aggregations, and ambiguity detection.
                </p>
                <div className="grid grid-cols-2 gap-2 font-mono text-[11px] text-slate-300 pt-1">
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    • customers (1,000)
                  </div>
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    • orders (5,000)
                  </div>
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    • order_items (10,000)
                  </div>
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    • products (500)
                  </div>
                </div>
              </div>

              <button
                onClick={handleConnectSample}
                disabled={isLoading}
                className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/20 transition-all disabled:opacity-50"
              >
                {isLoading ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Connecting Sample Database...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    Connect Sample Database
                  </>
                )}
              </button>
            </div>
          )}

          {/* Mode B: Upload SQLite DB */}
          {activeTab === 'upload' && (
            <form onSubmit={handleUploadSubmit} className="space-y-4">
              <div className="border-2 border-dashed border-slate-700 hover:border-indigo-500 rounded-xl p-6 text-center bg-slate-950/60 transition-colors">
                <FileCode className="w-8 h-8 text-indigo-400 mx-auto mb-2" />
                <label className="block text-xs font-medium text-slate-200 cursor-pointer">
                  <span>Choose a SQLite .db file</span>
                  <input
                    type="file"
                    accept=".db,.sqlite,.sqlite3"
                    className="hidden"
                    onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                  />
                </label>
                <p className="text-[11px] text-slate-500 mt-1">Supports SQLite files up to 50 MB</p>
                {selectedFile && (
                  <div className="mt-3 p-2 bg-indigo-950/40 border border-indigo-500/30 rounded-lg text-xs font-mono text-indigo-300 inline-flex items-center gap-2">
                    <Check className="w-3.5 h-3.5" />
                    <span>{selectedFile.name} ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)</span>
                  </div>
                )}
              </div>

              <button
                type="submit"
                disabled={!selectedFile || isLoading}
                className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/20 transition-all disabled:opacity-50"
              >
                {isLoading ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Introspecting Schema...
                  </>
                ) : (
                  <>
                    <Upload className="w-4 h-4" />
                    Upload & Introspect
                  </>
                )}
              </button>
            </form>
          )}

          {/* Mode C: Remote PostgreSQL */}
          {activeTab === 'postgres' && (
            <form onSubmit={handlePostgresSubmit} className="space-y-3">
              <div className="p-3 rounded-lg bg-indigo-950/30 border border-indigo-500/20 text-[11px] text-indigo-300 flex items-start gap-2">
                <ShieldCheck className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                <span>
                  We strongly recommend using a <strong>read-only</strong> PostgreSQL user account. Passwords are used only during the session and are never saved to disk.
                </span>
              </div>

              <div className="grid grid-cols-3 gap-2">
                <div className="col-span-2 space-y-1">
                  <label className="text-[11px] font-medium text-slate-300">Host</label>
                  <input
                    type="text"
                    required
                    placeholder="db.example.com"
                    value={pgParams.host}
                    onChange={(e) => setPgParams({ ...pgParams, host: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-indigo-500 font-mono"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[11px] font-medium text-slate-300">Port</label>
                  <input
                    type="number"
                    required
                    value={pgParams.port}
                    onChange={(e) => setPgParams({ ...pgParams, port: Number(e.target.value) })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-indigo-500 font-mono"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-[11px] font-medium text-slate-300">Database Name</label>
                <input
                  type="text"
                  required
                  placeholder="ecommerce"
                  value={pgParams.database}
                  onChange={(e) => setPgParams({ ...pgParams, database: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-indigo-500 font-mono"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <label className="text-[11px] font-medium text-slate-300">Username</label>
                  <input
                    type="text"
                    required
                    placeholder="ai_readonly"
                    value={pgParams.username}
                    onChange={(e) => setPgParams({ ...pgParams, username: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-indigo-500 font-mono"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[11px] font-medium text-slate-300">Password</label>
                  <input
                    type="password"
                    required
                    placeholder="••••••••"
                    value={pgParams.password}
                    onChange={(e) => setPgParams({ ...pgParams, password: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-indigo-500 font-mono"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/20 transition-all disabled:opacity-50 mt-2"
              >
                {isLoading ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Testing Connection & Introspecting...
                  </>
                ) : (
                  <>
                    <Server className="w-4 h-4" />
                    Connect & Discover Schema
                  </>
                )}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};
