# Agent AI: posty dla firmy instalującej monitoring

Automatycznie generuje 1 propozycję posta z obrazem AI w poniedziałek, środę i piątek około 9:07 czasu Polski. Tekst: Groq. Grafiki: Cloudflare Workers AI FLUX.1 schnell. Trendy: publiczne nagłówki Google News RSS z ostatnich 14 dni. Publikacja: GitHub Pages (HTML), bez automatycznego publikowania na Facebooku/Instagramie.

## Konfiguracja — bez uruchamiania komputera

1. Utwórz konto na https://github.com oraz **publiczne repozytorium** (np. `monitoring-posty`). Prześlij do niego **zawartość** tego folderu, zachowując strukturę `.github/workflows/generate.yml` (folder `.github` jest ukryty w niektórych menedżerach plików). Ustaw domyślną gałąź `main`.
2. Edytuj `config.json` na GitHubie: nazwę, miasto, usługi, pytania klientów i CTA. Nie wpisuj danych osobowych klientów.
3. Utwórz bezpłatny klucz API na https://console.groq.com/keys.
4. W https://dash.cloudflare.com przejdź do Workers AI → Use REST API, utwórz token z uprawnieniami Workers AI i skopiuj Account ID. Zobacz https://developers.cloudflare.com/workers-ai/get-started/rest-api/.
5. Na GitHubie: repozytorium → Settings → Secrets and variables → Actions → New repository secret. Utwórz trzy sekrety: `GROQ_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`. **Nie wklejaj kluczy do plików repozytorium.**
6. GitHub → Settings → Actions → General → Workflow permissions → **Read and write permissions** (o ile to ustawienie jest dostępne). Plik workflow ma również `contents: write`.
7. GitHub → Settings → Pages → Build and deployment → Source: **Deploy from a branch** → Branch: `main`, folder `/docs` → Save. Strona będzie pod adresem `https://TWOJ_LOGIN.github.io/monitoring-posty/` (dla repozytorium o tej nazwie).
8. GitHub → Actions → **Generuj post i grafikę AI** → Run workflow. Pierwsze uruchomienie jest ręczne. Potem harmonogram wykona to samodzielnie.

**Uwaga:** GitHub Pages w tym wariancie jest publiczny. Nie umieszczaj we wpisach prywatnych danych klientów, adresów instalacji, poufnych ofert, haseł ani informacji o rozmieszczeniu kamer u konkretnych klientów.

## Działanie

- Agent pobiera publiczne nagłówki i odnośniki do artykułów o monitoringu z Google News RSS, porównuje je z listą pytań klientów oraz historią postów.
- Wybiera pytanie jeszcze niewykorzystane w ostatnim cyklu, wysyła kontekst do Groq i żąda ustrukturyzowanego posta i promptu graficznego.
- Groq nie uzyskuje pełnej zawartości artykułów, tylko nagłówki. Nie wykonuje niezależnej weryfikacji faktów — tekst wymaga akceptacji człowieka.
- Cloudflare Workers AI tworzy ilustrację AI. W razie problemu z obrazem propozycja tekstowa jest nadal zapisywana i panel wskazuje brak grafiki.
- Wyniki trafiają do `data/posts.json`, grafiki do `docs/images`, a gotowy panel do `docs/index.html`.
- Panel ma przyciski kopiowania tekstu i pobierania grafiki. Nie publikuje postów automatycznie.

## Koszty i limity

GitHub Pages + GitHub Actions w ramach limitów darmowego planu, Groq Free w ramach limitów, Cloudflare Workers AI do 10 000 Neurons/dzień bez opłat według dokumentacji na październik 2026. Nie gwarantujemy nieograniczonego ani niezmiennego darmowego dostępu. GitHub Actions może uruchomić zadanie z opóźnieniem, a schemat harmonogramu może zostać wyłączony po długim okresie bezczynności w repozytorium. Nowe wpisy i grafiki zajmują miejsce w repozytorium.

## Test lokalny (opcjonalnie)

`pip install -r requirements.txt`

Ustaw środowiskowe `GROQ_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, potem `python agent.py`.

## Zmiany

- Harmonogram: `.github/workflows/generate.yml`
- Pytania klientów, zakres usług, model Groq: `config.json`
- Trendy: `news_queries` w `config.json`
- Wymuszenie drugiego wpisu tego samego dnia: uruchom lokalnie z `FORCE_NEW=1`; na GitHubie domyślnie jeden wpis dziennie, aby zapobiegać duplikatom.
