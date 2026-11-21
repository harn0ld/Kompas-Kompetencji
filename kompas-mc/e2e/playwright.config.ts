import { defineConfig, devices } from "@playwright/test";

// Testy interfejsu wersji MC. Dwie pary serwerów na świeżych bazach:
// A – konfiguracja domyślna (pracownik proponuje cele), B – cele-bez-edycji.yaml (tylko przełożony).
// Porty domyślnie jak w README (A: API 8002, interfejs 5174; B: 8003, 5175); zmienne E2E_* je zmieniają.
// E2E_REUSE=1 używa już uruchomionych serwerów; PW_CHROMIUM wskazuje własną przeglądarkę.
const port = (nazwa: string, domyslny: number) => Number(process.env[nazwa] ?? domyslny);
export const A = { api: port("E2E_API_A", 8002), ui: port("E2E_UI_A", 5174) };
export const B = { api: port("E2E_API_B", 8003), ui: port("E2E_UI_B", 5175) };
const reuse = !!process.env.E2E_REUSE;
const dane = (nazwa: string) => `KOMPAS_MC_DANE=$PWD/.dane/$(date +%s)-${nazwa}`;

export default defineConfig({
  testDir: "./tests",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
    launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
  },
  webServer: [
    {
      command: `${dane("a")} KOMPAS_MC_PORT=${A.api} uv run --project ../backend kompas-mc`,
      url: `http://127.0.0.1:${A.api}/api/zdrowie`,
      timeout: 120_000,
      reuseExistingServer: reuse,
    },
    {
      command: `KOMPAS_MC_API=http://127.0.0.1:${A.api} npm --prefix ../frontend run dev -- --port ${A.ui}`,
      url: `http://localhost:${A.ui}`,
      timeout: 120_000,
      reuseExistingServer: reuse,
    },
    {
      command: `${dane("b")} KOMPAS_MC_CELE=$PWD/cele-bez-edycji.yaml KOMPAS_MC_PORT=${B.api} uv run --project ../backend kompas-mc`,
      url: `http://127.0.0.1:${B.api}/api/zdrowie`,
      timeout: 120_000,
      reuseExistingServer: reuse,
    },
    {
      command: `KOMPAS_MC_API=http://127.0.0.1:${B.api} npm --prefix ../frontend run dev -- --port ${B.ui}`,
      url: `http://localhost:${B.ui}`,
      timeout: 120_000,
      reuseExistingServer: reuse,
    },
  ],
});
