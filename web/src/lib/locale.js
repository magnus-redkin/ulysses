// Создаем реактивный объект состояния
export const locale = $state({
  current: 'ru', // язык по умолчанию

  // Метод для переключения
  set(lang) {
    this.current = lang;
  }
});
