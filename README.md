# Faktúra Renamer - Omega Integrácia

🧾 Automatické premenovanie PDF faktúr s integráciou účtovného SW Omega.

## ✨ Funkcie

- 📄 Načítanie CSV exportu z Omegy
- 🔗 Automatické párovanie podľa externého čísla, KV DPH a sumy
- 🔍 OCR podpora pre naskenované dokumenty
- 👁 Náhľad PDF s možnosťou manuálneho párovania
- 📊 Triedenie Omega záznamov (číslo, suma, partner)
- ☐ Možnosť zahrnúť doklady s nulovou sumou

## 📋 Výstupný formát

```
{typ_dokladu}{interné_číslo}-{externé_číslo}-{pôvodný_názov}.pdf
```

Príklad: `DF302025001-259003485-scan.pdf`

## 🚀 Použitie

1. **Načítaj CSV** z Omegy (export dokladov)
2. **Vyber typy dokladov** (DF, ZDF, DPF...)
3. **Vyber priečinok** s PDF faktúrami
4. **Skenovať a párovať** - automatické párovanie
5. **Manuálne spárovanie** pre nejednoznačné zhody
6. **Premenovať** jednotlivo alebo hromadne

## 🔧 Párovanie

Program páruje PDF s Omega záznamami podľa:
- Externého čísla dokladu
- Čísla KV DPH
- Len číslicovej časti (napr. `25VF051` → `25051`)
- Celkovej sumy (s toleranciou 0.02 EUR)

## 📦 Inštalácia

```bash
pip install pdfplumber pymupdf Pillow pytesseract
```

Pre OCR: [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)

## 📄 Licencia

MIT License
