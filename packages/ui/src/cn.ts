import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge class names, letting a caller's utility win over a component default.
 *
 * Without the tailwind-merge pass, `<Button className="px-8">` would emit both
 * `px-4` and `px-8` and the winner would depend on stylesheet order.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
