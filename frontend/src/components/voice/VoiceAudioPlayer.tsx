import { useEffect, useMemo, useRef } from "react";

interface VoiceAudioPlayerProps {
  audio: { data: string; mimeType: string } | null;
  onConsumed: () => void;
}

function base64ToObjectUrl(data: string, mimeType: string) {
  const binary = window.atob(data);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  return URL.createObjectURL(new Blob([bytes], { type: mimeType }));
}

export function VoiceAudioPlayer({ audio, onConsumed }: VoiceAudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrl = useMemo(() => {
    if (!audio) {
      return null;
    }
    return base64ToObjectUrl(audio.data, audio.mimeType || "audio/mpeg");
  }, [audio]);

  useEffect(() => {
    const element = audioRef.current;
    if (!element || !objectUrl) {
      return;
    }

    element.src = objectUrl;
    void element.play().catch(() => {
      // Autoplay can fail if the browser requires another gesture.
    });

    const revoke = () => URL.revokeObjectURL(objectUrl);
    element.addEventListener("ended", revoke, { once: true });

    return () => {
      element.removeEventListener("ended", revoke);
      URL.revokeObjectURL(objectUrl);
    };
  }, [objectUrl]);

  return (
    <audio
      ref={audioRef}
      className="hidden"
      onEnded={onConsumed}
      onError={onConsumed}
      preload="auto"
    />
  );
}