import react from '@vitejs/plugin-react'
// defineConfig vem do vitest/config (e não do vite) para que a chave `test`
// seja tipada — com o import do vite, tsc rejeita a configuração de teste.
import { configDefaults, defineConfig } from 'vitest/config'
import { pwaBuild } from './scripts/pwa-build'

// O browser nunca fala direto com a API: tudo passa por /api na mesma origem.
// Isso evita CORS em dev e deixa o caminho pronto para o cookie httpOnly da S3.
const apiTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8010'

export default defineConfig({
  plugins: [react(), pwaBuild()],
  // Mantém o orçamento existente sem remover recursos ou alterar navegadores-alvo.
  build: {
    minify: 'terser', terserOptions: { maxWorkers: 2, compress: { passes: 4 } },
    rollupOptions: { output: {
      onlyExplicitManualChunks: true,
      // Jornada e aula completa compartilham player, exercícios e explicações.
      // Agrupar esses módulos reduz overhead de compressão sem antecipá-los no login/Hoje.
      manualChunks(id) {
        // Ferramentas pessoais/históricos usam os mesmos contratos e padrões de UI.
        // Compartilham um chunk tardio; login/Hoje e aulas não o antecipam.
        if (/\/src\/(pages\/(NotebookPage|PersonalDataPage|ReviewPage|TestPage|CourseReviewPage|CourseCompletionPage|usePagedItems)\.|api\/(completion|courseReviews|review)\.|features\/(privacy\/deviceInventory\.|(review|completion|checkpoint)\/))/.test(id)) return 'study-tools'
        if (/\/src\/(pages\/(StudyPage|LessonPage|PracticePage)|api\/(media|practice|assist|addReviewItem)\.|features\/(assist|exercise|media|speaking|study-session|writing|practice)\/|components\/(LessonSections|ExerciseCard|WritingFeedbackProvenance|GrammarBlockView|Markdown))/.test(id)) return 'lesson-study'
      },
    } },
  },
  server: {
    host: true,
    port: 5180,
    strictPort: true,
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    // scripts/*.test.mjs rodam com `node --test` (npm run test:scripts), sem jsdom.
    exclude: [...configDefaults.exclude, 'scripts/**'],
  },
})
