import { computed, ref } from 'vue'
import { getJson, postJson } from '../api/http.js'
import { toUserErrorMessage } from '../utils/errors.js'

const currentUser = ref(null)
const status = ref('idle')
const error = ref('')
let loadPromise = null

function normalizeAuthError(err) {
  if (err instanceof Error && typeof err.status === 'number' && err.status !== 401) {
    return toUserErrorMessage(err)
  }

  return toUserErrorMessage(err, 'Не удалось выполнить авторизацию.')
}

async function loadCurrentUser() {
  if (loadPromise) {
    return loadPromise
  }

  loadPromise = (async () => {
    status.value = 'loading'

    try {
      currentUser.value = await getJson('/auth/me')
      status.value = 'authenticated'
      error.value = ''
      return currentUser.value
    } catch (err) {
      currentUser.value = null
      status.value = 'anonymous'
      error.value = ''
      if (err instanceof Error && typeof err.status === 'number' && err.status !== 401) {
        error.value = normalizeAuthError(err)
      }
      return null
    } finally {
      loadPromise = null
    }
  })()

  return loadPromise
}

export function useAuth() {
  const isAuthenticated = computed(() => currentUser.value !== null)
  const isLoading = computed(() => status.value === 'idle' || status.value === 'loading')

  async function ensureAuthLoaded() {
    if (status.value === 'idle' || status.value === 'loading') {
      return loadCurrentUser()
    }

    return currentUser.value
  }

  async function login(username, password) {
    error.value = ''

    try {
      currentUser.value = await postJson('/auth/login', { username, password })
      status.value = 'authenticated'
      return currentUser.value
    } catch (err) {
      currentUser.value = null
      status.value = 'anonymous'
      error.value = normalizeAuthError(err)
      throw err
    }
  }

  async function logout() {
    error.value = ''

    try {
      await postJson('/auth/logout', {})
    } finally {
      currentUser.value = null
      status.value = 'anonymous'
    }
  }

  return {
    currentUser,
    error,
    isAuthenticated,
    isLoading,
    ensureAuthLoaded,
    login,
    loadCurrentUser,
    logout,
    status,
  }
}
