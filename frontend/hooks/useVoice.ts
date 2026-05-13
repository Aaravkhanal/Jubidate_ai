import { useState, useEffect, useCallback, useRef } from "react";

export type VoiceSettings = {
  enabled: boolean;
  voiceURI: string | null;
  playbackSpeed: number;
  autoPlay: boolean;
  micSensitivity: number;
  provider: "browser" | "google";
  googleVoice: string;
};

const defaultSettings: VoiceSettings = {
  enabled: false,
  voiceURI: null,
  playbackSpeed: 1.0,
  autoPlay: true,
  micSensitivity: 50,
  provider: "browser",
  googleVoice: "en-US-Journey-F",
};

export function useVoiceSettings() {
  const [settings, setSettings] = useState<VoiceSettings>(defaultSettings);
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("jubidate-voice-settings");
      if (saved) {
        setSettings({ ...defaultSettings, ...JSON.parse(saved) });
      }
    } catch {}
    setIsLoaded(true);
  }, []);

  const updateSettings = useCallback((updates: Partial<VoiceSettings>) => {
    setSettings((current) => {
      const next = { ...current, ...updates };
      localStorage.setItem("jubidate-voice-settings", JSON.stringify(next));
      return next;
    });
  }, []);

  return { settings, updateSettings, isLoaded };
}

export function useVoiceSynthesis(settings: VoiceSettings) {
  const [availableVoices, setAvailableVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  
  useEffect(() => {
    const loadVoices = () => {
      const voices = window.speechSynthesis.getVoices();
      if (voices.length > 0) {
        setAvailableVoices(voices);
      }
    };
    
    window.speechSynthesis.onvoiceschanged = loadVoices;
    loadVoices();
    
    return () => {
      window.speechSynthesis.onvoiceschanged = null;
    };
  }, []);

  const speakGoogle = useCallback(async (text: string) => {
    try {
      setIsSpeaking(true);
      const res = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice: settings.googleVoice }),
      });
      if (!res.ok) throw new Error('TTS Failed');
      const data = await res.json();
      
      const audio = new Audio(`data:audio/mp3;base64,${data.audioContent}`);
      audio.playbackRate = settings.playbackSpeed;
      audioRef.current = audio;
      
      audio.onended = () => {
        setIsSpeaking(false);
        setIsPaused(false);
      };
      audio.onerror = () => {
        setIsSpeaking(false);
        setIsPaused(false);
      };
      
      await audio.play();
    } catch (e) {
      console.error('Google TTS error:', e);
      setIsSpeaking(false);
    }
  }, [settings.googleVoice, settings.playbackSpeed]);

  const speak = useCallback((text: string) => {
    if (!settings.enabled) return;
    
    if (settings.provider === "google") {
        speakGoogle(text);
        return;
    }

    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel(); // Stop current speech
    
    const utterance = new SpeechSynthesisUtterance(text);
    if (settings.voiceURI) {
      const voice = availableVoices.find(v => v.voiceURI === settings.voiceURI);
      if (voice) utterance.voice = voice;
    } else if (availableVoices.length > 0) {
      // Pick a good default voice if possible
      const defaultVoice = availableVoices.find(v => v.lang.startsWith("en") && v.name.includes("Google")) || availableVoices[0];
      if (defaultVoice) utterance.voice = defaultVoice;
    }
    
    utterance.rate = settings.playbackSpeed;
    
    utterance.onstart = () => {
      setIsSpeaking(true);
      setIsPaused(false);
    };
    
    utterance.onend = () => {
      setIsSpeaking(false);
      setIsPaused(false);
    };
    
    utterance.onerror = () => {
      setIsSpeaking(false);
      setIsPaused(false);
    };
    
    window.speechSynthesis.speak(utterance);
  }, [settings, availableVoices, speakGoogle]);

  const pause = useCallback(() => {
    if (settings.provider === "google") {
       if (audioRef.current) {
           audioRef.current.pause();
           setIsPaused(true);
       }
    } else {
        window.speechSynthesis.pause();
        setIsPaused(true);
    }
  }, [settings.provider]);

  const resume = useCallback(() => {
    if (settings.provider === "google") {
        if (audioRef.current) {
            audioRef.current.play();
            setIsPaused(false);
        }
    } else {
        window.speechSynthesis.resume();
        setIsPaused(false);
    }
  }, [settings.provider]);

  const stop = useCallback(() => {
    if (settings.provider === "google") {
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current.currentTime = 0;
            setIsSpeaking(false);
            setIsPaused(false);
        }
    } else {
        window.speechSynthesis.cancel();
        setIsSpeaking(false);
        setIsPaused(false);
    }
  }, [settings.provider]);

  return { availableVoices, speak, pause, resume, stop, isSpeaking, isPaused };
}

export function useSpeechRecognition(provider: "browser" | "google" = "browser") {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const recognitionRef = useRef<any>(null);
  
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    if (provider === "browser") {
        const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        if (SpeechRecognition) {
          recognitionRef.current = new SpeechRecognition();
          recognitionRef.current.continuous = true;
          recognitionRef.current.interimResults = true;
          
          recognitionRef.current.onstart = () => {
            setIsListening(true);
          };
          
          recognitionRef.current.onend = () => {
            setIsListening(false);
          };
        }
    }
  }, [provider]);

  const startListeningBrowser = useCallback((onResult: (text: string, isFinal: boolean) => void) => {
    if (!recognitionRef.current) return;
    
    setTranscript("");
    recognitionRef.current.onresult = (event: any) => {
      let currentTranscript = "";
      let isFinal = false;
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          isFinal = true;
        }
        currentTranscript += event.results[i][0].transcript;
      }
      setTranscript(currentTranscript);
      onResult(currentTranscript, isFinal);
    };
    
    try {
      recognitionRef.current.start();
    } catch (e) {
      // Already started
    }
  }, []);

  const stopListeningBrowser = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
  }, []);

  const startListeningGoogle = useCallback(async (onResult: (text: string, isFinal: boolean) => void) => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm;codecs=opus' });
        const reader = new FileReader();
        reader.readAsDataURL(audioBlob);
        reader.onloadend = async () => {
            const base64Audio = (reader.result as string).split(',')[1];
            try {
                const res = await fetch('/api/stt', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ audioContent: base64Audio }),
                });
                if (res.ok) {
                    const data = await res.json();
                    if (data.transcript) {
                        setTranscript(data.transcript);
                        onResult(data.transcript, true);
                    }
                }
            } catch (e) {
                console.error("STT Error", e);
            }
        };
      };

      mediaRecorder.start();
      setIsListening(true);
    } catch (e) {
        console.error("Microphone error", e);
    }
  }, []);

  const stopListeningGoogle = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
        mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
    }
    setIsListening(false);
  }, []);

  const startListening = useCallback((onResult: (text: string, isFinal: boolean) => void) => {
    if (provider === "google") {
        startListeningGoogle(onResult);
    } else {
        startListeningBrowser(onResult);
    }
  }, [provider, startListeningBrowser, startListeningGoogle]);

  const stopListening = useCallback(() => {
    if (provider === "google") {
        stopListeningGoogle();
    } else {
        stopListeningBrowser();
    }
  }, [provider, stopListeningBrowser, stopListeningGoogle]);

  return { isListening, transcript, startListening, stopListening, isSupported: provider === "google" || !!recognitionRef.current };
}
