import { ref } from 'vue'
import { getJson } from '../api/http.js'

export function useHealth() {
  const health = ref(null)
  const status = ref('idle')
  const error = ref('')

  async function refreshHealth() {
    status.value = 'loading'
    error.value = ''

    try {
      health.value = await getJson('/health')
      status.value = 'ready'
    } catch (err) {
      health.value = null
      error.value = err instanceof Error ? err.message : 'Unknown error'
      status.value = 'error'
    }
  }

  return {
    health,
    status,
    error,
    refreshHealth,
  }
}
