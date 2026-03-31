/**
 * WebSocket client for real-time voice streaming to the GClaw backend.
 *
 * Handles:
 * - WebSocket connection with auth token
 * - MediaRecorder for microphone capture (PCM 16-bit 16kHz via AudioContext)
 * - AudioContext for playback of received PCM audio
 * - State management (idle, connecting, listening, processing)
 */

import type { VoiceClientMessage, VoiceServerMessage, VoiceState } from "@/types";

export type VoiceStateCallback = (state: VoiceState) => void;
export type VoiceAudioCallback = (audioData: Float32Array) => void;

export class VoiceClient {
  private ws: WebSocket | null = null;
  private mediaStream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private processorNode: ScriptProcessorNode | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private playbackContext: AudioContext | null = null;
  private state: VoiceState = "idle";
  private onStateChange: VoiceStateCallback;
  private baseUrl: string;
  private getToken: () => Promise<string | null>;

  constructor(
    baseUrl: string,
    getToken: () => Promise<string | null>,
    onStateChange: VoiceStateCallback,
  ) {
    this.baseUrl = baseUrl.replace(/^http/, "ws").replace(/\/+$/, "");
    this.getToken = getToken;
    this.onStateChange = onStateChange;
  }

  getState(): VoiceState {
    return this.state;
  }

  private setState(s: VoiceState) {
    this.state = s;
    this.onStateChange(s);
  }

  /** Start voice session: connect WS, open mic, begin streaming. */
  async start(): Promise<void> {
    if (this.state !== "idle") return;
    this.setState("connecting");

    try {
      const token = await this.getToken();
      if (!token) throw new Error("Not authenticated");

      // Open WebSocket
      this.ws = new WebSocket(`${this.baseUrl}/voice?token=${encodeURIComponent(token)}`);
      this.ws.onclose = () => this.stop();
      this.ws.onerror = () => this.setState("error");
      this.ws.onmessage = (event) => this.handleMessage(event);

      await new Promise<void>((resolve, reject) => {
        if (!this.ws) return reject(new Error("No WS"));
        this.ws.onopen = () => resolve();
        this.ws.onerror = () => reject(new Error("WS connection failed"));
      });

      // Open microphone
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true },
      });

      // Set up AudioContext to capture PCM data
      this.audioContext = new AudioContext({ sampleRate: 16000 });
      this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream);
      this.processorNode = this.audioContext.createScriptProcessor(4096, 1, 1);

      this.processorNode.onaudioprocess = (event) => {
        if (this.state !== "listening" || !this.ws) return;
        const float32 = event.inputBuffer.getChannelData(0);
        const int16 = this.float32ToInt16(float32);
        const base64 = this.arrayBufferToBase64(int16.buffer);
        const msg: VoiceClientMessage = { type: "audio", data: base64 };
        this.ws.send(JSON.stringify(msg));
      };

      this.sourceNode.connect(this.processorNode);
      this.processorNode.connect(this.audioContext.destination);

      // Set up playback context
      this.playbackContext = new AudioContext({ sampleRate: 24000 });

      this.setState("listening");
    } catch (err) {
      console.error("Voice start failed:", err);
      this.setState("error");
      this.cleanup();
    }
  }

  /** Stop voice session and clean up all resources. */
  stop(): void {
    if (this.state === "idle") return;
    this.cleanup();
    this.setState("idle");
  }

  private cleanup(): void {
    if (this.processorNode) {
      this.processorNode.disconnect();
      this.processorNode = null;
    }
    if (this.sourceNode) {
      this.sourceNode.disconnect();
      this.sourceNode = null;
    }
    if (this.audioContext) {
      this.audioContext.close().catch(() => {});
      this.audioContext = null;
    }
    if (this.playbackContext) {
      this.playbackContext.close().catch(() => {});
      this.playbackContext = null;
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((t) => t.stop());
      this.mediaStream = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  private handleMessage(event: MessageEvent): void {
    try {
      const msg: VoiceServerMessage = JSON.parse(event.data as string);
      if (msg.type === "audio" && msg.data) {
        this.setState("processing");
        this.playAudio(msg.data);
      } else if (msg.type === "turn_complete") {
        this.setState("listening");
      } else if (msg.type === "error") {
        console.error("Voice server error:", msg.message);
        this.setState("error");
      }
    } catch (err) {
      console.error("Failed to parse voice message:", err);
    }
  }

  private playAudio(base64Data: string): void {
    if (!this.playbackContext) return;
    const raw = atob(base64Data);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);

    // Assume 16-bit PCM at 24kHz from Gemini
    const int16 = new Int16Array(bytes.buffer);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768;

    const buffer = this.playbackContext.createBuffer(1, float32.length, 24000);
    buffer.getChannelData(0).set(float32);
    const source = this.playbackContext.createBufferSource();
    source.buffer = buffer;
    source.connect(this.playbackContext.destination);
    source.start();
  }

  private float32ToInt16(float32: Float32Array): Int16Array {
    const int16 = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
      const s = Math.max(-1, Math.min(1, float32[i]));
      int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return int16;
  }

  private arrayBufferToBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
    return btoa(binary);
  }
}
