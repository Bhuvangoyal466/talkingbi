import { Loader2, Mic, MicOff, Volume2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { VoiceState } from "@/hooks/useVoiceAgent";

interface MicButtonProps {
  state: VoiceState;
  onToggle: () => void;
  disabled?: boolean;
}

const STATE_STYLES: Record<VoiceState, { icon: typeof Mic; className: string; label: string }> = {
  idle: { icon: Mic, className: "bg-secondary text-foreground hover:bg-secondary/80", label: "Start voice input" },
  listening: {
    icon: Mic,
    className: "bg-primary text-primary-foreground shadow-lg shadow-primary/25 ring-2 ring-primary/40 animate-pulse",
    label: "Stop voice input",
  },
  transcribing: {
    icon: Loader2,
    className: "bg-amber-500/15 text-amber-300 ring-2 ring-amber-400/20",
    label: "Transcribing voice",
  },
  processing: {
    icon: Loader2,
    className: "bg-amber-500/15 text-amber-300 ring-2 ring-amber-400/20",
    label: "Processing voice query",
  },
  speaking: {
    icon: Volume2,
    className: "bg-emerald-500/15 text-emerald-300 ring-2 ring-emerald-400/20",
    label: "Speaking response",
  },
  error: { icon: MicOff, className: "bg-red-500/15 text-red-300 ring-2 ring-red-400/20", label: "Voice error" },
};

export function MicButton({ state, onToggle, disabled = false }: MicButtonProps) {
  const config = STATE_STYLES[state];
  const Icon = config.icon;

  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled}
      aria-label={config.label}
      title={config.label}
      className={cn(
        "inline-flex h-10 w-10 items-center justify-center rounded-full transition-all duration-200 hover:scale-[1.03] active:scale-95 disabled:cursor-not-allowed disabled:opacity-50",
        config.className,
      )}
    >
      <Icon size={18} className={state === "transcribing" || state === "processing" ? "animate-spin" : ""} />
    </button>
  );
}