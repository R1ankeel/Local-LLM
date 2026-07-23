<template>
  <div class="auth-page">
    <section class="auth-card">
      <p class="brand-kicker">Локальная сеть</p>
      <h1 class="auth-title">Вход</h1>
      <p class="auth-copy">
        Используйте локальную учетную запись бэкенда, чтобы открыть чат. Сеанс сохраняется в
        cookie HttpOnly.
      </p>

      <form class="auth-form" @submit.prevent="handleLogin">
        <label class="auth-field">
          <span>Имя пользователя</span>
          <input v-model="username" type="text" autocomplete="username" required />
        </label>

        <label class="auth-field">
          <span>Пароль</span>
          <input v-model="password" type="password" autocomplete="current-password" required />
        </label>

        <p v-if="errorMessage" class="stream-error" role="alert">{{ errorMessage }}</p>

        <button class="send-button auth-submit" type="submit" :disabled="loading">
          {{ loading ? 'Выполняется вход...' : 'Войти' }}
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
    localError.value = err instanceof Error && /[А-Яа-яЁё]/.test(err.message)
      ? err.message
      : 'Не удалось выполнить вход.'
  } finally {
    loading.value = false
  }
}
</script>
