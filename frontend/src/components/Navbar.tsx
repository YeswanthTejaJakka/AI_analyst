import React from 'react';
import { Database, ShieldCheck, Sparkles } from 'lucide-react';
import type { DatabaseConnectionResponse } from '../types/api';

interface NavbarProps {
  connection: DatabaseConnectionResponse | null;
  onOpenConnectModal: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ connection, onOpenConnectModal }) => {
  return (
    <header className="h-14 border-b border-slate-800 bg-slate-950/80 backdrop-blur px-4 flex items-center justify-between sticky top-0 z-20">
      <div className="flex items-center gap-3">
        <div className="bg-indigo-600/20 p-2 rounded-lg border border-indigo-500/30 text-indigo-400">
          <Sparkles className="w-5 h-5" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-base font-semibold text-slate-100 tracking-tight">QueryPilot</h1>
            <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 font-medium border border-indigo-500/20">
              AI Analyst
            </span>
          </div>
          <p className="text-xs text-slate-400 hidden sm:block">
            Ambiguity-aware Natural Language Database Querying
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {connection ? (
          <button
            onClick={onOpenConnectModal}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 hover:border-indigo-500/50 text-xs text-slate-300 hover:text-white transition-all shadow-sm group"
          >
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-medium max-w-[140px] truncate">{connection.database_name}</span>
            <span className="text-[10px] text-slate-400 group-hover:text-slate-300 uppercase px-1.5 py-0.5 rounded bg-slate-800">
              {connection.database_type}
            </span>
          </button>
        ) : (
          <button
            onClick={onOpenConnectModal}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs shadow-lg shadow-indigo-600/20 transition-all"
          >
            <Database className="w-3.5 h-3.5" />
            Connect Database
          </button>
        )}

        <div className="hidden md:flex items-center gap-1.5 text-xs text-emerald-400/90 bg-emerald-950/40 border border-emerald-800/40 px-2.5 py-1 rounded-md">
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>Read-Only Guard Active</span>
        </div>
      </div>
    </header>
  );
};
