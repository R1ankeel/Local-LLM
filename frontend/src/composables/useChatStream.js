import { ref } from 'vue'
import { postStream } from '../api/http.js'

function normalizeError(message) {
  return message || 'Не удалось получить ответ'
}

export function useChatStream() {
  const isGenerating = ref(false)
  const error = ref('')
  const assistantText = ref('')

  let abortController = null

  function stop() {
    if (abortController) {
      abortController.abort()
    }
  }

  async function sendChat(payload, handlers = {}) {
    if (isGenerating.value) {
      return { started: false, text: assistantText.value, aborted: false }
    }

    const controller = new AbortController()
    abortController = controller
    isGenerating.value = true
    error.value = ''
    assistantText.value = ''

    let started = false
    let finished = false

    try {
      const response = await postStream('/chat', payload, {
        signal: controller.signal,
      })

      if (!response.ok || !response.body) {
        throw new Error(`Request failed with status ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()

        if (done) {
          break
        }

        buffer += decoder.decode(value, { stream: true })

        while (true) {
          const newlineIndex = buffer.indexOf('\n')
          if (newlineIndex === -1) {
            break
          }

          const rawLine = buffer.slice(0, newlineIndex).trim()
          buffer = buffer.slice(newlineIndex + 1)

          if (!rawLine) {
            continue
          }

          const event = JSON.parse(rawLine)

          if (event.type === 'content') {
            started = true
            assistantText.value += event.content || ''
            handlers.onChunk?.(assistantText.value, event.content || '')
            continue
          }

          if (event.type === 'done') {
            finished = true
            handlers.onDone?.(assistantText.value)
            break
          }

          if (event.type === 'error') {
            throw new Error(event.message || 'Unknown error')
          }
        }

        if (finished) {
          break
        }
      }

      if (!finished && buffer.trim()) {
        const event = JSON.parse(buffer.trim())

        if (event.type === 'content') {
          started = true
          assistantText.value += event.content || ''
          handlers.onChunk?.(assistantText.value, event.content || '')
        } else if (event.type === 'error') {
          throw new Error(event.message || 'Unknown error')
        }
      }

      if (!finished) {
        handlers.onDone?.(assistantText.value)
      }

      return { started, text: assistantText.value, aborted: false }
    } catch (err) {
      if (controller.signal.aborted) {
        handlers.onAbort?.({ started, text: assistantText.value })
        return { started, text: assistantText.value, aborted: true }
      }

      const message = err instanceof Error ? normalizeError(err.message) : normalizeError('')
      error.value = message
      handlers.onError?.({ started, text: assistantText.value, message })
      return { started, text: assistantText.value, aborted: false, error: message }
    } finally {
      isGenerating.value = false
      abortController = null
    }
  }

  return {
    assistantText,
    error,
    isGenerating,
    sendChat,
    stop,
  }
}
