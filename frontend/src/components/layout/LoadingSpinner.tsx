interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg";
  label?: string;
}

const SIZES = {
  sm: "h-4 w-4 border-2",
  md: "h-8 w-8 border-2",
  lg: "h-12 w-12 border-[3px]",
};

export default function LoadingSpinner({ size = "md", label }: LoadingSpinnerProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3">
      <div
        className={`${SIZES[size]} animate-spin rounded-full border-border border-t-accent`}
        role="status"
        aria-label={label ?? "Loading"}
      />
      {label && <p className="text-sm text-text-muted">{label}</p>}
    </div>
  );
}
