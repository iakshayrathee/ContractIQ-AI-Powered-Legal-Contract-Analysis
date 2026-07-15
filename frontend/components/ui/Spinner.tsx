export function Spinner({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const sizes = { sm: "w-4 h-4 border-[1.5px]", md: "w-5 h-5 border-2", lg: "w-7 h-7 border-2" };
  return (
    <span
      className={`${sizes[size]} border-border border-t-gold rounded-full animate-spin inline-block`}
    />
  );
}
