interface VoiceTranscriptBubbleProps {
  transcript: string;
  visible: boolean;
}

export function VoiceTranscriptBubble({ transcript, visible }: VoiceTranscriptBubbleProps) {
  if (!visible || !transcript) {
    return null;
  }

  return (
    <div className="mb-3 rounded-2xl border border-primary/20 bg-primary/8 px-4 py-3 text-sm text-primary-foreground shadow-sm backdrop-blur-sm">
      <div className="flex items-start gap-3">
        <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-primary animate-pulse" />
        <p className="text-foreground/90 italic leading-relaxed">“{transcript}”</p>
      </div>
    </div>
  );
}