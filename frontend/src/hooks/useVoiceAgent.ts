import { useCallback, useEffect, useRef, useState } from "react";

import type { ChatResponse } from "@/types/api";

export type VoiceState = "idle" | "listening" | "transcribing" | "processing" | "speaking" | "error";

type VoiceAudio = {
  data: string;
  mimeType: string;
};

type VoiceStreamMessage =
  | { type: "state"; state: VoiceState }
  | { type: "transcript"; text: string; final: boolean }
  | { type: "response"; data: ChatResponse }
  | { type: "speech"; text: string }
  | { type: "audio"; mime: string; data: string }
  | { type: "tts_complete" }
  | { type: "error"; message: string };

interface UseVoiceAgentOptions {
  sessionId: string;
  onResponse: (response: ChatResponse) => void;
  onTranscript?: (text: string) => void;
}

function buildVoiceStreamUrl(sessionId: string) {
  const url = new URL("/voice/stream", window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("session_id", sessionId);
  return url.toString();
}

function playSpeechFallback(text: string) {
  if (typeof window === "undefined" || !window.speechSynthesis) {
    return;
  }

  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1;
  utterance.pitch = 1;
  window.speechSynthesis.speak(utterance);
}

export function useVoiceAgent({ sessionId, onResponse, onTranscript }: UseVoiceAgentOptions) {
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [partialTranscript, setPartialTranscript] = useState("");
  const [spokenAudio, setSpokenAudio] = useState<VoiceAudio | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const wsReadyRef = useRef<Promise<WebSocket> | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const isRecordingRef = useRef(false);
  const pendingSpeechTextRef = useRef<string>("");

  const clearSpokenAudio = useCallback(() => {
    setSpokenAudio(null);
  }, []);

  const resetSpeechState = useCallback(() => {
    pendingSpeechTextRef.current = "";
    setPartialTranscript("");
    clearSpokenAudio();
  }, [clearSpokenAudio]);

  const connect = useCallback(async () => {
    if (!sessionId) {
      throw new Error("No active session available.");
    }

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      return wsRef.current;
    }

    if (wsReadyRef.current) {
      return wsReadyRef.current;
    }

    const websocket = new WebSocket(buildVoiceStreamUrl(sessionId));
    websocket.binaryType = "arraybuffer";

    websocket.onopen = () => setIsConnected(true);
    websocket.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;
      wsReadyRef.current = null;
    };
    websocket.onerror = () => {
      setIsConnected(false);
      setVoiceState("error");
      setError("Voice connection failed.");
    };

    websocket.onmessage = (event) => {
      let message: VoiceStreamMessage;
      try {
        message = JSON.parse(event.data as string) as VoiceStreamMessage;
      } catch {
        return;
      }

      if (message.type === "state") {
        setVoiceState(message.state);
        if (message.state === "idle") {
          if (pendingSpeechTextRef.current) {
            playSpeechFallback(pendingSpeechTextRef.current);
          }
          pendingSpeechTextRef.current = "";
        }
        return;
      }

      if (message.type === "transcript") {
        setPartialTranscript(message.text);
        onTranscript?.(message.text);
        return;
      }

      if (message.type === "response") {
        onResponse(message.data);
        return;
      }

      if (message.type === "speech") {
        pendingSpeechTextRef.current = message.text;
        return;
      }

      if (message.type === "audio") {
        pendingSpeechTextRef.current = "";
        setSpokenAudio({ data: message.data, mimeType: message.mime || "audio/mpeg" });
        return;
      }

      if (message.type === "error") {
        setError(message.message);
        setVoiceState("error");
        return;
      }

      if (message.type === "tts_complete") {
        setVoiceState("idle");
      }
    };

    wsRef.current = websocket;
    wsReadyRef.current = new Promise<WebSocket>((resolve, reject) => {
      websocket.onopen = () => {
        setIsConnected(true);
        wsReadyRef.current = null;
        resolve(websocket);
      };
      websocket.onerror = () => {
        setIsConnected(false);
        setVoiceState("error");
        const message = new Error("Voice connection failed.");
        setError(message.message);
        reject(message);
      };
    });

    return wsReadyRef.current;
  }, [clearSpokenAudio, onResponse, onTranscript, sessionId, spokenAudio]);

  const stopListening = useCallback(() => {
    if (mediaRecorderRef.current && isRecordingRef.current) {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // Ignore stop race conditions.
      }
    }

    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    isRecordingRef.current = false;
  }, []);

  const startListening = useCallback(async () => {
    if (isRecordingRef.current) {
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setVoiceState("error");
      setError("Voice input is not supported in this browser.");
      return;
    }

    try {
      setError(null);
      resetSpeechState();
      const websocket = await connect();

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      mediaStreamRef.current = stream;

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : "";

      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      recorder.ondataavailable = async (event) => {
        if (!event.data.size || websocket.readyState !== WebSocket.OPEN) {
          return;
        }

        const buffer = await event.data.arrayBuffer();
        websocket.send(buffer);
      };

      recorder.onstop = () => {
        if (websocket.readyState === WebSocket.OPEN) {
          websocket.send(JSON.stringify({ type: "stop", filename: "voice.webm" }));
        }
      };

      recorder.start(250);
      mediaRecorderRef.current = recorder;
      isRecordingRef.current = true;
      setVoiceState("listening");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to start voice capture.";
      setVoiceState("error");
      setError(message);
      stopListening();
    }
  }, [connect, resetSpeechState, stopListening]);

  const toggleListening = useCallback(() => {
    if (isRecordingRef.current) {
      stopListening();
      setVoiceState("transcribing");
      return;
    }

    void startListening();
  }, [startListening, stopListening]);

  useEffect(() => {
    return () => {
      stopListening();
      wsRef.current?.close();
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, [stopListening]);

  return {
    voiceState,
    isConnected,
    error,
    partialTranscript,
    spokenAudio,
    clearSpokenAudio,
    toggleListening,
    stopListening,
    isListening: isRecordingRef.current,
  };
}