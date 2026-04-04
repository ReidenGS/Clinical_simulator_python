import type { AIConfig } from '../types/app';

// ---------------------------------------------------------------------------
// fetchWithRetry (frontend -> python backend)
// ---------------------------------------------------------------------------

function extractStatus(error: unknown): number | undefined {
  if (error !== null && typeof error === 'object') {
    const e = error as Record<string, unknown>;
    const status = e.status ?? (e.response as Record<string, unknown> | undefined)?.status ?? e.statusCode;
    if (typeof status === 'number') return status;
  }
  return undefined;
}

async function postBackend<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error = new Error(await response.text());
    (error as Error & { status?: number }).status = response.status;
    throw error;
  }

  return response.json() as Promise<T>;
}

/**
 * Retry wrapper that does NOT retry on 429 (rate limit), 401 (unauthorized), or 403 (forbidden).
 */
export const fetchWithRetry = async <T>(
  fn: () => Promise<T>,
  retries = 3,
  delay = 1000
): Promise<T> => {
  try {
    return await fn();
  } catch (error: unknown) {
    const status = extractStatus(error);
    if (typeof status === 'number' && (status === 429 || status === 401 || status === 403)) {
      throw error;
    }
    if (retries <= 0) throw error;
    await new Promise(resolve => setTimeout(resolve, delay));
    return fetchWithRetry(fn, retries - 1, delay * 2);
  }
};

/**
 * Generate a text completion using the configured AI provider.
 */
export async function generateText(
  config: AIConfig,
  systemPrompt: string,
  messages: Array<{ role: 'user' | 'assistant'; content: string }>
): Promise<string> {
  const response = await fetchWithRetry(() =>
    postBackend<{ text: string }>('/api/ai/text', {
      provider: config.textProvider,
      model: config.textModel,
      system_prompt: systemPrompt,
      messages,
      temperature: 0.4,
      api_key: config.textApiKey,
      base_url: config.textBaseUrl,
    })
  );

  return response.text || '';
}

/**
 * Generate a JSON completion using the configured AI provider.
 * Returns the raw JSON string.
 */
export async function generateJSON(
  config: AIConfig,
  systemPrompt: string,
  messages: Array<{ role: 'user' | 'assistant'; content: string }>
): Promise<string> {
  const response = await fetchWithRetry(() =>
    postBackend<{ text: string }>('/api/ai/json', {
      provider: config.textProvider,
      model: config.textModel,
      system_prompt: systemPrompt,
      messages,
      temperature: 0.4,
      api_key: config.textApiKey,
      base_url: config.textBaseUrl,
    })
  );

  return response.text || '{}';
}

/**
 * Generate a JSON completion from a single prompt (no conversation history).
 */
export async function generateJSONFromPrompt(
  config: AIConfig,
  prompt: string,
  temperature = 0.2
): Promise<string> {
  const response = await fetchWithRetry(() =>
    postBackend<{ text: string }>('/api/ai/json', {
      provider: config.textProvider,
      model: config.textModel,
      system_prompt: '',
      messages: [{ role: 'user', content: prompt }],
      temperature,
      api_key: config.textApiKey,
      base_url: config.textBaseUrl,
    })
  );

  return response.text || '{}';
}
