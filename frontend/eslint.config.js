import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'node_modules'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommendedTypeChecked, jsxA11y.flatConfigs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022, globals: globals.browser,
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Regiões de tabela com overflow precisam receber foco para rolar por teclado.
      'jsx-a11y/no-noninteractive-tabindex': ['error', { roles: ['region'] }],
      'jsx-a11y/label-has-associated-control': ['error', { depth: 3 }],
    },
  },
  {
    ...js.configs.recommended,
    files: ['public/sw.js'],
    languageOptions: { globals: { ...globals.serviceworker, AbortController: 'readonly' } },
  },
  {
    ...js.configs.recommended,
    files: ['scripts/**/*.mjs'],
    languageOptions: { globals: globals.node },
  },
)
