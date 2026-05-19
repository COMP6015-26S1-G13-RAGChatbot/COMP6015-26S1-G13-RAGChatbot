import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { parseSourceString } from '@/lib/utils';

export function MessageItem({ message }: { message: any }) {
  const isAssistant = message.role === "assistant";

  return (
    <div className={`flex ${isAssistant ? "justify-start" : "justify-end"} mb-6`}>
      <div className={`max-w-[85%] rounded-2xl px-5 py-4 ${
        isAssistant ? "bg-white shadow-sm border border-slate-200" : "bg-ieee-blue text-white"
      }`}>
        <div className={`prose prose-sm max-w-none ${isAssistant ? "text-slate-800" : "text-white"}`}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {message.content}
          </ReactMarkdown>
        </div>

        {isAssistant && message.sources && message.sources.length > 0 && (
          <div className="mt-4 pt-4 border-t border-slate-100">
            <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">Sources</p>
            <div className="flex flex-wrap gap-2">
              {message.sources.map((sourceStr: string, idx: number) => {
                const { type, docName, page } = parseSourceString(sourceStr, idx);
                return (
                  <button
                    key={idx}
                    className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] font-medium transition-colors ${
                      type === "LEGAL" 
                        ? "bg-purple-50 text-purple-600 hover:bg-purple-100" 
                        : "bg-blue-50 text-blue-600 hover:bg-blue-100"
                    }`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${type === "LEGAL" ? "bg-purple-500" : "bg-blue-500"}`} />
                    {docName} (p.{page})
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}