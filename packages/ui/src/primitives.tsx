"use client";

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { AlertCircle, Inbox, Loader2, Lock, ServerCrash } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "./cn";

/**
 * The interface vocabulary (§86): one button, one card, one field, one table,
 * used everywhere. Anything that needs to look different is a variant here,
 * not a bespoke set of classes at the call site.
 *
 * The state components at the bottom exist because §85 requires every screen
 * to have a loading, empty, error and permission-denied state. Making them
 * components rather than a convention is what stops screens shipping with only
 * the happy path.
 */

// ── Button ──────────────────────────────────────────────────────────────────

const buttonStyles = cva(
  cn(
    "inline-flex items-center justify-center gap-2 rounded-card",
    "text-sm font-medium whitespace-nowrap transition-colors",
    "disabled:pointer-events-none disabled:opacity-50",
    "[&_svg]:size-4 [&_svg]:shrink-0",
  ),
  {
    variants: {
      variant: {
        primary: "bg-navy-800 text-white hover:bg-navy-700 active:bg-navy-900",
        accent: "bg-burnt text-white hover:bg-[#b9591a] active:bg-[#a24e17]",
        outline:
          "border border-navy-100 bg-white text-navy-800 hover:border-navy-300 hover:bg-sand-50",
        ghost: "text-navy-800 hover:bg-navy-100/60",
        danger: "bg-low text-white hover:bg-[#98201a]",
        link: "text-navy-700 underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-8 px-3 text-[0.8125rem]",
        md: "h-9 px-4",
        lg: "h-11 px-6 text-base",
        icon: "size-9",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export type ButtonProps = ComponentProps<"button"> &
  VariantProps<typeof buttonStyles> & {
    asChild?: boolean;
    /** Shows a spinner and disables the button. Label stays, so width is stable. */
    busy?: boolean;
  };

export function Button({
  className,
  variant,
  size,
  asChild,
  busy,
  disabled,
  children,
  ...props
}: ButtonProps) {
  const styles = cn(buttonStyles({ variant, size }), className);

  // Slot requires EXACTLY one element child, so the asChild path cannot wrap
  // the caller's element alongside a spinner. That is fine in practice: a
  // Button rendered as a link never has a pending state to report.
  if (asChild) {
    return (
      <Slot className={styles} {...props}>
        {children}
      </Slot>
    );
  }

  return (
    <button className={styles} disabled={disabled || busy} {...props}>
      {busy ? <Loader2 className="animate-spin" aria-hidden /> : null}
      {children}
    </button>
  );
}

// ── Surfaces ────────────────────────────────────────────────────────────────

export function Card({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "rounded-card border border-sand-200 bg-white shadow-panel",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({
  title,
  description,
  action,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-4 border-b border-sand-200 px-5 py-4",
        className,
      )}
    >
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-navy-900">{title}</h2>
        {description ? (
          <p className="mt-0.5 text-sm text-sand-500">{description}</p>
        ) : null}
      </div>
      {action}
    </div>
  );
}

/**
 * A dashboard counter (§14, §20, §27, §31).
 *
 * The number leads; the label sits under it. `hint` is for the one line of
 * context that stops a bare figure being ambiguous.
 */
export function StatCard({
  label,
  value,
  hint,
  tone = "default",
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "attention" | "good";
  icon?: ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-card border bg-white px-4 py-3.5 shadow-panel",
        tone === "attention" && "border-warm",
        tone === "good" && "border-high/30",
        tone === "default" && "border-sand-200",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="eyebrow">{label}</p>
        {icon ? <span className="text-sand-300">{icon}</span> : null}
      </div>
      <p className="id mt-2 text-2xl font-semibold tracking-tight text-navy-900">
        {value}
      </p>
      {hint ? <p className="mt-1 text-xs text-sand-500">{hint}</p> : null}
    </div>
  );
}

// ── Form fields ─────────────────────────────────────────────────────────────

export function Field({
  label,
  hint,
  error,
  required,
  children,
  className,
}: {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("block", className)}>
      <span className="mb-1.5 flex items-baseline gap-1.5 text-sm font-medium text-navy-900">
        {label}
        {required ? (
          <span className="text-burnt" aria-label="required">
            *
          </span>
        ) : null}
      </span>
      {children}
      {error ? (
        <span className="mt-1.5 flex items-center gap-1.5 text-xs text-low">
          <AlertCircle className="size-3.5 shrink-0" aria-hidden />
          {error}
        </span>
      ) : hint ? (
        <span className="mt-1.5 block text-xs text-sand-500">{hint}</span>
      ) : null}
    </label>
  );
}

const controlStyles = cn(
  "w-full rounded-card border border-sand-200 bg-white px-3 py-2",
  "text-sm text-ink placeholder:text-sand-300",
  "focus:border-navy-600 focus:outline-none focus-visible:outline-2",
  "disabled:bg-sand-50 disabled:text-sand-500",
);

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(controlStyles, className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(controlStyles, "min-h-24 resize-y", className)} {...props} />;
}

export function Select({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <select className={cn(controlStyles, "pr-8", className)} {...props}>
      {children}
    </select>
  );
}

// ── Tables ──────────────────────────────────────────────────────────────────

export function Table({ className, ...props }: ComponentProps<"table">) {
  return (
    <div className="overflow-x-auto">
      <table className={cn("w-full border-collapse text-sm", className)} {...props} />
    </div>
  );
}

export function Th({ className, ...props }: ComponentProps<"th">) {
  return (
    <th
      className={cn(
        "border-b border-sand-200 px-3 py-2.5 text-left align-bottom",
        "text-[0.6875rem] font-semibold uppercase tracking-wider text-sand-500",
        className,
      )}
      {...props}
    />
  );
}

export function Td({ className, ...props }: ComponentProps<"td">) {
  return (
    <td className={cn("border-b border-sand-100 px-3 py-2.5 align-middle", className)} {...props} />
  );
}

// ── The four required screen states (§85) ───────────────────────────────────

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div
      className="flex items-center justify-center gap-3 px-6 py-14 text-sm text-sand-500"
      role="status"
    >
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}…
    </div>
  );
}

/** An empty screen is an invitation to act, so it takes an action. */
export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
      <span className="text-sand-300">{icon ?? <Inbox className="size-7" aria-hidden />}</span>
      <div>
        <p className="text-sm font-medium text-navy-900">{title}</p>
        {description ? (
          <p className="mx-auto mt-1 max-w-md text-sm text-sand-500">{description}</p>
        ) : null}
      </div>
      {action}
    </div>
  );
}

/** Says what went wrong and how to fix it — never just "an error occurred". */
export function ErrorState({
  title = "That request did not go through",
  description,
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
      <ServerCrash className="size-7 text-low" aria-hidden />
      <div>
        <p className="text-sm font-medium text-navy-900">{title}</p>
        {description ? (
          <p className="mx-auto mt-1 max-w-md text-sm text-sand-500">{description}</p>
        ) : null}
      </div>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}

/** §36 refused this caller. Distinct from an error and from an empty list. */
export function ForbiddenState({
  description = "Your role does not include this. If you think it should, ask your tehsildar.",
}: {
  description?: string;
}) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
      <Lock className="size-7 text-sand-300" aria-hidden />
      <div>
        <p className="text-sm font-medium text-navy-900">You cannot open this</p>
        <p className="mx-auto mt-1 max-w-md text-sm text-sand-500">{description}</p>
      </div>
    </div>
  );
}
