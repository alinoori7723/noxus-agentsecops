import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
export default tseslint.config({ ignores: ["dist/**", "coverage/**", "node_modules/**"] }, js.configs.recommended, tseslint.configs.recommended, {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: { globals: globals.browser },
    plugins: { "react-hooks": reactHooks },
    rules: {
            "no-empty": ["error", { allowEmptyCatch: true }],
        "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "error",
    },
}, {
    files: ["*.{js,ts}"],
    languageOptions: { globals: globals.node },
});
