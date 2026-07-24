<template>
  <form class="composer" @submit.prevent="handleSubmit">
    <div class="composer-topline">
      <div class="mode-switch" role="radiogroup" aria-label="Режим ответа">
        <button
          v-for="option in modeOptions"
          :key="option.value"
          type="button"
          class="mode-chip"
          :class="{ active: mode === option.value }"
          :aria-pressed="mode === option.value"
          @click="emit('update:mode', option.value)"
        >
          {{ option.label }}
        </button>
      </div>

      <div class="search-switch" role="radiogroup" aria-label="Режим поиска в сети">
        <button
          v-for="option in searchModeOptions"
          :key="option.value"
          type="button"
          class="mode-chip search-chip"
          :class="{ active: webSearchMode === option.value }"
          :aria-pressed="webSearchMode === option.value"
          :disabled="disabled || isGenerating"
          @click="emit('update:webSearchMode', option.value)"
        >
          {{ option.label }}
        </button>
      </div>

      <div class="search-switch" role="radiogroup" aria-label="Источник поиска в сети">
        <button
          v-for="option in searchProviderOptions"
          :key="option.value"
          type="button"
          class="mode-chip search-chip"
          :class="{ active: webSearchProvider === option.value }"
          :aria-pressed="webSearchProvider === option.value"
          :disabled="disabled || isGenerating"
          @click="emit('update:webSearchProvider', option.value)"
        >
          {{ option.label }}
        </button>
      </div>

      <button v-if="isGenerating" class="stop-button" type="button" @click="emit('stop')">
        Остановить генерацию
      </button>
      <button v-else class="send-button" type="submit" :disabled="disabled || !canSend">
        Отправить
      </button>
    </div>

    <label class="composer-field">
      <span class="sr-only">Сообщение</span>
      <textarea
        ref="textareaRef"
        :value="modelValue"
        class="composer-input"
        rows="1"
        :placeholder="placeholder"
        :disabled="disabled"
        @input="onInput"
        @keydown="onKeydown"
      ></textarea>
    </label>
  </form>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  mode: {
    type: String,
    default: 'instant',
  },
  webSearchMode: {
    type: String,
    default: 'auto',
  },
  webSearchProvider: {
    type: String,
    default: 'duckduckgo',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  isGenerating: {
    type: Boolean,
    default: false,
  },
  placeholder: {
    type: String,
    default: 'Введите сообщение...',
  },
})

const emit = defineEmits([
  'update:modelValue',
  'update:mode',
  'update:webSearchMode',
  'update:webSearchProvider',
  'send',
  'stop',
])

const textareaRef = ref(null)

const canSend = computed(() => props.modelValue.trim().length > 0)

const modeOptions = [
  { value: 'instant', label: 'Мгновенно' },
  { value: 'thinking', label: 'С обдумыванием' },
]

const searchModeOptions = [
  { value: 'off', label: 'Выкл' },
  { value: 'auto', label: 'Авто' },
  { value: 'always', label: 'Всегда' },
]

const searchProviderOptions = [
  { value: 'duckduckgo', label: 'DuckDuckGo' },
  { value: 'xai', label: 'xAI' },
]

function resizeTextarea() {
  const textarea = textareaRef.value
  if (!textarea) return

  textarea.style.height = '0px'
  const nextHeight = Math.min(textarea.scrollHeight, 180)
  textarea.style.height = `${Math.max(nextHeight, 56)}px`
}

function onInput(event) {
  emit('update:modelValue', event.target.value)
  resizeTextarea()
}

function handleSubmit() {
  if (!canSend.value || props.disabled || props.isGenerating) {
    return
  }

  emit('send')
}

function onKeydown(event) {
  if (event.isComposing) {
    return
  }

  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSubmit()
  }
}

watch(
  () => props.modelValue,
  async () => {
    await nextTick()
    resizeTextarea()
  },
)

onMounted(() => {
  resizeTextarea()
})
</script>
