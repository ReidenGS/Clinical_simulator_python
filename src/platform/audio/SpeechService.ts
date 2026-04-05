import type { AIConfig } from '../types/app';
import { generateSpeech, type VoiceContext } from './speechSynthesis';

/**
 * SpeechService provides a unified interface for text-to-speech.
 * It handles provider selection, fallback logic, and future extensibility.
 */
export class SpeechService {
  private config: AIConfig;
  private cachedNativeVoiceUri: string | null = null;

  constructor(config: AIConfig) {
    this.config = config;
  }

  /**
   * Generates an audio URL for the given text.
   * Falls back to null if AI generation fails.
   */
  async generateUrl(text: string, context: VoiceContext): Promise<string | null> {
    try {
      return await generateSpeech(text, this.config, context);
    } catch (error) {
      console.error('SpeechService: AI generation failed:', error);
      return null;
    }
  }

  /**
   * Speaks the text directly. 
   * Tries AI generation first, falls back to browser native TTS.
   */
  async speak(text: string, context: VoiceContext): Promise<void> {
    const url = await this.generateUrl(text, context);
    
    if (url) {
      return new Promise((resolve, reject) => {
        const audio = new Audio(url);
        audio.onended = () => { URL.revokeObjectURL(url); resolve(); };
        audio.onerror = (e) => {
          console.warn('SpeechService: Audio playback failed, falling back to native TTS', e);
          this.speakNative(text, context).then(resolve).catch(reject);
        };
        audio.play().catch(err => {
          console.warn('SpeechService: Playback blocked or failed:', err);
          this.speakNative(text, context).then(resolve).catch(reject);
        });
      });
    } else {
      console.log('SpeechService: No AI audio URL, using native TTS fallback');
      return this.speakNative(text, context);
    }
  }

  /**
   * Browser native TTS fallback.
   */
  private speakNative(text: string, context: VoiceContext): Promise<void> {
    return new Promise((resolve) => {
      if (!window.speechSynthesis) {
        console.error('SpeechService: Browser does not support SpeechSynthesis');
        resolve();
        return;
      }

      const speak = () => {
        // Stop any current speech
        window.speechSynthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(text);
        const voices = window.speechSynthesis.getVoices();
        const preferredVoice = this.selectNativeVoice(voices, context);
        if (preferredVoice?.voiceURI) {
          this.cachedNativeVoiceUri = preferredVoice.voiceURI;
          utterance.voice = preferredVoice;
        }

        // Adjust pitch/rate based on age
        if (context.age) {
          if (context.age > 60) {
            utterance.rate = 0.8;
            utterance.pitch = 0.9;
          } else if (context.age < 20) {
            utterance.rate = 1.1;
            utterance.pitch = 1.1;
          }
        }

        utterance.onend = () => resolve();
        utterance.onerror = () => resolve();

        window.speechSynthesis.speak(utterance);
      };

      if (window.speechSynthesis.getVoices().length === 0) {
        window.speechSynthesis.onvoiceschanged = speak;
      } else {
        speak();
      }
    });
  }

  private resolveGender(genderRaw: string | undefined | null): 'female' | 'male' | 'unknown' {
    const g = (genderRaw || '').trim().toLowerCase();
    if (!g) return 'unknown';

    const tokens = g
      .replace(/[^a-z0-9]+/g, ' ')
      .split(/\s+/)
      .filter(Boolean);

    if (tokens.includes('female') || tokens.includes('woman') || tokens.includes('girl') || tokens.includes('f')) {
      return 'female';
    }
    if (tokens.includes('male') || tokens.includes('man') || tokens.includes('boy') || tokens.includes('m')) {
      return 'male';
    }
    if (g.includes('female') || g.includes('woman')) return 'female';
    if (g.includes('male') || g.includes('man')) return 'male';
    return 'unknown';
  }

  private selectNativeVoice(voices: SpeechSynthesisVoice[], context: VoiceContext): SpeechSynthesisVoice | null {
    if (voices.length === 0) return null;

    // Keep the fallback voice stable during a session once selected.
    if (this.cachedNativeVoiceUri) {
      const cached = voices.find((v) => v.voiceURI === this.cachedNativeVoiceUri);
      if (cached) return cached;
    }

    const gender = this.resolveGender(context.gender);
    const preferredHints = gender === 'female'
      ? ['female', 'woman', 'girl', 'samantha', 'victoria']
      : ['male', 'man', 'boy', 'alex', 'daniel'];

    const englishVoices = voices.filter((v) => v.lang.toLowerCase().startsWith('en'));
    const pool = englishVoices.length > 0 ? englishVoices : voices;

    const ranked = [...pool].sort((a, b) => {
      const aName = a.name.toLowerCase();
      const bName = b.name.toLowerCase();

      const aScore = preferredHints.some((hint) => aName.includes(hint)) ? 1 : 0;
      const bScore = preferredHints.some((hint) => bName.includes(hint)) ? 1 : 0;
      if (aScore !== bScore) return bScore - aScore;

      const aIsLocal = a.localService ? 1 : 0;
      const bIsLocal = b.localService ? 1 : 0;
      if (aIsLocal !== bIsLocal) return bIsLocal - aIsLocal;

      return aName.localeCompare(bName);
    });

    return ranked[0] || null;
  }
}
