import { computed, ref } from 'vue'
import { getJson } from '../api/http.js'
import { toUserErrorMessage } from '../utils/errors.js'

const models = ref([])
const activeModel = ref('')
const status = ref('idle')
const error = ref('')

function sortModels(items) {
  return [...items].sort((left, right) => left.name.localeCompare(right.name))
}

async function refreshModels() {
  status.value = 'loading'
  error.value = ''

  try {
    const payload = await getJson('/models')
    models.value = sortModels(payload.models || [])
    activeModel.value = payload.active_model || ''
    status.value = 'ready'
    return models.value
  } catch (err) {
    models.value = []
    activeModel.value = ''
    status.value = 'error'
    error.value = toUserErrorMessage(err)
    throw err
  }
}

const modelNames = computed(() => models.value.map((model) => model.name))

function hasModel(name) {
  return models.value.some((model) => model.name === name)
}

export function useModels() {
  return {
    activeModel,
    error,
    modelNames,
    models,
    refreshModels,
    status,
    hasModel,
  }
}
