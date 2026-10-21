# Website: De AI-kennisbank voor verzekeringsmakelaars

Statische one-pager. Geen build-stap, geen frameworks: alles staat in `index.html`.

## Bestanden

| Bestand | Wat |
|---|---|
| `index.html` | De volledige pagina, inclusief de twee animaties (HTML + CSS + een klein script onderaan) |
| `privacy.html` | Kladversie van het privacybeleid (laten nalezen) |
| `img/` | Foto's van Stefan en Robbe |
| `fonts/` | Geist en Geist Mono (tekst) en Newsreader (titels), zelf gehost (geen Google Fonts nodig, OFL-licentie) |
| `favicon.svg` | Rood bolletje als tab-icoon |
| `og-image.png` | Voorbeeldafbeelding voor LinkedIn en andere links (1200×630) |

## Nog in te vullen (zoek op `[`)

- `[Naam]`: productnaam (navigatie, footer, chatvenster in animatie 2, paginatitel, privacy)
- `og:image`: zet er de volledige URL voor zodra je domein live staat, bv. `https://jouwdomein.be/og-image.png`. LinkedIn heeft een absolute URL nodig.
- Zodra jullie een bedrijf, een domeinmailadres of een LinkedIn-bedrijfspagina hebben: e-mailadressen vervangen in `index.html` en `privacy.html`, en KBO-nummer en adres toevoegen in de footer.
- In `privacy.html`: `[termijn]` (hoe lang jullie contactgegevens bewaren)

## Lokaal bekijken

```bash
python3 -m http.server 8000
# open http://localhost:8000
```

## Online zetten

**GitHub Pages:** de workflow `.github/workflows/pages.yml` publiceert de map `website/` (zonder README en TODO) bij elke push naar `main` of `client-filter` die iets in `website/` wijzigt. Eenmalig instellen: *Settings → Pages → Source: GitHub Actions*. Eigen domein: vul het in onder *Custom domain* en voeg bij je registrar een `CNAME`-record toe naar `robbe111.github.io`.

**Netlify of Cloudflare Pages:** koppel de GitHub-repo; build command leeg laten, publish directory `/`. Daarna je domein toevoegen en de DNS-records volgen die ze tonen. HTTPS komt er automatisch bij.

## De animaties aanpassen

De tijdlijnen staan onderaan in `index.html` in de functies `overzicht(t)` en `chat(t)`. Elk element met `data-cls="sleutel"` krijgt de klasse die de tijdlijn op dat moment teruggeeft (`on`/`off`, ...). Een moment uitstellen = het getal in `on(start, E)` verhogen.

- Animatie 1 duurt 18,8 s, animatie 2 duurt 21 s; ze lopen in een lus.
- Ze spelen alleen af als ze in beeld zijn, en staan stil op een eindbeeld voor wie "minder beweging" aanzet in het besturingssysteem.
