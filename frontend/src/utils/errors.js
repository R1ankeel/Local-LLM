export function toUserErrorMessage(error, fallback = 'Неизвестная ошибка.') {
  if (error instanceof Error && /[А-Яа-яЁё]/.test(error.message)) {
    return error.message
  }

  return fallback
}
