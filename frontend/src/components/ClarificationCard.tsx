import React, { useState } from 'react';
import { HelpCircle, Send, Sparkles } from 'lucide-react';
import type { ClarificationRequest } from '../types/api';

interface ClarificationCardProps {
  clarification: ClarificationRequest;
  onSelectOption: (fieldName: string, optionText?: string, customInput?: string) => void;
  isSubmitting?: boolean;
}

export const ClarificationCard: React.FC<ClarificationCardProps> = ({
  clarification,
  onSelectOption,
  isSubmitting,
}) => {
  const [customInput, setCustomInput] = useState('');

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (customInput.trim()) {
      onSelectOption(clarification.field_name, undefined, customInput.trim());
    }
  };

  return (
    <div className="rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-4 space-y-3 my-3 shadow-lg shadow-indigo-950/30">
      {/* Header */}
      <div className="flex items-start gap-2.5">
        <div className="p-1.5 rounded-lg bg-indigo-600/20 border border-indigo-500/30 text-indigo-400 mt-0.5">
          <HelpCircle className="w-4 h-4" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-indigo-300 uppercase tracking-wider">
              Clarification Required
            </span>
            <span className="text-[10px] bg-indigo-500/20 text-indigo-300 px-1.5 py-0.5 rounded font-mono">
              Field: {clarification.field_name}
            </span>
          </div>
          <p className="text-sm font-medium text-slate-100 mt-1 leading-snug">
            {clarification.question}
          </p>
        </div>
      </div>

      {/* Concrete Option Buttons */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
        {clarification.options.map((option, idx) => (
          <button
            key={idx}
            disabled={isSubmitting}
            onClick={() => onSelectOption(clarification.field_name, option)}
            className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/90 border border-indigo-500/20 hover:border-indigo-400 hover:bg-slate-800 text-left text-xs font-medium text-slate-200 hover:text-white transition-all shadow-sm group disabled:opacity-50"
          >
            <span className="pr-2">{option}</span>
            <Sparkles className="w-3.5 h-3.5 text-indigo-400 group-hover:scale-110 transition-transform shrink-0" />
          </button>
        ))}
      </div>

      {/* Free-text write-in input */}
      <form onSubmit={handleCustomSubmit} className="flex gap-2 pt-1">
        <input
          type="text"
          placeholder="Or type your custom definition / period..."
          value={customInput}
          onChange={(e) => setCustomInput(e.target.value)}
          className="flex-1 bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
        />
        <button
          type="submit"
          disabled={!customInput.trim() || isSubmitting}
          className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
        >
          <span>Submit</span>
          <Send className="w-3 h-3" />
        </button>
      </form>
    </div>
  );
};
