'use client';
import { useState, useRef, useEffect } from 'react';
import { useChatStream } from '@/hooks/use-chat-stream';
import { MessageBubble } from './message-bubble';

const SUGGESTED = [
  'How does Spark handle data partitioning?',
  'What is the difference between ETL and ELT?',
  'Explain columnar vs row-based storage.',
  'What makes a good data warehouse schema?',
];

export function ChatWindow() {
  const { messages, isLoading, sendMessage, clearMessages } = useChatStream();
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const submit = (content: string) => {
    const trimmed = content.trim();
    if (!trimmed || isLoading) return;
    setInput('');
    sendMessage(trimmed);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submit(input);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit(input);
    }
  };

  return (
    <div className="flex flex-col h-screen w-full">
      {/* Header */}
      <header className="shrink-0 border-b border-zinc-800 px-8 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-green-500 font-bold text-sm">▶ book-chat</span>
          <span className="text-zinc-600 text-xs hidden sm:inline">data engineering &amp; spark knowledge base</span>
        </div>
        {messages.length > 0 && (
          <button
            onClick={clearMessages}
            className="text-xs text-zinc-700 hover:text-zinc-400 transition-colors"
          >
            [clear]
          </button>
        )}
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-8 py-8 space-y-8 min-h-0">
        {messages.length === 0 ? (
          <div className="space-y-8 pt-4">
            <div className="space-y-1">
              <p className="text-zinc-700 text-xs">// suggested queries</p>
            </div>
            <div className="space-y-3">
              {SUGGESTED.map(q => (
                <button
                  key={q}
                  onClick={() => submit(q)}
                  className="block w-full text-left text-sm text-zinc-500 hover:text-green-400 transition-colors group"
                >
                  <span className="text-zinc-700 group-hover:text-green-600 mr-2 transition-colors">$</span>
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) => (
            <MessageBubble
              key={m.id}
              message={m}
              isPending={isLoading && i === messages.length - 1 && m.role === 'assistant' && m.content === ''}
            />
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="shrink-0 border-t border-zinc-800 px-8 py-4 flex items-start gap-3">
        <span className="text-green-500 text-sm mt-0.5 shrink-0 select-none">$</span>
        <textarea
          ref={textareaRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="ask anything..."
          rows={1}
          className="flex-1 bg-transparent text-zinc-200 text-sm placeholder-zinc-700 focus:outline-none resize-none leading-relaxed"
          disabled={isLoading}
        />
        <button
          type="submit"
          disabled={isLoading || !input.trim()}
          className="text-xs text-zinc-700 hover:text-green-500 disabled:opacity-25 disabled:cursor-not-allowed transition-colors shrink-0 mt-0.5"
        >
          [run]
        </button>
      </form>
    </div>
  );
}
