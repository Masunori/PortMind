import type { ButtonHTMLAttributes, ReactNode } from "react";

interface LoadingButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    pending?: boolean;
    pendingLabel?: ReactNode;
}

export default function LoadingButton({
    pending = false,
    pendingLabel,
    disabled,
    children,
    className = "",
    ...props
}: LoadingButtonProps) {
    return (
        <button
            {...props}
            disabled={disabled || pending}
            aria-busy={pending}
            className={`inline-flex items-center justify-center gap-2 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 ${pending ? "cursor-wait" : ""} ${className}`}
        >
            {pending && (
                <span
                    aria-hidden="true"
                    className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-current border-r-transparent"
                />
            )}
            <span>{pending ? (pendingLabel ?? children) : children}</span>
        </button>
    );
}
