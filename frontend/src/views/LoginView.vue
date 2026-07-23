<template>
  <div class="auth-page">
    <section class="auth-card">
      <p class="brand-kicker">Local network</p>
      <h1 class="auth-title">Sign in</h1>
      <p class="auth-copy">
        Use your local backend account to open the chat. The session is stored in an HttpOnly
        cookie.
      </p>

      <form class="auth-form" @submit.prevent="handleLogin">
        <label class="auth-field">
          <span>Username</span>
          <input v-model="username" type="text" autocomplete="username" required />
        </label>

        <label class="auth-field">
          <span>Password</span>
          <input v-model="password" type="password" autocomplete="current-password" required />
        </label>

        <p v-if="errorMessage" class="stream-error" role="alert">{{ errorMessage }}</p>

        <button class="send-button auth-submit" type="submit" :disabled="loading">
          {{ loading ? 'Signing in...' : 'Sign in' }}
        </button>
      </form>
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth.js'

const username = ref('')
const password = ref('')
const loading = ref(false)
const localError = ref('')

const router = useRouter()
const route = useRoute()
const auth = useAuth()

const errorMessage = computed(() => localError.value || auth.error.value)

async function handleLogin() {
  if (loading.value) {
    return
  }

  loading.value = true
  localError.value = ''

  try {
    await auth.login(username.value.trim(), password.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.push(redirect)
  } catch (err) {
    localError.value = err instanceof Error ? err.message : 'Login failed'
  } finally {
    loading.value = false
  }
}
</script>
