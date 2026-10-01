import type {
  ChatResponse,
  DatabaseConnectionResponse,
  DatabaseSchema,
  PostgresConnectParams,
} from '../types/api';

const API_BASE = '/api';

export async function connectSampleDatabase(): Promise<DatabaseConnectionResponse> {
  const res = await fetch(`${API_BASE}/database/sample`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to connect sample database' }));
    throw new Error(err.detail || 'Failed to connect sample database');
  }
  return res.json();
}

export async function uploadDatabase(file: File): Promise<DatabaseConnectionResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE}/database/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to upload database' }));
    throw new Error(err.detail || 'Failed to upload database');
  }
  return res.json();
}

export async function connectPostgres(
  params: PostgresConnectParams
): Promise<DatabaseConnectionResponse> {
  const res = await fetch(`${API_BASE}/database/connect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to connect PostgreSQL' }));
    throw new Error(err.detail || 'Failed to connect PostgreSQL');
  }
  return res.json();
}

export async function getSchema(sessionId: string): Promise<DatabaseSchema> {
  const res = await fetch(`${API_BASE}/database/${sessionId}/schema`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to fetch schema' }));
    throw new Error(err.detail || 'Failed to fetch schema');
  }
  const data = await res.json();
  return data.schema_data;
}

export async function sendMessage(
  databaseId: string,
  query: string,
  conversationId?: string
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      database_id: databaseId,
      query,
      conversation_id: conversationId,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to send message' }));
    throw new Error(err.detail || 'Failed to send message');
  }
  return res.json();
}

export async function sendClarification(
  conversationId: string,
  fieldName: string,
  selectedOption?: string,
  customInput?: string
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat/${conversationId}/clarify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      field_name: fieldName,
      selected_option: selectedOption,
      custom_input: customInput,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to submit clarification' }));
    throw new Error(err.detail || 'Failed to submit clarification');
  }
  return res.json();
}
