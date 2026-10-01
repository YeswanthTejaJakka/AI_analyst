import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Copy, Check, Code, Clock, Hash } from 'lucide-react';

interface SqlViewerProps {
  sql: string;
  executionTimeMs?: number;
  rowCount?: number;
}

export const SqlViewer: React.FC<SqlViewerProps> = ({ sql, executionTimeMs, rowCount }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyToClipboard = () => {
    navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950 overflow-hidden my-2">
      {/* Toggle header */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-3 py-2 bg-slate-900/80 hover:bg-slate-900 flex items-center justify-between text-xs text-slate-300 transition-colors"
      >
        <div className="flex items-center gap-2 font-mono">
          {isOpen ? (
            <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
          )}
          <Code className="w-3.5 h-3.5 text-indigo-400" />
          <span className="font-semibold text-slate-200">Generated SQL Query</span>
        </div>

        <div className="flex items-center gap-3 text-[11px] font-mono text-slate-400">
          {executionTimeMs !== undefined && (
            <span className="flex items-center gap-1 text-slate-400">
              <Clock className="w-3 h-3 text-slate-500" />
              {executionTimeMs.toFixed(0)} ms
            </span>
          )}
          {rowCount !== undefined && (
            <span className="flex items-center gap-1 text-slate-400">
              <Hash className="w-3 h-3 text-slate-500" />
              {rowCount} rows
            </span>
          )}
          <span className="text-indigo-400 hover:underline">{isOpen ? 'Hide SQL' : 'View SQL'}</span>
        </div>
      </button>

      {/* SQL code block */}
      {isOpen && (
        <div className="relative p-3 bg-slate-950 border-t border-slate-800/80 font-mono text-xs text-indigo-200 overflow-x-auto">
          <button
            onClick={copyToClipboard}
            className="absolute top-2.5 right-2.5 p-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
            title="Copy SQL"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
          <pre className="pr-10 leading-relaxed font-mono whitespace-pre-wrap">{sql}</pre>
        </div>
      )}
    </div>
  );
};
