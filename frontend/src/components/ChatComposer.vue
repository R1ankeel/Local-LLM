<template>
  <form class="composer" @submit.prevent="handleSubmit">
    <div class="composer-topline">
      <div class="mode-switch" role="radiogroup" aria-label="Response mode">
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

      <button v-if="isGenerating" class="stop-button" type="button" @click="emit('stop')">
        Остановить
      </button>
      <button v-else class="send-button" type="submit" :disabled="disabled || !canSend">
        Отправить
      </button>
    </div>

    <label class="composer-field">
      <span class="sr-only">Введите сообщение</span>
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
    default: 'Напишите сообщение...',
  },
})

const emit = defineEmits(['update:modelValue', 'update:mode', 'send', 'stop'])

const textareaRef = ref(null)

const canSend = computed(() => props.modelValue.trim().length > 0)

const modeOptions = [
  { value: 'instant', label: 'Instant' },
  { value: 'thinking', label: 'Thinking' },
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
