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
      // Aula e ferramentas pessoais compartilham um pacote de estudo sob demanda.
      // Evita ciclos entre escrita/player e comprime contratos/UI compartilhados;
      // login e Hoje continuam sem carregar esse pacote. Diálogo segue separado.
      manualChunks(id) {
        if (/\/src\/features\/listening\/nativeStore\./.test(id)) return 'native-store'
        if (/\/src\/features\/media\/positionSync\./.test(id)) return 'position-sync'
        if (/\/src\/(features\/listening\/|api\/nativePosition\.)/.test(id)) return 'native-listening'
        if (/\/src\/(pages\/NativeListening|api\/nativeListening\.|features\/media\/NativeAudioPlayer\.)/.test(id)) return 'native-listening'
        if (/\/src\/features\/(exercise\/SelectionInput|media\/(AudioPlayback|formatAudioTime))\./.test(id)) return 'audio-controls'
        if (/\/node_modules\/@tanstack\/(?:react-query|query-core)\/.*\/(?:useInfiniteQuery|infiniteQueryObserver)\./.test(id)) return 'study'
        if (/\/src\/(pages\/(NotebookPage|PersonalDataPage|ReviewPage|TestPage|CourseReviewPage|CourseCompletionPage|usePagedItems)\.|api\/(completion|courseReviews|review|notebook)\.|features\/(privacy\/deviceInventory\.|(review|completion|checkpoint|history|notebook)\/))/.test(id)) return 'study'
        if (/\/src\/(pages\/(StudyPage|LessonPage|PracticePage)|api\/(writing|speaking|media|practice|assist|addReviewItem)\.|features\/(assist|exercise|media|speaking|study-session|writing|practice)\/|components\/(LessonSections|ExerciseCard|WritingFeedbackProvenance|GrammarBlockView|Markdown))/.test(id)) return 'study'
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
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.test.{ts,tsx}', 'src/**/*.d.ts', 'src/test-setup.ts', 'src/main.tsx'],
      reporter: ['text-summary', 'json-summary', 'html'],
      thresholds: { statements: 80, branches: 74, functions: 78, lines: 85 },
    },
    // scripts/*.test.mjs rodam com `node --test` (npm run test:scripts), sem jsdom.
    exclude: [...configDefaults.exclude, 'scripts/**'],
  },
})
