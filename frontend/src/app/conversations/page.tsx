'use client';

import { useState } from 'react';
import { fetchAPI, type Conversation } from '@/lib/api';

export default function ConversationsPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [loaded, setLoaded] = useState(false);

  async function loadConversations() {
    const data = await fetchAPI('/conversations');
    setConversations(data);
    setLoaded(true);
  }

  return (
    <div className="flex gap-4 h-[calc(100vh-3rem)]">
      {/* List panel */}
      <div className="w-80 flex flex-col bg-white rounded shadow overflow-hidden">
        <div className="p-3 border-b flex items-center justify-between">
          <h3 className="font-semibold text-sm">Conversations</h3>
          <button onClick={loadConversations} className="text-xs text-blue-600 hover:underline">
            {loaded ? 'Refresh' : 'Load'}
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {!loaded && <p className="p-3 text-gray-500 text-sm">Click Load to fetch conversations.</p>}
          {conversations.map((c) => (
            <div
              key={c.id}
              onClick={() => setSelected(c)}
              className={`p-3 border-b cursor-pointer hover:bg-gray-50 text-sm ${
                selected?.id === c.id ? 'bg-blue-50' : ''
              }`}
            >
              <div className="font-medium">{c.target_display_name || c.target_user_id}</div>
              <div className="text-gray-500 text-xs mt-0.5">
                {c.state} &middot; {c.turn_count} turns
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Chat panel */}
      <div className="flex-1 bg-white rounded shadow flex flex-col overflow-hidden">
        {selected ? (
          <>
            <div className="p-3 border-b">
              <div className="font-semibold">{selected.target_display_name || selected.target_user_id}</div>
              <div className="text-xs text-gray-500">State: {selected.state}</div>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {selected.messages.map((m) => (
                <div
                  key={m.id}
                  className={`max-w-[70%] px-3 py-2 rounded-lg text-sm ${
                    m.direction === 'outbound'
                      ? 'ml-auto bg-blue-600 text-white'
                      : 'mr-auto bg-gray-100'
                  }`}
                >
                  <p>{m.content}</p>
                  <div className={`text-xs mt-1 ${m.direction === 'outbound' ? 'text-blue-200' : 'text-gray-400'}`}>
                    {new Date(m.created_at).toLocaleTimeString()}
                  </div>
                </div>
              ))}
              {selected.messages.length === 0 && (
                <p className="text-gray-400 text-sm text-center mt-8">No messages yet</p>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-400">
            Select a conversation to view messages
          </div>
        )}
      </div>
    </div>
  );
}
