import js from "@eslint/js"
import globals from "globals"
import css from "@eslint/css"
import neostandard from 'neostandard'
import { defineConfig } from "eslint/config"

export default defineConfig([
  {
    ignores: [
      "**/node_modules/",
      "**/venv/",
      "**/env/",
      "**/*.py",
      "**/*.html",
      "**/migrations/",
      "**/externals/",
      "/static/",
      "dist/"
    ]
  },

  ...neostandard(),

  { 
    files: ["**/*.{js,mjs,cjs}"],
    plugins: { js },
    extends: ["js/recommended"], languageOptions: { globals: globals.browser }
  }
])
