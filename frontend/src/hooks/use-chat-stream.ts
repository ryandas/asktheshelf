'use client';
import { useState, useCallback, useRef } from 'react';
import { v4 as uuidv4 } from 'uuid';

export interface Source {
  book: string;
  excerpt: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources: Source[];
}

export function useChatStream() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const threadId = useRef(uuidv4());

  const sendMessage = useCallback(async (content: string) => {
    const userMsg: Message = { id: uuidv4(), role: 'user', content, sources: [] };
    const assistantId = uuidv4();
    const assistantMsg: Message = { id: assistantId, role: 'assistant', content: '', sources: [] };

    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setIsLoading(true);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: content, thread_id: threadId.current }),
      });

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        for (const line of decoder.decode(value).split('\n')) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6);
          if (raw === '[DONE]') break;

          try {
            const event = JSON.parse(raw);
            if (event.type === 'token') {
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? { ...m, content: m.content + event.content } : m)
              );
            } else if (event.type === 'sources') {
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? { ...m, sources: event.content } : m)
              );
            }
          } catch { /* malformed chunk, skip */ }
        }
      }
    } catch {
      setMessages(prev =>
        prev.map(m => m.id === assistantId ? { ...m, content: 'Something went wrong. Please try again.' } : m)
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    threadId.current = uuidv4();
  }, []);

  return { messages, isLoading, sendMessage, clearMessages };
}
