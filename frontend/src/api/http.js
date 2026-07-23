const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

function buildUrl(path) {
  return `${API_BASE_URL}${path}`
}

export async function getJson(path, options = {}) {
  const response = await fetch(buildUrl(path), {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  })

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`)
  }

  return response.json()
}

export function postStream(path, body, options = {}) {
  return fetch(buildUrl(path), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    body: JSON.stringify(body),
    signal: options.signal,
  })
}
