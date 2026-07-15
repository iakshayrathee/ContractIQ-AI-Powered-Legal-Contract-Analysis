"use client";

export default function RAGExplainer() {
  const stages = [
    {
      number: 1,
      title: "Ingest",
      description: "Upload PDFs",
      detail: "Documents are extracted with advanced text parsing",
      icon: "📄",
      color: "from-blue-500/30 to-blue-600/20",
      dotColor: "bg-blue-400",
    },
    {
      number: 2,
      title: "Chunk",
      description: "Split into chunks",
      detail: "Content divided into meaningful semantic chunks",
      icon: "🧩",
      color: "from-purple-500/30 to-purple-600/20",
      dotColor: "bg-purple-400",
    },
    {
      number: 3,
      title: "Embed",
      description: "Generate vectors",
      detail: "Each chunk converted to vector embeddings",
      icon: "🧮",
      color: "from-indigo-500/30 to-indigo-600/20",
      dotColor: "bg-indigo-400",
    },
    {
      number: 4,
      title: "Store",
      description: "Qdrant index",
      detail: "Vectors stored for fast similarity search",
      icon: "💾",
      color: "from-cyan-500/30 to-cyan-600/20",
      dotColor: "bg-cyan-400",
    },
    {
      number: 5,
      title: "Answer",
      description: "Ask questions",
      detail: "Find relevant chunks and generate responses",
      icon: "🔍",
      color: "from-pink-500/30 to-pink-600/20",
      dotColor: "bg-pink-400",
    },
  ];

  return (
    <div className="bg-card border border-subtle rounded-xl p-6">
      <div className="mb-6">
        <h3 className="text-base font-bold text-white">How RAG Works</h3>
        <p className="text-sm text-muted mt-2">
          Retrieval-Augmented Generation combines your documents with AI for accurate answers.
        </p>
      </div>

      <div className="space-y-3">
        {stages.map((stage, idx) => (
          <div key={stage.number}>
            <div
              className={`rounded-lg bg-gradient-to-br ${stage.color} border border-white/10 p-4`}
            >
              <div className="flex items-start gap-4">
                <div className="flex items-center justify-center w-10 h-10 rounded-full bg-white/10 text-lg flex-shrink-0 font-bold">
                  {stage.icon}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs font-bold px-2 py-1 rounded ${stage.dotColor} text-white`}>
                      Step {stage.number}
                    </span>
                  </div>
                  <h4 className="text-sm font-semibold text-white">
                    {stage.title}
                  </h4>
                  <p className="text-xs text-muted mt-1">{stage.detail}</p>
                </div>
              </div>
            </div>
            {idx < stages.length - 1 && (
              <div className="flex justify-center py-2">
                <div className={`w-1 h-4 rounded-full ${stages[idx + 1].dotColor} opacity-40`} />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
