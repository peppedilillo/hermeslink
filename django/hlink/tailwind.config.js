/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    'templates/*.html',
    'templates/registration/*.html',
    'configs/templates/configs/*.html',
    'configs/templates/configs/includes/*.html',
    'main/templates/main/*.html',
  ],
  safelist: [
    'text-blue-500',
    'text-orange-500',
    'text-green-50',
    'text-green-100',
    'text-green-200',
    'text-green-300',
    'text-green-400',
    'text-green-500',
    'text-green-600',
    'text-green-700',
    'text-green-800',
    'text-green-900',
    'text-green-950',
    'status-dot',
    'status-dot-green',
    'status-dot-red',
    'status-dot-yellow',
  ],
  theme: {
    extend: {
      // Add custom box shadows for the glow effects
      boxShadow: {
        'glow-green': '0 0 5px 2px rgba(34, 197, 94, 0.6)',
        'glow-red': '0 0 5px 2px rgba(239, 68, 68, 0.6)',
        'glow-yellow': '0 0 5px 2px rgba(234, 179, 8, 0.6)',
      },
    },
  },
}