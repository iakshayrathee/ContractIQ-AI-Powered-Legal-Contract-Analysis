import type { ChunkItem } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";

interface Props {
  chunk: ChunkItem;
  selected: boolean;
  onClick: () => void;
}

// Type-specific icons and colors
const TYPE_CONFIG = {
  text: { color: "border-l-blue-500", icon: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z", iconColor: "text-blue-400" },
  table: { color: "border-l-amber-500", icon: "M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z", iconColor: "text-amber-400" },
  image: { color: "border-l-emerald-500", icon: "M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z", iconColor: "text-emerald-400" },
};

export default function ChunkCard({ chunk, selected, onClick }: Props) {
  // Determine primary type for visual styling
  const primaryType = chunk.chunk_type || chunk.content_types[0] || "text";
  const typeKey = primaryType === "image_description" ? "image" : (primaryType as keyof typeof TYPE_CONFIG);
  const config = TYPE_CONFIG[typeKey] || TYPE_CONFIG.text;

  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-4 py-3 border-b border-subtle transition-all
        ${selected ? `bg-accent/10 border-l-2 ${config.color}` : "hover:bg-card/50 border-l-2 border-l-transparent"}`}
    >
      {/* Header row: icon, badges, page number */}
      <div className="flex items-center gap-1.5 mb-1.5">
        <svg className={`w-3.5 h-3.5 ${config.iconColor} shrink-0`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d={config.icon} />
        </svg>
        {chunk.content_types.map((t) => (
          <Badge key={t} type={t} small />
        ))}
        {chunk.page_number != null && (
          <span className="ml-auto text-[10px] text-muted font-mono bg-subtle/50 px-1.5 py-0.5 rounded">
            p.{chunk.page_number}
          </span>
        )}
      </div>

      {/* Metadata row: clause type, source file */}
      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
        {chunk.clause_type && (
          <span className="text-[10px] text-accent/80 bg-accent/10 px-1.5 py-0.5 rounded font-medium">
            {chunk.clause_type}
          </span>
        )}
        {chunk.source_file && (
          <span className="text-[10px] text-muted/70 truncate max-w-[150px]" title={chunk.source_file}>
            {chunk.source_file}
          </span>
        )}
      </div>

      {/* Content preview */}
      <p className="text-xs text-muted line-clamp-3 leading-relaxed">
        {chunk.content.slice(0, 200)}
        {chunk.content.length > 200 && "…"}
      </p>

      {/* Footer: chunk ID */}
      <div className="mt-1.5 pt-1.5 border-t border-subtle/50">
        <span className="text-[9px] text-muted/50 font-mono">
          #{chunk.chunk_id.slice(0, 8)}
        </span>
      </div>
    </button>
  );
}
