import React, { useState } from 'react';
import { ChevronLeft, ChevronRight, Download, Table as TableIcon } from 'lucide-react';
import type { QueryResult } from '../types/api';

interface ResultTableProps {
  result: QueryResult;
}

export const ResultTable: React.FC<ResultTableProps> = ({ result }) => {
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  if (!result.columns || result.columns.length === 0) {
    return null;
  }

  const totalPages = Math.ceil(result.rows.length / pageSize) || 1;
  const startIndex = (currentPage - 1) * pageSize;
  const currentRows = result.rows.slice(startIndex, startIndex + pageSize);

  const downloadCSV = () => {
    const csvContent = [
      result.columns.join(','),
      ...result.rows.map((row) =>
        row.map((val) => `"${String(val ?? '').replace(/"/g, '""')}"`).join(',')
      ),
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', 'querypilot_result.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const formatCellValue = (val: any) => {
    if (val === null || val === undefined) {
      return <span className="text-slate-600 italic">null</span>;
    }
    if (typeof val === 'number') {
      return val.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }
    return String(val);
  };

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950 overflow-hidden my-3 shadow-md">
      {/* Table Top Bar */}
      <div className="px-3 py-2 bg-slate-900 border-b border-slate-800 flex items-center justify-between text-xs">
        <div className="flex items-center gap-2 text-slate-300 font-medium">
          <TableIcon className="w-4 h-4 text-indigo-400" />
          <span>Results ({result.row_count} rows)</span>
          {result.truncated && (
            <span className="text-[10px] bg-amber-500/10 text-amber-400 px-1.5 py-0.5 rounded border border-amber-500/20">
              Truncated
            </span>
          )}
        </div>

        <button
          onClick={downloadCSV}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors text-xs"
        >
          <Download className="w-3.5 h-3.5" />
          Export CSV
        </button>
      </div>

      {/* Data Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="bg-slate-900/60 border-b border-slate-800 font-mono text-slate-300 uppercase tracking-wider text-[11px]">
              {result.columns.map((col, idx) => (
                <th key={idx} className="px-3 py-2.5 font-semibold border-r border-slate-800/60 last:border-r-0 whitespace-nowrap">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            {currentRows.length > 0 ? (
              currentRows.map((row, rIdx) => (
                <tr key={rIdx} className="hover:bg-slate-900/40 transition-colors font-mono">
                  {row.map((cell, cIdx) => (
                    <td key={cIdx} className="px-3 py-2 text-slate-200 border-r border-slate-800/40 last:border-r-0 whitespace-nowrap">
                      {formatCellValue(cell)}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={result.columns.length} className="px-3 py-4 text-center text-slate-500 italic">
                  No records returned
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      {totalPages > 1 && (
        <div className="px-3 py-2 bg-slate-900/80 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400 font-mono">
          <span>
            Showing {startIndex + 1}-{Math.min(startIndex + pageSize, result.rows.length)} of {result.rows.length}
          </span>

          <div className="flex items-center gap-2">
            <button
              disabled={currentPage === 1}
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              className="p-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span>
              Page {currentPage} of {totalPages}
            </span>
            <button
              disabled={currentPage === totalPages}
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              className="p-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
