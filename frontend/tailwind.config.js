/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        med: {
          blue: '#0f6fa8',
          teal: '#0f9b8e',
          ink: '#102a43',
          mist: '#f4f8fb',
        },
      },
      boxShadow: {
        card: '0 14px 40px rgba(15, 111, 168, 0.08)',
      },
      borderRadius: {
        card: '18px',
      },
    },
  },
  plugins: [],
};
