import React from 'react';
import { Sparkles } from 'lucide-react';

interface SuggestedQueriesProps {
  onSelectQuery: (query: string) => void;
}

const SAMPLE_PROMPTS = [
  'Who are our top 5 customers by total spending?',
  'Which products sold the most?',
  'What was our revenue last month?',
  'Which category generates the most revenue?',
  'Find customers who haven\'t ordered recently.',
  'What\'s the average order value?',
];

export const SuggestedQueries: React.FC<SuggestedQueriesProps> = ({ onSelectQuery }) => {
  return (
    <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/40 space-y-3 my-4">
      <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
        <Sparkles className="w-4 h-4 text-indigo-400" />
        <span>Example Prompts to Try</span>
      </div>

      <div className="flex flex-wrap gap-2">
        {SAMPLE_PROMPTS.map((prompt, idx) => (
          <button
            key={idx}
            onClick={() => onSelectQuery(prompt)}
            className="px-3 py-1.5 rounded-full bg-slate-800/90 hover:bg-indigo-600/20 border border-slate-700 hover:border-indigo-500/50 text-xs text-slate-300 hover:text-indigo-200 transition-all text-left"
          >
            • {prompt}
          </button>
        ))}
      </div>
    </div>
  );
};
