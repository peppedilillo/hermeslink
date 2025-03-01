/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    'templates/*.html',
    'templates/registration/*.html',
    'configs/templates/configs/*.html',
    'main/templates/main/*.html',
  ],
  safelist: [
    'text-blue-500',
    'text-orange-500',
  ],
}