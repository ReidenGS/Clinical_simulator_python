import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { RefreshCw, Stethoscope } from 'lucide-react';
import { AnimatePresence } from 'motion/react';
import type { ModuleScreenProps } from '../../../platform/types';
import { AIProvider } from '../../../platform/types';
import { InterviewStatus } from '../types';
import type { PatientCase, Assessment, FeedbackReport } from '../types';
import { loadAllCases } from '../data/CaseRepository';
import { loadRubricConfig } from '../data/RubricRepository';
import { useInterviewSession } from '../hooks/useInterviewSession';
import { useSpeechRecognition } from '../../../platform/audio/speechRecognition';
import { ProgressEngine } from '../tracking/ProgressEngine';
import { saveInterviewResult } from '../../../platform/storage/sessionStore';
import { getCasesByDifficulty } from '../data/CaseRepository';
import CaseSelector from './CaseSelector';
import PatientInfoPanel from './PatientInfoPanel';
import InterviewChat from './InterviewChat';
import AssessmentReport from './AssessmentReport';
import InterviewBrief from './InterviewBrief';
import InlineConfirm from './InlineConfirm';

const USE_NEW_ORCHESTRATION = true;
// Legacy evaluation fallback is disabled by default. The Python backend is the primary path.
const ENABLE_LEGACY_INTERVIEW_EVALUATION = false;


