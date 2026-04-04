import { useState, useRef, useCallback } from 'react';
import type { PatientCase, SessionState } from '../types';
import type { Message, AIConfig } from '../../../platform/types';
import { SpeechService } from '../../../platform/audio/SpeechService';
import type { VoiceContext } from '../../../platform/audio/speechSynthesis';

type Decision = {
  type: 'CONTINUE' | 'HINT_NEEDED' | 'RISK_BRANCH' | 'PHASE_ADVANCE' | 'EARLY_END_WARNING' | 'RED_FLAG';
  message?: string;
  data?: Record<string, unknown>;
};

interface UseInterviewSessionReturn {
  messages: Message[];
  sessionState: SessionState | null;
  isLoading: boolean;
  lastDecision: Decision | null;
  startSession: (caseData: PatientCase) => void;
  processTurn: (input: string, config: AIConfig, useNewOrchestration: boolean) => Promise<void>;
  evaluateSubmission: () => Decision | null;
  resetSession: () => void;
}

function toVoiceContext(caseData: PatientCase): VoiceContext {
  return {
    gender: caseData.gender,
    age: caseData.age,
    personality: caseData.personality,
    speechPatterns: caseData.speechPatterns,
    condition: caseData.correctDiagnosis,
  };
}

async function processTurnViaBackend(
  caseData: PatientCase,
  history: Message[],
  studentInput: string,
  sessionState: SessionState | null,
  config: AIConfig,
) {
  const response = await fetch('/api/interview/respond', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      caseData,
      history,
      studentInput,
      sessionState,
      config,
    }),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json() as Promise<{
    patientMessage: Message;
    extraction: unknown;
    sessionState: SessionState;
    decision: Decision;
  }>;
}

export function useInterviewSession(): UseInterviewSessionReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionState, setSessionState] = useState<SessionState | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [lastDecision, setLastDecision] = useState<Decision | null>(null);
  const caseRef = useRef<PatientCase | null>(null);
  const messagesRef = useRef<Message[]>(messages);
  messagesRef.current = messages;

  const startSession = useCallback((caseData: PatientCase) => {
    caseRef.current = caseData;
    setMessages([{ role: 'patient', text: caseData.initialComplaint }]);
    setSessionState(null);
    setLastDecision(null);
  }, []);

  const processTurn = useCallback(async (
    input: string,
    config: AIConfig,
    useNewOrchestration: boolean
  ) => {
    if (!caseRef.current || isLoading) return;

    const studentMsg: Message = { role: 'student', text: input };
    setMessages(prev => [...prev, studentMsg]);
    setIsLoading(true);

    const speechService = new SpeechService(config);
    const voiceContext = toVoiceContext(caseRef.current);

    try {
      if (useNewOrchestration && caseRef.current) {
        // Python backend orchestration path
        const allMessages = [...messagesRef.current, studentMsg];
        const result = await processTurnViaBackend(
          caseRef.current,
          allMessages,
          input,
          sessionState,
          config,
        );

        setMessages(prev => [...prev, result.patientMessage]);
        setSessionState(result.sessionState);
        setLastDecision(result.decision);

        if (result.decision.message && result.decision.type !== 'CONTINUE') {
          const coachMsg: Message = { role: 'coach', text: result.decision.message };
          setMessages(prev => [...prev, coachMsg]);
        }

        void speechService.speak(result.patientMessage.text, voiceContext);
      } else if (ENABLE_LEGACY_INTERVIEW_FALLBACK) {
        // Legacy frontend orchestration path is intentionally disabled by default.
        const { generatePatientResponse } = await import('../legacy/services/interviewAiService');
        const patientText = await generatePatientResponse(
          caseRef.current, messagesRef.current, input, config
        );

        const audioUrl = await speechService.generateUrl(patientText, voiceContext);
        const patientMsg: Message = {
          role: 'patient',
          text: patientText,
          audioUrl: audioUrl || undefined,
        };
        setMessages(prev => [...prev, patientMsg]);
        void speechService.speak(patientText, voiceContext);
      } else {
        throw new Error('Legacy interview fallback is disabled; backend orchestration is required.');
      }
    } catch (error) {
      console.error("Failed to get patient response:", error);
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, sessionState]);

  const evaluateSubmission = useCallback((): Decision | null => {
    if (!sessionState) return null;
    if (sessionState.overallCoverage < 40) {
      return {
        type: 'EARLY_END_WARNING',
        message: `Warning: You have only covered ${sessionState.overallCoverage}% of the key clinical areas. Are you sure you want to submit?`,
        data: { coverage: sessionState.overallCoverage },
      };
    }
    return null;
  }, [sessionState]);

  const resetSession = useCallback(() => {
    setMessages([]);
    setSessionState(null);
    setLastDecision(null);
    caseRef.current = null;
  }, []);

  return {
    messages,
    sessionState,
    isLoading,
    lastDecision,
    startSession,
    processTurn,
    evaluateSubmission,
    resetSession,
  };
}
