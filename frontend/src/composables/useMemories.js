import { ref } from 'vue'
import { deleteJson, getJson, patchJson, postJson } from '../api/http.js'
import { toUserErrorMessage } from '../utils/errors.js'

const memories = ref([])
const status = ref('idle')
const error = ref('')

function sortMemories(items) {
  return [...items].sort((left, right) => {
    const leftTime = new Date(left.updated_at || left.created_at || 0).getTime()
    const rightTime = new Date(right.updated_at || right.created_at || 0).getTime()

    if (leftTime !== rightTime) {
      return rightTime - leftTime
    }

    return (right.id || 0) - (left.id || 0)
  })
}

function upsertMemory(memory) {
  const next = memories.value.filter((item) => item.id !== memory.id)
  next.push(memory)
  memories.value = sortMemories(next)
}

function resetMemories() {
  memories.value = []
  status.value = 'idle'
  error.value = ''
}

async function refreshMemories() {
  status.value = 'loading'
  error.value = ''

  try {
    memories.value = sortMemories(await getJson('/memories'))
    status.value = 'ready'
    return memories.value
  } catch (err) {
    memories.value = []
    status.value = 'error'
    error.value = toUserErrorMessage(err)
    throw err
  }
}

async function createMemory(payload) {
  const memory = await postJson('/memories', payload)
  upsertMemory(memory)
  return memory
}

async function updateMemory(memoryId, payload) {
  const memory = await patchJson(`/memories/${memoryId}`, payload)
  upsertMemory(memory)
  return memory
}

async function deleteMemory(memoryId) {
  await deleteJson(`/memories/${memoryId}`)
  memories.value = memories.value.filter((memory) => memory.id !== memoryId)
}

export function useMemories() {
  return {
    createMemory,
    deleteMemory,
    error,
    memories,
    refreshMemories,
    resetMemories,
    status,
    updateMemory,
  }
}
