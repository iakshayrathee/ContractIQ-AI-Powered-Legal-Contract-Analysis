import { useState } from "react";
import type { ChunkItem } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";

interface Props {
  chunk: ChunkItem | null;
}

export default function ChunkDetailPanel({ chunk }: Props) {
  const [imageZoom, setImageZoom] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  if (!chunk) {
    return (
      <div className="flex-1 border-l border-subtle flex items-center justify-center bg-surface">
        <p className="text-sm text-muted">Select a chunk to inspect</p>
      </div>
    );
  }

  const copyToClipboard = () => {
    navigator.clipboard.writeText(chunk.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex-1 border-l border-subtle flex flex-col bg-surface overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-subtle shrink-0">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-white">Detail Inspector</h2>
          <div className="flex gap-1 ml-auto">
            {chunk.content_types.map((t) => (
              <Badge key={t} type={t} />
            ))}
          </div>
        </div>
        <p className="text-[10px] text-muted mt-1 font-mono">{chunk.chunk_id}</p>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">
        {/* Rich metadata grid */}
        <section>
          <h3 className="text-xs font-medium text-muted uppercase tracking-wider mb-3">
            Metadata
          </h3>
          <div className="grid grid-cols-2 gap-3 bg-card border border-subtle rounded-lg p-4">
            {chunk.page_number != null && (
              <div>
                <div className="text-[10px] text-muted uppercase tracking-wide mb-1">Page Number</div>
                <div className="text-sm text-white font-medium">{chunk.page_number}</div>
              </div>
            )}
            {chunk.chunk_index != null && (
              <div>
                <div className="text-[10px] text-muted uppercase tracking-wide mb-1">Chunk Index</div>
                <div className="text-sm text-white font-medium">{chunk.chunk_index}</div>
              </div>
            )}
            {chunk.clause_type && (
              <div>
                <div className="text-[10px] text-muted uppercase tracking-wide mb-1">Clause Type</div>
                <div className="text-sm text-accent font-medium capitalize">{chunk.clause_type.replace(/_/g, " ")}</div>
              </div>
            )}
            {chunk.section_reference && (
              <div>
                <div className="text-[10px] text-muted uppercase tracking-wide mb-1">Section</div>
                <div className="text-sm text-white font-medium">{chunk.section_reference}</div>
              </div>
            )}
            {chunk.source_file && (
              <div className="col-span-2">
                <div className="text-[10px] text-muted uppercase tracking-wide mb-1">Source File</div>
                <div className="text-sm text-white font-medium truncate" title={chunk.source_file}>
                  {chunk.source_file}
                </div>
              </div>
            )}
            {chunk.chunk_type && (
              <div>
                <div className="text-[10px] text-muted uppercase tracking-wide mb-1">Chunk Type</div>
                <div className="text-sm text-white font-medium capitalize">{chunk.chunk_type.replace(/_/g, " ")}</div>
              </div>
            )}
            {chunk.image_dimensions && (
              <div>
                <div className="text-[10px] text-muted uppercase tracking-wide mb-1">Dimensions</div>
                <div className="text-sm text-white font-medium font-mono">{chunk.image_dimensions}</div>
              </div>
            )}
          </div>
        </section>

        {/* Enhanced content */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-medium text-muted uppercase tracking-wider">
              Search-Optimized Summary
            </h3>
            <button
              onClick={copyToClipboard}
              className="text-xs text-muted hover:text-white transition-colors flex items-center gap-1.5 px-2 py-1 rounded hover:bg-card/50"
              title="Copy to clipboard"
            >
              {copied ? (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Copied!
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                  Copy
                </>
              )}
            </button>
          </div>
          <div className="bg-card border border-subtle rounded-lg px-4 py-3 text-sm text-white leading-relaxed whitespace-pre-wrap">
            {chunk.content}
          </div>
        </section>

        {/* Raw text */}
        {chunk.raw_text !== chunk.content && (
          <section>
            <h3 className="text-xs font-medium text-muted uppercase tracking-wider mb-2">
              Raw Text
            </h3>
            <div className="bg-card border border-subtle rounded-lg px-4 py-3 text-sm text-muted leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">
              {chunk.raw_text}
            </div>
          </section>
        )}

        {/* Tables with enhanced styling */}
        {chunk.tables_html.length > 0 && (
          <section>
            <h3 className="text-xs font-medium text-muted uppercase tracking-wider mb-2">
              Tables ({chunk.tables_html.length})
            </h3>
            {chunk.tables_html.map((html, i) => (
              <div
                key={i}
                className="bg-card border border-subtle rounded-lg px-3 py-3 mb-3 overflow-x-auto text-xs text-white
                  [&_table]:w-full [&_table]:border-collapse
                  [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:font-semibold [&_th]:bg-accent/10 [&_th]:text-accent [&_th]:border [&_th]:border-subtle
                  [&_td]:px-3 [&_td]:py-2 [&_td]:border [&_td]:border-subtle
                  [&_tbody_tr]:transition-colors [&_tbody_tr:hover]:bg-subtle/30"
                dangerouslySetInnerHTML={{ __html: html }}
              />
            ))}
          </section>
        )}

        {/* Images with zoom functionality */}
        {chunk.images_base64.length > 0 && (
          <section>
            <h3 className="text-xs font-medium text-muted uppercase tracking-wider mb-2">
              Images ({chunk.images_base64.length})
            </h3>
            <div className="space-y-3">
              {chunk.images_base64.map((b64, i) => {
                const src = `data:image/jpeg;base64,${b64}`;
                return (
                  <div key={i} className="relative group">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={src}
                      alt={`Chunk image ${i + 1}`}
                      className="rounded-lg border border-subtle w-full object-contain cursor-zoom-in max-h-80 transition-all group-hover:border-accent/50"
                      onClick={() => setImageZoom(src)}
                    />
                    <div className="absolute top-2 right-2 bg-black/60 text-white text-[10px] px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity">
                      Click to zoom
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}
      </div>

      {/* Image zoom lightbox */}
      {imageZoom && (
        <div
          className="fixed inset-0 bg-black/90 z-50 flex items-center justify-center p-8"
          onClick={() => setImageZoom(null)}
        >
          <button
            className="absolute top-4 right-4 text-white hover:text-accent transition-colors"
            onClick={() => setImageZoom(null)}
          >
            <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={imageZoom}
            alt="Zoomed image"
            className="max-w-full max-h-full object-contain rounded-lg shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
}
