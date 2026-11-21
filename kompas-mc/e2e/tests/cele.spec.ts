import { expect, test, type Page } from "@playwright/test";
import { A, B } from "../playwright.config";

// Cele rozwojowe (#11): pełny obieg propozycji i wariant, w którym cele ustala tylko przełożony.

async function zaloguj(page: Page, ui: number, login: string) {
  await page.goto(`http://localhost:${ui}/`);
  await page.getByLabel("Login").fill(login);
  await page.getByLabel("Hasło").fill("demo");
  await page.keyboard.press("Enter");
  await expect(page.locator("nav.menu")).toBeVisible();
}

async function otworzCelAnny(page: Page, nazwa: string) {
  await page.locator("nav.menu button.poz", { hasText: "Cele zespołu" }).click();
  await page.getByText("Anna Zielińska-Demo").click();
  const cel = page.locator(".cel", { hasText: nazwa });
  await cel.locator("button.cel-glowa").click();
  return cel;
}

test("pracownik proponuje cel, przełożony odsyła do poprawy, pracownik poprawia, przełożony zatwierdza", async ({ browser }) => {
  const pracownik = await (await browser.newContext()).newPage();
  const przelozony = await (await browser.newContext()).newPage();
  const nazwa = `Prowadzenie spotkań zespołu ${Date.now()}`; // unikalna, gdy serwery są używane ponownie

  await zaloguj(pracownik, A.ui, "oceniany");
  await pracownik.locator("nav.menu button.poz", { hasText: "Twoje cele" }).click();
  await pracownik.getByRole("button", { name: "Dodaj cel" }).click();
  await pracownik.getByLabel("Cel").fill(nazwa);
  await pracownik.getByLabel("Miernik").fill("3 spotkania");
  await pracownik.getByLabel("Termin").fill("30.06.2027");
  await pracownik.getByRole("button", { name: "Wyślij do akceptacji" }).click();
  const mojCel = pracownik.locator(".cel", { hasText: nazwa });
  await expect(mojCel.locator(".status", { hasText: "do akceptacji" })).toBeVisible();

  await zaloguj(przelozony, A.ui, "przelozony1");
  let cel = await otworzCelAnny(przelozony, nazwa);
  await cel.locator(".cel-akcje").getByRole("button", { name: "Odeślij do poprawy", exact: true }).click();
  await cel.getByLabel("Co poprawić?").fill("Dodaj liczbę uczestników do miernika.");
  await cel.locator(".cel-odrzucenie").getByRole("button", { name: "Odeślij do poprawy", exact: true }).click();
  await expect(cel.locator(".status", { hasText: "do poprawy" })).toBeVisible();

  await pracownik.reload();
  await pracownik.locator("nav.menu button.poz", { hasText: "Twoje cele" }).click();
  await mojCel.locator("button.cel-glowa").click();
  await expect(mojCel.locator(".cel-komentarz")).toContainText("Dodaj liczbę uczestników");
  await mojCel.getByRole("button", { name: "Popraw", exact: true }).click();
  await mojCel.getByLabel("Miernik").fill("3 spotkania, min. 5 osób");
  await mojCel.getByRole("button", { name: "Wyślij do akceptacji", exact: true }).click();
  await expect(mojCel.locator(".status", { hasText: "do akceptacji" })).toBeVisible();

  await przelozony.reload();
  cel = await otworzCelAnny(przelozony, nazwa);
  await cel.locator(".cel-akcje").getByRole("button", { name: "Zatwierdź", exact: true }).click();
  await expect(cel.locator(".status", { hasText: "zatwierdzony" })).toBeVisible();
  await expect(cel.locator(".cel-historia li")).toHaveCount(4);
  await expect(cel.locator(".cel-historia li").nth(1)).toContainText("zmiana: miernik");
});

test("przy pracownik_moze_edytowac: false pracownik nie widzi formularza, a cel przełożonego może rozpocząć", async ({ browser }) => {
  const przelozony = await (await browser.newContext()).newPage();
  await zaloguj(przelozony, B.ui, "przelozony1");
  await przelozony.locator("nav.menu button.poz", { hasText: "Cele zespołu" }).click();
  await przelozony.getByText("Anna Zielińska-Demo").click();
  await przelozony.getByRole("button", { name: "Dodaj cel" }).click();
  const nazwa = `Szkolenie z AI Act ${Date.now()}`;
  await przelozony.getByLabel("Cel").fill(nazwa);
  await przelozony.locator("form.cel-formularz").getByRole("button", { name: "Dodaj cel" }).click();
  await expect(przelozony.locator(".cel", { hasText: nazwa }).locator(".status", { hasText: "zatwierdzony" })).toBeVisible();

  const pracownik = await (await browser.newContext()).newPage();
  await zaloguj(pracownik, B.ui, "oceniany");
  await pracownik.locator("nav.menu button.poz", { hasText: "Twoje cele" }).click();
  await expect(pracownik.getByText("Cele ustala przełożony.")).toBeVisible();
  await expect(pracownik.getByRole("button", { name: "Dodaj cel" })).toHaveCount(0);
  const cel = pracownik.locator(".cel", { hasText: nazwa });
  await cel.locator("button.cel-glowa").click();
  await expect(cel.getByRole("button", { name: "Edytuj", exact: true })).toHaveCount(0);
  await cel.getByRole("button", { name: "Rozpocznij realizację", exact: true }).click();
  await expect(cel.locator(".status", { hasText: "w realizacji" })).toBeVisible();
});
