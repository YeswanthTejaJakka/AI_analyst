import React, { useState } from 'react';
import {
  Database,
  Table as TableIcon,
  ChevronDown,
  ChevronRight,
  Key,
  Link,
  Search,
  FileSpreadsheet,
} from 'lucide-react';
import type { DatabaseSchema } from '../types/api';

interface SidebarProps {
  schema: DatabaseSchema | null;
  isLoadingSchema: boolean;
  onOpenConnectModal: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ schema, isLoadingSchema, onOpenConnectModal }) => {
  const [expandedTables, setExpandedTables] = useState<Record<string, boolean>>({});
  const [searchTerm, setSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState<'tables' | 'relationships'>('tables');

  const toggleTable = (tableName: string) => {
    setExpandedTables((prev) => ({ ...prev, [tableName]: !prev[tableName] }));
  };

  const filteredTables = schema?.tables.filter((t) =>
    t.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <aside className="w-72 bg-slate-950 border-r border-slate-800 flex flex-col h-[calc(100vh-3.5rem)] text-xs">
      {/* Sidebar Header */}
      <div className="p-3 border-b border-slate-800 space-y-2">
        <div className="flex items-center justify-between text-slate-300">
          <span className="font-semibold flex items-center gap-1.5 text-slate-200">
            <Database className="w-4 h-4 text-indigo-400" />
            Schema Explorer
          </span>
          <button
            onClick={onOpenConnectModal}
            className="text-[11px] text-indigo-400 hover:text-indigo-300 hover:underline"
          >
            Change DB
          </button>
        </div>

        {schema && (
          <div className="text-[11px] text-slate-400 flex items-center gap-3">
            <span>{schema.total_tables} Tables</span>
            <span>•</span>
            <span>{schema.total_relationships} Relationships</span>
            <span>•</span>
            <span className="uppercase text-slate-500 font-mono text-[10px]">{schema.dialect}</span>
          </div>
        )}

        {/* Tab switcher */}
        <div className="flex rounded-md bg-slate-900 p-0.5 border border-slate-800">
          <button
            onClick={() => setActiveTab('tables')}
            className={`flex-1 py-1 text-center font-medium rounded ${
              activeTab === 'tables' ? 'bg-slate-800 text-indigo-400 shadow-sm' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Tables ({schema?.tables.length || 0})
          </button>
          <button
            onClick={() => setActiveTab('relationships')}
            className={`flex-1 py-1 text-center font-medium rounded ${
              activeTab === 'relationships' ? 'bg-slate-800 text-indigo-400 shadow-sm' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Relations ({schema?.relationships.length || 0})
          </button>
        </div>

        {/* Search */}
        {activeTab === 'tables' && (
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2 text-slate-500" />
            <input
              type="text"
              placeholder="Search tables..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-md pl-8 pr-2 py-1 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 text-xs"
            />
          </div>
        )}
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {isLoadingSchema ? (
          <div className="p-4 text-center text-slate-500 space-y-2">
            <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto" />
            <p>Loading schema structure...</p>
          </div>
        ) : !schema ? (
          <div className="p-4 text-center text-slate-500 space-y-3">
            <FileSpreadsheet className="w-8 h-8 mx-auto text-slate-600" />
            <p>No active database connected.</p>
            <button
              onClick={onOpenConnectModal}
              className="px-3 py-1.5 rounded bg-indigo-600 text-white font-medium text-xs hover:bg-indigo-500"
            >
              Try Sample Database
            </button>
          </div>
        ) : activeTab === 'tables' ? (
          filteredTables && filteredTables.length > 0 ? (
            filteredTables.map((table) => {
              const isExpanded = expandedTables[table.name];
              return (
                <div key={table.name} className="rounded border border-slate-900 bg-slate-900/40 overflow-hidden">
                  <button
                    onClick={() => toggleTable(table.name)}
                    className="w-full flex items-center justify-between px-2.5 py-1.5 hover:bg-slate-800/60 transition-colors text-left"
                  >
                    <div className="flex items-center gap-2 font-mono text-slate-200 truncate">
                      {isExpanded ? (
                        <ChevronDown className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      )}
                      <TableIcon className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                      <span className="font-semibold text-slate-200 truncate">{table.name}</span>
                    </div>
                    <span className="text-[10px] font-mono text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded shrink-0">
                      ~{table.row_count}
                    </span>
                  </button>

                  {isExpanded && (
                    <div className="px-3 py-2 bg-slate-950/80 border-t border-slate-800/80 space-y-1.5">
                      {table.columns.map((col) => {
                        const isPk = table.primary_keys.includes(col.name) || col.primary_key;
                        const fk = table.foreign_keys.find((f) => f.column === col.name);

                        return (
                          <div key={col.name} className="flex items-center justify-between font-mono text-[11px]">
                            <div className="flex items-center gap-1.5 truncate">
                              {isPk ? (
                                <span title="Primary Key">
                                  <Key className="w-3 h-3 text-amber-400 shrink-0" />
                                </span>
                              ) : fk ? (
                                <span title={`FK -> ${fk.references_table}.${fk.references_column}`}>
                                  <Link className="w-3 h-3 text-indigo-400 shrink-0" />
                                </span>
                              ) : (
                                <span className="w-3 h-3 block border-l-2 border-slate-700 ml-1" />
                              )}
                              <span className={`truncate ${isPk ? 'text-amber-200 font-semibold' : 'text-slate-300'}`}>
                                {col.name}
                              </span>
                            </div>
                            <span className="text-[10px] text-slate-500 shrink-0 uppercase">{col.type}</span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })
          ) : (
            <div className="p-3 text-center text-slate-500">No tables matched "{searchTerm}"</div>
          )
        ) : (
          /* Relationships tab */
          <div className="space-y-2">
            {schema.relationships.map((rel, idx) => (
              <div key={idx} className="p-2 rounded bg-slate-900 border border-slate-800 space-y-1">
                <div className="flex items-center justify-between text-indigo-300 font-mono text-[11px]">
                  <span className="font-semibold">{rel.from_table}</span>
                  <span className="text-slate-500 text-[10px]">→</span>
                  <span className="font-semibold">{rel.to_table}</span>
                </div>
                <div className="text-[10px] text-slate-400 font-mono">
                  {rel.from_table}.{rel.from_column} = {rel.to_table}.{rel.to_column}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
};
