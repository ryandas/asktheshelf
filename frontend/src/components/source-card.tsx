import type { Source } from '@/hooks/use-chat-stream';

export function SourceCard({ source }: { source: Source }) {
  return (
    <details className="mt-2 rounded-lg border border-zinc-200 dark:border-zinc-700 text-sm">
      <summary className="cursor-pointer px-3 py-2 font-medium text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 list-none flex items-center gap-2">
        <span>📖</span>
        <span>{source.book}</span>
      </summary>
      <p className="px-3 py-2 text-zinc-500 dark:text-zinc-400 border-t border-zinc-100 dark:border-zinc-800 whitespace-pre-wrap text-xs leading-relaxed">
        {source.excerpt}
      </p>
    </details>
  );
}
