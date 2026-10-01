export interface ColumnInfo {
  name: string;
  type: string;
  nullable?: boolean;
  primary_key?: boolean;
  default_value?: string;
  description?: string;
}

export interface ForeignKeyInfo {
  column: string;
  references_table: string;
  references_column: string;
}

export interface TableInfo {
  name: string;
  columns: ColumnInfo[];
  primary_keys: string[];
  foreign_keys: ForeignKeyInfo[];
  row_count: number;
  description?: string;
}

export interface RelationshipInfo {
  from_table: string;
  from_column: string;
  to_table: string;
  to_column: string;
  type: string;
}

export interface DatabaseSchema {
  database_id: string;
  database_name: string;
  dialect: 'sqlite' | 'postgresql';
  tables: TableInfo[];
  relationships: RelationshipInfo[];
  total_tables: number;
  total_relationships: number;
}

export interface SchemaTableSummary {
  name: string;
  columns: number;
  row_count: number;
}

export interface DatabaseConnectionResponse {
  session_id: string;
  database_name: string;
  database_type: 'sample' | 'sqlite' | 'postgresql';
  total_tables: number;
  total_relationships: number;
  tables: SchemaTableSummary[];
  message: string;
}

export interface ClarificationOption {
  text: string;
  field?: string;
}

export interface ClarificationRequest {
  field_name: string;
  question: string;
  options: string[];
}

export interface QueryIntent {
  entity?: string;
  operation?: string;
  metric?: string;
  time_range?: string;
  limit?: number;
  sort_direction?: string;
  is_ambiguous: boolean;
  unsupported_reason?: string;
}

export interface QueryResult {
  columns: string[];
  rows: any[][];
  row_count: number;
  execution_time_ms: number;
  truncated: boolean;
  sql: string;
  error?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  intent?: QueryIntent;
  clarification?: ClarificationRequest;
  sql?: string;
  query_result?: QueryResult;
  execution_time_ms?: number;
  error?: string;
}

export interface ChatResponse {
  conversation_id: string;
  message: ChatMessage;
  has_clarification: boolean;
}

export interface PostgresConnectParams {
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
  ssl?: string;
}