export default function InterviewScreen({ aiConfig, onBack, registerGlobalBackHandler }: ModuleScreenProps) {
  const [showBrief, setShowBrief] = useState(false);
  const [status, setStatus] = useState<InterviewStatus>(InterviewStatus.IDLE);
  const [currentCase, setCurrentCase] = useState<PatientCase | null>(null);
  const [inputText, setInputText] = useState('');
  const [diagnosis, setDiagnosis] = useState('');
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [feedbackReport, setFeedbackReport] = useState<FeedbackReport | null>(null);
  const [showDiagnosis, setShowDiagnosis] = useState(false);
  const [showTips, setShowTips] = useState(false);
  const [beginnerMode, setBeginnerMode] = useState(() => localStorage.getItem('beginner_mode') === 'true');
  const [warningMessage, setWarningMessage] = useState<string | null>(null);
  const [pendingSubmit, setPendingSubmit] = useState(false);
  const [showExitConfirm, setShowExitConfirm] = useState(false);

  const { isListening, transcript, isSupported, toggleListening, clearTranscript } = useSpeechRecognition();
  const session = useInterviewSession();

  const allCases = useMemo(() => loadAllCases(), []);

  const toggleBeginner = () => {
    setBeginnerMode((prev) => {
      const next = !prev;
      localStorage.setItem('beginner_mode', String(next));
      return next;
    });
  };

  // Sync speech recognition transcript to input
  useEffect(() => {
    if (transcript) {
      setInputText(transcript);
      clearTranscript();
    }
  }, [transcript, clearTranscript]);

  const handleSelectCase = (patientCase: PatientCase) => {
    setCurrentCase(patientCase);
    setShowBrief(true);
  };

  const handleStartFromBrief = () => {
    if (!currentCase) return;
    setShowBrief(false);
    session.startSession(currentCase);
    setStatus(InterviewStatus.INTERVIEWING);
    setDiagnosis('');
    setAssessment(null);
    setFeedbackReport(null);
    setShowDiagnosis(false);
    setShowTips(false);
  };

  const handleBackToCases = () => {
    setCurrentCase(null);
    setShowBrief(false);
    setStatus(InterviewStatus.IDLE);
  };

  const handleRetryCase = () => {
    if (!currentCase) return;
    setShowBrief(true);
    setStatus(InterviewStatus.IDLE);
    setAssessment(null);
    setFeedbackReport(null);
  };

  const handleSendMessage = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!inputText.trim() || !currentCase || session.isLoading) return;
    const text = inputText;
    setInputText('');
    await session.processTurn(text, aiConfig, USE_NEW_ORCHESTRATION);
  };

  const handleEndInterview = async () => {
    if (!diagnosis.trim() || !currentCase) return;

    // Beginner mode: block with inline message
    if (beginnerMode && session.sessionState && session.sessionState.overallCoverage < 40) {
      setWarningMessage(`In Beginner Mode, you need at least 40% coverage before submitting. Currently at ${Math.round(session.sessionState.overallCoverage)}%.`);
      return;
    }

    // Check for early submission warning — show inline, require second click
    if (USE_NEW_ORCHESTRATION && !pendingSubmit) {
      const warning = session.evaluateSubmission();
      if (warning) {
        setWarningMessage(warning.message || 'Your coverage is low. Submit anyway?');
        setPendingSubmit(true);
        return;
      }
    }

    setPendingSubmit(false);
    setWarningMessage(null);
    setStatus(InterviewStatus.ASSESSING);

    try {
      if (USE_NEW_ORCHESTRATION && session.sessionState) {
        // All three providers (OPENAI, GEMINI, QWEN) are now supported by the backend.
        const evaluationConfig = aiConfig;

        const rubricConfig = loadRubricConfig();
        const difficultyCases = {
          easy: getCasesByDifficulty('easy'),
          medium: getCasesByDifficulty('medium'),
          hard: getCasesByDifficulty('hard'),
        };

        const response = await fetch('/api/interview/evaluate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sessionState: session.sessionState,
            diagnosis,
            caseData: currentCase,
            rubricConfig,
            config: evaluationConfig,
            difficultyCases,
          }),
        });

        if (!response.ok) {
          const raw = await response.text();
          let detail = raw;
          try {
            const parsed = JSON.parse(raw) as { detail?: unknown };
            if (typeof parsed.detail === 'string') {
              detail = parsed.detail;
            } else if (Array.isArray(parsed.detail)) {
              detail = parsed.detail.map(item => {
                if (item && typeof item === 'object' && 'msg' in item && typeof item.msg === 'string') {
                  return item.msg;
                }
                return String(item);
              }).join('; ');
            }
          } catch {
            // keep raw text
          }
          throw new Error(detail || `HTTP ${response.status}`);
        }

        const result = await response.json() as {
          rubricResult: NonNullable<FeedbackReport['rubricResult']>;
          feedbackReport: FeedbackReport;
        };

        setFeedbackReport(result.feedbackReport);

        saveInterviewResult(
          currentCase.name,
          result.rubricResult.weightedTotal,
          `${result.feedbackReport.competencyLevel} - ${currentCase.name}`,
        );
      } else if (ENABLE_LEGACY_INTERVIEW_EVALUATION) {
        const { evaluateInterview } = await import('../legacy/services/interviewAiService');
        const result = await evaluateInterview(currentCase, session.messages, diagnosis, aiConfig);
        setAssessment(result);
        saveInterviewResult(
          currentCase.name,
          result.score,
          `Score ${result.score} - ${currentCase.name}`,
        );
      } else {
        throw new Error('Legacy interview evaluation is disabled; backend evaluation is required.');
      }
      setStatus(InterviewStatus.COMPLETED);
    } catch (error) {
      console.error("Assessment failed:", error);
      const message = error instanceof Error ? error.message : 'Unknown error';
      setWarningMessage(`Assessment failed: ${message}`);
      setStatus(InterviewStatus.INTERVIEWING);
    }
  };

  // Exit protection — inline confirm
  const handleBack = useCallback(() => {
    if (status === InterviewStatus.INTERVIEWING && session.messages.length > 2) {
      setShowExitConfirm(true);
      return;
    }
    onBack();
  }, [onBack, session.messages.length, status]);

  const confirmExit = useCallback(() => {
    setShowExitConfirm(false);
    onBack();
  }, [onBack]);

  useEffect(() => {
    registerGlobalBackHandler?.(handleBack);
    return () => registerGlobalBackHandler?.(null);
  }, [handleBack, registerGlobalBackHandler]);

  // Progress engine for critical gaps
  const progressEngine = useMemo(
    () => (currentCase ? new ProgressEngine(currentCase) : null),
    [currentCase]
  );
  const criticalGaps = useMemo(
    () => (progressEngine && session.sessionState
      ? progressEngine.getCriticalGaps(session.sessionState)
      : []),
    [progressEngine, session.sessionState]
  );

  // BRIEF phase: full-width card
  if (showBrief && currentCase) {
    return (
      <AnimatePresence mode="wait">
        <InterviewBrief
          patientCase={currentCase}
          onStart={handleStartFromBrief}
          onBack={handleBackToCases}
        />
      </AnimatePresence>
    );
  }

  if (status === InterviewStatus.IDLE) {
    return (
      <div className="lg:col-span-12 flex items-start justify-center py-2 lg:py-6">
        <CaseSelector cases={allCases} onSelectCase={handleSelectCase} />
      </div>
    );
  }

  // Full-width centered layouts for completed / assessing states
  if (status === InterviewStatus.COMPLETED) {
    return (
      <div className="lg:col-span-12 flex justify-center overflow-y-auto overscroll-contain lg:max-h-[calc(100dvh-9rem)]">
        <div className="w-full max-w-4xl">
          <AssessmentReport
            assessment={assessment}
            feedbackReport={feedbackReport}
            onNewSession={() => { setCurrentCase(null); setStatus(InterviewStatus.IDLE); }}
            onRetryCase={handleRetryCase}
          />
        </div>
      </div>
    );
  }

  if (status === InterviewStatus.ASSESSING) {
    return (
      <div className="lg:col-span-12 h-[calc(100vh-12rem)] flex flex-col items-center justify-center space-y-6">
        <div className="relative">
          <RefreshCw className="w-16 h-16 animate-spin text-[#141414]" />
          <Stethoscope className="w-6 h-6 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
        </div>
        <div className="text-center space-y-2">
          <h2 className="text-xl font-bold uppercase tracking-widest">Analyzing Interview</h2>
          <p className="text-sm opacity-50 font-mono">Evaluating clinical reasoning and communication efficiency...</p>
        </div>
      </div>
    );
  }

  return (
    <>
      {/* Left Column */}
      <div className="lg:col-span-4 space-y-3">
        {/* Exit confirm banner */}
        <InlineConfirm
          message="You are in the middle of a session. Exit anyway?"
          isVisible={showExitConfirm}
          onConfirm={confirmExit}
          onCancel={() => setShowExitConfirm(false)}
          confirmLabel="Exit"
          cancelLabel="Stay"
          variant="danger"
        />

        {currentCase && (
          <PatientInfoPanel
            currentCase={currentCase}
            status={status}
            diagnosis={diagnosis}
            isLoading={session.isLoading}
            showDiagnosis={showDiagnosis}
            showTips={showTips}
            sessionState={session.sessionState || undefined}
            criticalGaps={criticalGaps}
            onDiagnosisChange={setDiagnosis}
            onToggleDiagnosis={() => setShowDiagnosis(!showDiagnosis)}
            onToggleTips={() => setShowTips(!showTips)}
            onSubmitDiagnosis={handleEndInterview}
            beginnerMode={beginnerMode}
            warningMessage={warningMessage}
            onDismissWarning={() => { setWarningMessage(null); setPendingSubmit(false); }}
          />
        )}
      </div>

      {/* Right Column */}
      <div className="lg:col-span-8">
        <AnimatePresence mode="wait">
          {status === InterviewStatus.INTERVIEWING ? (
            <InterviewChat
              messages={session.messages}
              inputText={inputText}
              isLoading={session.isLoading}
              isListening={isListening}
              isSupported={isSupported}
              aiConfig={aiConfig}
              onInputChange={setInputText}
              onSend={handleSendMessage}
              onToggleListening={toggleListening}
              sessionState={session.sessionState || undefined}
              beginnerMode={beginnerMode}
            />
          ) : null}
        </AnimatePresence>
      </div>
    </>
  );
}
