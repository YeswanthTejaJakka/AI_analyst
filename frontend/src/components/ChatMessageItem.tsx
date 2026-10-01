import React from 'react';
import { User, Bot, AlertTriangle, Filter } from 'lucide-react';
import type { ChatMessage } from '../types/api';
import { ClarificationCard } from './ClarificationCard';
import { SqlViewer } from './SqlViewer';
import { ResultTable } from './ResultTable';

interface ChatMessageItemProps {
  message: ChatMessage;
  onSelectClarificationOption: (fieldName: string, optionText?: string, customInput?: string) => void;
  isSubmittingClarification?: boolean;
}

export const ChatMessageItem: React.FC<ChatMessageItemProps> = ({
  message,
  onSelectClarificationOption,
  isSubmittingClarification,
}) => {
  const isUser = message.role === 'user';

  return (
    <div className={`flex gap-3 py-4 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="w-8 h-8 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shrink-0 mt-0.5">
          <Bot className="w-4 h-4" />
        </div>
      )}

      <div className={`max-w-3xl space-y-2 ${isUser ? 'items-end' : 'items-start'}`}>
        {/* User Message */}
        {isUser ? (
          <div className="bg-indigo-600 text-white rounded-2xl rounded-tr-none px-4 py-2.5 text-sm font-medium shadow-md">
            {message.content}
          </div>
        ) : (
          <div className="space-y-3">
            {/* Intent Badge if available */}
            {message.intent && (
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-900 border border-slate-800 text-[11px] font-mono text-slate-400">
                <Filter className="w-3 h-3 text-indigo-400" />
                <span>Intent:</span>
                <span className="text-slate-200 uppercase font-semibold">
                  {message.intent.operation}
                </span>
                {message.intent.entity && (
                  <span className="text-slate-400">({message.intent.entity})</span>
                )}
              </div>
            )}

            {/* Response Content Text */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl rounded-tl-none p-4 text-sm text-slate-100 leading-relaxed shadow-sm space-y-2">
              <p className="whitespace-pre-wrap">{message.content}</p>

              {/* Error Notice */}
              {message.error && (
                <div className="flex items-start gap-2 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs mt-2">
                  <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold block">Notice</span>
                    <span>{message.error}</span>
                  </div>
                </div>
              )}

              {/* Clarification Request */}
              {message.clarification && (
                <ClarificationCard
                  clarification={message.clarification}
                  onSelectOption={onSelectClarificationOption}
                  isSubmitting={isSubmittingClarification}
                />
              )}

              {/* SQL Viewer */}
              {message.sql && (
                <SqlViewer
                  sql={message.sql}
                  executionTimeMs={message.execution_time_ms}
                  rowCount={message.query_result?.row_count}
                />
              )}

              {/* Result Data Table */}
              {message.query_result && <ResultTable result={message.query_result} />}
            </div>
          </div>
        )}
      </div>

      {isUser && (
        <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 shrink-0 mt-0.5">
          <User className="w-4 h-4" />
        </div>
      )}
    </div>
  );
};
