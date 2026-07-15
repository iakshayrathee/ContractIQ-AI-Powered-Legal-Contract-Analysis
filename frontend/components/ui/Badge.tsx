const dotColors: Record<string, string> = {
  text:  "bg-blue-400",
  table: "bg-amber-400",
  image: "bg-emerald-400",
};

const bgColors: Record<string, string> = {
  text:  "bg-blue-950/60 text-blue-300 border-blue-800/40",
  table: "bg-amber-950/60 text-amber-300 border-amber-800/40",
  image: "bg-emerald-950/60 text-emerald-300 border-emerald-800/40",
};

interface BadgeProps {
  type: "text" | "table" | "image" | string;
  small?: boolean;
}

export function Badge({ type, small = false }: BadgeProps) {
  const bg  = bgColors[type]  ?? "bg-card text-white/80 border-border";
  const dot = dotColors[type] ?? "bg-muted";
  return (
    <span
      className={`inline-flex items-center gap-1.5 border rounded-md font-medium capitalize
        ${small ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs"}
        ${bg}`}
    >
      <span className={`inline-block ${small ? "w-1 h-1" : "w-1.5 h-1.5"} rounded-full flex-shrink-0 ${dot}`} />
      {type}
    </span>
  );
}
