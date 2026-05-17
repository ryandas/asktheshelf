import ReactMarkdown from 'react-markdown';
import type { Message } from '@/hooks/use-chat-stream';

interface Props {
  message: Message;
  isPending?: boolean;
}

export function MessageBubble({ message, isPending }: Props) {
  if (message.role === 'user') {
    return (
      <div className="text-sm">
        <span className="text-green-500 mr-2 select-none">user@book-chat:~$</span>
        <span className="text-zinc-300">{message.content}</span>
      </div>
    );
  }

  return (
    <div className="text-sm space-y-4 pl-4 border-l-2 border-zinc-800">
      <div className="flex gap-3 items-start">
        <span className="text-green-500 shrink-0 select-none mt-0.5">●</span>
        <div className="min-w-0 flex-1">
          {isPending ? (
            <LoadingSkeleton />
          ) : (
            <div className="text-zinc-300 prose prose-sm prose-invert max-w-none
              [&_p]:text-zinc-300 [&_p]:my-1
              [&_code]:text-green-400 [&_code]:bg-zinc-900 [&_code]:px-1 [&_code]:rounded
              [&_pre]:bg-zinc-900 [&_pre]:border [&_pre]:border-zinc-800 [&_pre]:rounded [&_pre]:p-3
              [&_pre_code]:bg-transparent [&_pre_code]:p-0
              [&_strong]:text-zinc-100
              [&_h1]:text-zinc-100 [&_h2]:text-zinc-100 [&_h3]:text-zinc-200
              [&_ul]:text-zinc-300 [&_li]:my-0.5
              [&_a]:text-indigo-400 [&_a:hover]:text-indigo-300">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )}
        </div>
      </div>

      {message.sources.length > 0 && (
        <div className="pl-6 space-y-1.5">
          {message.sources.map(s => (
            <details key={s.book} className="group">
              <summary className="text-xs text-indigo-500 hover:text-indigo-400 cursor-pointer list-none transition-colors">
                <span className="select-none">[ref] </span>{s.book}
              </summary>
              <p className="mt-1.5 text-xs text-zinc-600 pl-4 border-l border-zinc-800 leading-relaxed">
                {s.excerpt}
              </p>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5 text-zinc-600 text-xs">
        <span>processing</span>
        <span className="[animation:blink_1s_step-end_0s_infinite]">.</span>
        <span className="[animation:blink_1s_step-end_0.33s_infinite]">.</span>
        <span className="[animation:blink_1s_step-end_0.66s_infinite]">.</span>
      </div>
      <div className="space-y-2 animate-pulse">
        <div className="h-2.5 bg-zinc-800 rounded w-3/4" />
        <div className="h-2.5 bg-zinc-800 rounded w-full" />
        <div className="h-2.5 bg-zinc-800 rounded w-5/6" />
      </div>
    </div>
  );
}
