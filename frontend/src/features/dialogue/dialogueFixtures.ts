/** Dados inteiramente sintéticos, usados pelos testes do motor e pelo harness isolado. */
import type { Dialogue, DialogueStatus, Turn } from './dialogueTransport'
import type { LessonDetail, SpeakingPolicy } from '../../api/client'

export const statusFixture: DialogueStatus = {
  enabled: true, guided_enabled: true, audio_enabled: true, daily_quota: 12,
  remaining_today: 12, reserved_today: 0, consumed_today: 0, cost_microusd_today: 0,
  cost_incomplete: false, quota_resets_at: '2026-10-29T00:00:00Z', retention_days: 30,
}
export const policyFixture: SpeakingPolicy = {
  max_bytes: 2_000_000, max_duration_ms: 30_000, mime_types: ['audio/webm', 'audio/wav'],
  recording_target_ms: 29_000, upload_timeout_seconds: 30, content_validation: 'decoded_audio_v1',
  max_channels: 2, min_sample_rate_hz: 8000, max_sample_rate_hz: 48000,
}
export const dialogueFixture = (): Dialogue => ({
  id: 7, lesson_id: 31, mode: 'guided', state: 'active', partner_speaker: 'Anna',
  turn_limit: 12, turns_remaining: 12, provider_name: 'synthetic', rubric_version: 'test',
  started_at: '2026-10-28T12:00:00Z', ended_at: null, turns: [],
})
export const turnFixture = (position = 1): Turn => ({
  position, role: 'student', input_kind: 'text', state: 'completed', transcript: 'I take the bus.',
  checks: { target_terms_missing: true, too_short: true, too_long: true },
  check_details: { target_terms: [{ text: 'bus', covered: true }], grammar_patterns: [] },
  hints: [], partner_text: 'Where do you go?', confidence: 0.8, fallback: false,
  error_code: null, human_rating: null, job_id: 8,
  created_at: '2026-10-28T12:00:00Z', completed_at: '2026-10-28T12:00:01Z', words: [],
})
// A tela só acessa id, number, media. O harness não se passa por uma aula real.
export const lessonFixture = { id: 31, number: 31, media: [] } as unknown as LessonDetail
