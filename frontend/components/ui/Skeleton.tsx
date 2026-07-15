interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className = "" }: SkeletonProps) {
  return (
    <div className={`relative overflow-hidden rounded-lg bg-card ${className}`}>
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_1.8s_infinite] bg-gradient-to-r from-transparent via-gold/[0.05] to-transparent" />
    </div>
  );
}

/** A skeleton mimicking a project card */
export function ProjectCardSkeleton() {
  return (
    <div className="bg-card border border-border rounded-2xl overflow-hidden">
      <div className="h-0.5 bg-gradient-gold opacity-30" />
      <div className="p-5 pl-6 space-y-3">
        <div className="flex items-start justify-between">
          <Skeleton className="w-10 h-10 rounded-xl" />
          <Skeleton className="w-14 h-5 rounded-full" />
        </div>
        <Skeleton className="w-3/4 h-4" />
        <Skeleton className="w-full h-3" />
        <Skeleton className="w-full h-3" />
        <Skeleton className="w-1/3 h-3 mt-2" />
      </div>
    </div>
  );
}
