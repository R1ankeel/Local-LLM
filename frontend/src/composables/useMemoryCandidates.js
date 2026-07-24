import { ref } from 'vue'
import { deleteJson, getJson, patchJson, postJson } from '../api/http.js'
import { toUserErrorMessage } from '../utils/errors.js'

const memoryCandidates = ref([])
const status = ref('idle')
const error = ref('')

function sortCandidates(items) {
  return [...items].sort((left, right) => {
    const leftTime = new Date(left.updated_at || left.created_at || 0).getTime()
    const rightTime = new Date(right.updated_at || right.created_at || 0).getTime()

    if (leftTime !== rightTime) {
      return rightTime - leftTime
    }

    return (right.id || 0) - (left.id || 0)
  })
}

function upsertCandidate(candidate) {
  const next = memoryCandidates.value.filter((item) => item.id !== candidate.id)
  next.push(candidate)
  memoryCandidates.value = sortCandidates(next)
}

function resetMemoryCandidates() {
  memoryCandidates.value = []
  status.value = 'idle'
  error.value = ''
}

async function refreshMemoryCandidates(chatId) {
  if (!chatId) {
    resetMemoryCandidates()
    return memoryCandidates.value
  }

  status.value = 'loading'
  error.value = ''

  try {
    memoryCandidates.value = sortCandidates(
      (await getJson(`/chats/${chatId}/memory-candidates?status=pending`)).filter(
        (candidate) => candidate.status === 'pending',
      ),
    )
    status.value = 'ready'
    return memoryCandidates.value
  } catch (err) {
    memoryCandidates.value = []
    status.value = 'error'
    error.value = toUserErrorMessage(err)
    throw err
  }
}

async function analyzeMemoryCandidates(chatId) {
  if (!chatId) {
    return []
  }

  status.value = 'loading'
  error.value = ''

  try {
    memoryCandidates.value = sortCandidates(
      (await postJson(`/chats/${chatId}/memory-candidates/analyze`, {})).filter(
        (candidate) => candidate.status === 'pending',
      ),
    )
    status.value = 'ready'
    return memoryCandidates.value
  } catch (err) {
    status.value = 'error'
    error.value = toUserErrorMessage(err)
    throw err
  }
}

async function reviewMemoryCandidate(chatId, candidateId, payload) {
  const candidate = await patchJson(`/chats/${chatId}/memory-candidates/${candidateId}`, payload)
  if (candidate.status === 'pending') {
    upsertCandidate(candidate)
  } else {
    memoryCandidates.value = memoryCandidates.value.filter((item) => item.id !== candidate.id)
  }
  return candidate
}

async function deleteMemoryCandidate(chatId, candidateId) {
  await deleteJson(`/chats/${chatId}/memory-candidates/${candidateId}`)
  memoryCandidates.value = memoryCandidates.value.filter((candidate) => candidate.id !== candidateId)
}

export function useMemoryCandidates() {
  return {
    analyzeMemoryCandidates,
    deleteMemoryCandidate,
    error,
    memoryCandidates,
    refreshMemoryCandidates,
    resetMemoryCandidates,
    reviewMemoryCandidate,
    status,
  }
}
