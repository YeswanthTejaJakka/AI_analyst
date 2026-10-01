import { useState, useEffect, useRef } from 'react';
import { Send, Sparkles, Database, RefreshCw } from 'lucide-react';
import type {
  ChatMessage,
  DatabaseConnectionResponse,
  DatabaseSchema,
} from './types/api';
import {
  connectSampleDatabase,
  getSchema,
  sendMessage,
  sendClarification,
} from './services/api';
import { Navbar } from './components/Navbar';
import { Sidebar } from './components/Sidebar';
import { ChatMessageItem } from './components/ChatMessageItem';
import { DatabaseConnectModal } from './components/DatabaseConnectModal';
import { SuggestedQueries } from './components/SuggestedQueries';

export function App() {
  const [connection, setConnection] = useState<DatabaseConnectionResponse | null>(null);
  const [schema, setSchema] = useState<DatabaseSchema | null>(null);
  const [isLoadingSchema, setIsLoadingSchema] = useState(false);
  const [isConnectModalOpen, setIsConnectModalOpen] = useState(false);

  // Chat state
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputQuery, setInputQuery] = useState('');
  const [isSending, setIsSending] = useState(false);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  // Auto connect sample database on mount if none connected
  useEffect(() => {
    const autoConnect = async () => {
      setIsLoadingSchema(true);
      try {
        const conn = await connectSampleDatabase();
        setConnection(conn);
        const sch = await getSchema(conn.session_id);
        setSchema(sch);
      } catch (err) {
        console.error('Failed to auto-connect sample database:', err);
      } finally {
        setIsLoadingSchema(false);
      }
    };
    autoConnect();
  }, []);

  // Scroll chat to bottom on new messages
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isSending]);

  const handleDatabaseConnected = async (conn: DatabaseConnectionResponse) => {
    setConnection(conn);
    setConversationId(undefined);
    setMessages([]);
    setIsLoadingSchema(true);
    try {
      const sch = await getSchema(conn.session_id);
      setSchema(sch);
    } catch (err) {
      console.error('Failed to fetch schema after connection:', err);
    } finally {
      setIsLoadingSchema(false);
    }
  };

  const handleSendQuery = async (queryText: string) => {
    if (!queryText.trim() || !connection || isSending) return;

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: queryText.trim(),
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputQuery('');
    setIsSending(true);

    try {
      const res = await sendMessage(connection.session_id, queryText.trim(), conversationId);
      setConversationId(res.conversation_id);
      setMessages((prev) => [...prev, res.message]);
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: Date.now().toString(),
        role: 'assistant',
        content: `Error processing query: ${err.message || 'Server error'}`,
        timestamp: new Date().toISOString(),
        error: err.message,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsSending(false);
    }
  };

  const handleClarificationOption = async (
    fieldName: string,
    optionText?: string,
    customInput?: string
  ) => {
    if (!conversationId || !connection || isSending) return;

    const answer = customInput || optionText || '';
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: answer,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsSending(true);

    try {
      const res = await sendClarification(conversationId, fieldName, optionText, customInput);
      setMessages((prev) => [...prev, res.message]);
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: Date.now().toString(),
        role: 'assistant',
        content: `Error processing clarification: ${err.message || 'Server error'}`,
        timestamp: new Date().toISOString(),
        error: err.message,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Navbar */}
      <Navbar
        connection={connection}
        onOpenConnectModal={() => setIsConnectModalOpen(true)}
      />

      {/* Main Content Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <Sidebar
          schema={schema}
          isLoadingSchema={isLoadingSchema}
          onOpenConnectModal={() => setIsConnectModalOpen(true)}
        />

        {/* Chat Main View */}
        <main className="flex-1 flex flex-col h-[calc(100vh-3.5rem)] bg-slate-950">
          {/* Scrollable Conversation Stream */}
          <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-6 space-y-4">
            {/* Header banner if no messages */}
            {messages.length === 0 && (
              <div className="max-w-3xl mx-auto space-y-6 text-center py-8">
                <div className="inline-flex p-3 rounded-2xl bg-indigo-600/10 border border-indigo-500/20 text-indigo-400">
                  <Sparkles className="w-8 h-8" />
                </div>
                <div className="space-y-2">
                  <h2 className="text-2xl font-bold tracking-tight text-white">
                    Natural Language Database Analyst
                  </h2>
                  <p className="text-sm text-slate-400 max-w-lg mx-auto leading-relaxed">
                    Ask questions in plain English. QueryPilot detects query ambiguities, asks targeted clarification questions, generates safe SQL, and explains the results.
                  </p>
                </div>

                {connection && (
                  <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-left max-w-xl mx-auto text-xs space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-slate-200 flex items-center gap-1.5">
                        <Database className="w-4 h-4 text-indigo-400" />
                        Connected: {connection.database_name}
                      </span>
                      <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                        {connection.database_type}
                      </span>
                    </div>
                    <p className="text-slate-400">
                      Discovered {connection.total_tables} tables with {connection.total_relationships} relationships.
                    </p>
                  </div>
                )}

                <SuggestedQueries onSelectQuery={handleSendQuery} />
              </div>
            )}

            {/* Conversation Messages */}
            <div className="max-w-4xl mx-auto space-y-2">
              {messages.map((msg) => (
                <ChatMessageItem
                  key={msg.id}
                  message={msg}
                  onSelectClarificationOption={handleClarificationOption}
                  isSubmittingClarification={isSending}
                />
              ))}

              {isSending && (
                <div className="flex gap-3 py-4 items-start">
                  <div className="w-8 h-8 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shrink-0">
                    <Sparkles className="w-4 h-4 animate-spin" />
                  </div>
                  <div className="bg-slate-900 border border-slate-800 rounded-2xl rounded-tl-none px-4 py-3 text-xs text-slate-400 flex items-center gap-2">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-400" />
                    <span>Analyzing intent and generating safe query...</span>
                  </div>
                </div>
              )}
              <div ref={chatBottomRef} />
            </div>
          </div>

          {/* Bottom Query Input Bar */}
          <div className="p-4 border-t border-slate-800/80 bg-slate-950/90 backdrop-blur">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendQuery(inputQuery);
              }}
              className="max-w-4xl mx-auto flex gap-2"
            >
              <div className="relative flex-1">
                <input
                  type="text"
                  placeholder={
                    connection
                      ? 'Ask a question in natural language... (e.g. "Who is our best customer?")'
                      : 'Please connect a database to start...'
                  }
                  disabled={!connection || isSending}
                  value={inputQuery}
                  onChange={(e) => setInputQuery(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 focus:border-indigo-500 rounded-xl px-4 py-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none shadow-inner disabled:opacity-50"
                />
              </div>

              <button
                type="submit"
                disabled={!inputQuery.trim() || !connection || isSending}
                className="px-5 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs flex items-center gap-2 shadow-lg shadow-indigo-600/20 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <span>Query</span>
                <Send className="w-3.5 h-3.5" />
              </button>
            </form>
          </div>
        </main>
      </div>

      {/* Database Connection Modal */}
      <DatabaseConnectModal
        isOpen={isConnectModalOpen}
        onClose={() => setIsConnectModalOpen(false)}
        onConnected={handleDatabaseConnected}
      />
    </div>
  );
}

export default App;
