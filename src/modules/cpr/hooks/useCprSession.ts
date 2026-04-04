import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { WorkflowOrchestrator } from '../orchestration/WorkflowOrchestrator';
import { ScenarioManager } from '../orchestration/ScenarioManager';
import { loadCprRubric } from '../data/RubricRepository';
import type {
  CprBackendStateEnvelope,
  CprDecision,
  CprEvaluation,
  CprObservation,
  CprPhase,
  CprScenario,
  CprSessionState,
} from '../types';
import type { CprFeedbackSummary } from '../evaluation/FeedbackGenerator';

type BackendCprResult = {
  sessionState: CprSessionState;
  runtimeState: CprBackendStateEnvelope['runtimeState'];
  decision: CprDecision;
  meta?: {
    usedFallback?: boolean;
    transitionEvents?: string[];
  };
};

async function ingestViaBackend(
  scenario: CprScenario,
  state: CprBackendStateEnvelope | null,
  observation: CprObservation,
): Promise<BackendCprResult> {
  const response = await fetch('/api/cpr/runtime/ingest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      scenario,
      state,
      observation,
    }),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json() as Promise<BackendCprResult>;
}

async function applyActionViaBackend(
  scenario: CprScenario,
  state: CprBackendStateEnvelope,
  action: 'advance_phase' | 'confirm_ventilation' | 'confirm_phase_advance',
  phase?: CprPhase,
): Promise<BackendCprResult> {
  const response = await fetch('/api/cpr/runtime/action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      scenario,
      state,
      action,
      phase,
    }),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json() as Promise<BackendCprResult>;
}

async function evaluateViaBackend(
  sessionState: CprSessionState,
  scenario: CprScenario,
): Promise<{ evaluation: CprEvaluation; feedback: CprFeedbackSummary }> {
  const response = await fetch('/api/cpr/evaluate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      sessionState,
      scenario,
      rubric: loadCprRubric(),
    }),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json() as Promise<{ evaluation: CprEvaluation; feedback: CprFeedbackSummary }>;
}

interface UseCprSessionResult {
  scenario: CprScenario;
  sessionState: CprSessionState | null;
  lastDecision: CprDecision | null;
  evaluation: CprEvaluation | null;
  feedback: CprFeedbackSummary | null;
  ventilationBreathCount: number;
  ingestObservation: (observation: CprObservation) => void;
  finalizeSession: () => void;
  resetSession: () => void;
  advancePhase: (phase: CprPhase) => void;
  confirmVentilation: () => void;
  confirmPhaseAdvance: () => void;
  allScenarios: CprScenario[];
}

export function useCprSession(scenarioId?: string): UseCprSessionResult {
  const scenarioManager = useMemo(() => new ScenarioManager(scenarioId), [scenarioId]);
  const scenario = useMemo(() => scenarioManager.getScenario(), [scenarioManager]);
  const allScenarios = useMemo(() => ScenarioManager.listScenarios(), []);
  const orchestratorRef = useRef(new WorkflowOrchestrator(scenario));
  const backendStateRef = useRef<CprBackendStateEnvelope | null>(null);
  const requestSeqRef = useRef(0);
  const [sessionState, setSessionState] = useState<CprSessionState | null>(null);
  const [lastDecision, setLastDecision] = useState<CprDecision | null>(null);
  const [evaluation, setEvaluation] = useState<CprEvaluation | null>(null);
  const [feedback, setFeedback] = useState<CprFeedbackSummary | null>(null);
  const [ventilationBreathCount, setVentilationBreathCount] = useState(0);

  const applyAuthoritativeResult = useCallback((result: BackendCprResult) => {
    const envelope: CprBackendStateEnvelope = {
      sessionState: result.sessionState,
      runtimeState: result.runtimeState ?? null,
    };
    backendStateRef.current = envelope;
    setSessionState(result.sessionState);
    setLastDecision(result.decision);
    setVentilationBreathCount(
      result.sessionState.currentPhase === 'VENTILATION'
        ? (result.runtimeState?.ventilationBreathCount ?? 0)
        : 0,
    );
  }, []);

  useEffect(() => {
    if (sessionState && backendStateRef.current) {
      backendStateRef.current = {
        ...backendStateRef.current,
        sessionState,
      };
    }
  }, [sessionState]);

  useEffect(() => {
    orchestratorRef.current = new WorkflowOrchestrator(scenario);
    backendStateRef.current = null;
    requestSeqRef.current = 0;
    setSessionState(null);
    setLastDecision(null);
    setEvaluation(null);
    setFeedback(null);
    setVentilationBreathCount(0);
  }, [scenario]);

  const ingestObservation = useCallback((observation: CprObservation) => {
    const requestId = ++requestSeqRef.current;
    void ingestViaBackend(scenario, backendStateRef.current, observation)
      .then((result) => {
        if (requestId !== requestSeqRef.current) return;
        applyAuthoritativeResult(result);
      })
      .catch((error) => {
        if (requestId !== requestSeqRef.current) return;
        console.error('CPR backend ingest failed, using local fallback:', error);
        const fallback = orchestratorRef.current.ingest(observation);
        backendStateRef.current = {
          sessionState: fallback.state,
          runtimeState: null,
        };
        setSessionState(fallback.state);
        setLastDecision(fallback.decision);
        setVentilationBreathCount(orchestratorRef.current.getVentilationBreathCount());
      });
  }, [scenario, applyAuthoritativeResult]);

  const finalizeSession = useCallback(() => {
    const latestState = backendStateRef.current?.sessionState ?? orchestratorRef.current.getLatestState();
    if (!latestState) return;
    setSessionState(latestState);

    void evaluateViaBackend(latestState, scenario)
      .then((result) => {
        setEvaluation(result.evaluation);
        setFeedback(result.feedback);
      })
      .catch((error) => {
        console.error('CPR backend evaluation failed:', error);
        const fallback = orchestratorRef.current.evaluate(latestState);
        setEvaluation(fallback);
        setFeedback({
          headline: fallback.totalScore >= 85
            ? 'CPR workflow is on target.'
            : fallback.totalScore >= 70
              ? 'CPR workflow is functional with correctable gaps.'
              : 'CPR workflow needs more guided practice.',
          summary: `Average cadence ${latestState.averageRate || 0} CPM, visibility ${Math.round(latestState.visibleRatio * 100)}%, straight-arm consistency ${Math.round(latestState.straightArmRatio * 100)}%.`,
          evaluation: fallback,
        });
      });
  }, [scenario]);

  const resetSession = useCallback(() => {
    orchestratorRef.current.reset();
    backendStateRef.current = null;
    requestSeqRef.current += 1;
    setSessionState(null);
    setLastDecision(null);
    setEvaluation(null);
    setFeedback(null);
    setVentilationBreathCount(0);
  }, []);

  const advancePhase = useCallback((phase: CprPhase) => {
    const current = backendStateRef.current;
    if (current) {
      const requestId = ++requestSeqRef.current;
      void applyActionViaBackend(scenario, current, 'advance_phase', phase)
        .then((result) => {
          if (requestId !== requestSeqRef.current) return;
          applyAuthoritativeResult(result);
        })
        .catch((error) => {
          if (requestId !== requestSeqRef.current) return;
          console.error('CPR backend phase advance failed, using local fallback:', error);
          orchestratorRef.current.advancePhase(phase);
          const next = { ...current.sessionState, currentPhase: phase };
          backendStateRef.current = { ...current, sessionState: next };
          setSessionState(next);
        });
      return;
    }

    orchestratorRef.current.advancePhase(phase);
  }, [scenario, applyAuthoritativeResult]);

  const confirmVentilation = useCallback(() => {
    const current = backendStateRef.current;
    if (current) {
      const requestId = ++requestSeqRef.current;
      void applyActionViaBackend(scenario, current, 'confirm_ventilation')
        .then((result) => {
          if (requestId !== requestSeqRef.current) return;
          applyAuthoritativeResult(result);
        })
        .catch((error) => {
          if (requestId !== requestSeqRef.current) return;
          console.error('CPR backend ventilation confirm failed, using local fallback:', error);
          orchestratorRef.current.confirmVentilation();
          setVentilationBreathCount(orchestratorRef.current.getVentilationBreathCount());
        });
      return;
    }

    orchestratorRef.current.confirmVentilation();
    setVentilationBreathCount(orchestratorRef.current.getVentilationBreathCount());
  }, [scenario, applyAuthoritativeResult]);

  const confirmPhaseAdvance = useCallback(() => {
    const current = backendStateRef.current;
    if (current) {
      const requestId = ++requestSeqRef.current;
      void applyActionViaBackend(scenario, current, 'confirm_phase_advance')
        .then((result) => {
          if (requestId !== requestSeqRef.current) return;
          applyAuthoritativeResult(result);
        })
        .catch((error) => {
          if (requestId !== requestSeqRef.current) return;
          console.error('CPR backend phase confirm failed, using local fallback:', error);
          orchestratorRef.current.confirmPhaseAdvance();
          if (current.sessionState.currentPhase === 'CYCLE_BREAK') {
            const next = { ...current.sessionState, currentPhase: 'COMPRESSIONS' as CprPhase };
            backendStateRef.current = { ...current, sessionState: next };
            setSessionState(next);
          }
        });
      return;
    }

    orchestratorRef.current.confirmPhaseAdvance();
  }, [scenario, applyAuthoritativeResult]);

  return {
    scenario,
    sessionState,
    lastDecision,
    evaluation,
    feedback,
    ventilationBreathCount,
    ingestObservation,
    finalizeSession,
    resetSession,
    advancePhase,
    confirmVentilation,
    confirmPhaseAdvance,
    allScenarios,
  };
}
