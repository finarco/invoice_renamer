# Faktúra Renamer

🧾 Automatické premenovanie PDF faktúr podľa čísla faktúry s OCR podporou.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## ✨ Funkcie

- 📄 Automatická extrakcia čísla faktúry z PDF
- 🔍 OCR podpora pre naskenované dokumenty
- 👁 Náhľad PDF so zvýraznením nájdeného čísla
- ✏️ Manuálne zadanie čísla ak automatika zlyhá
- 🏷 Premenovanie na formát: `číslo_faktúry-pôvodný_názov.pdf`

## 📸 Screenshot

```
┌─────────────────────────────────────────────────────────────┐
│  📁 Priečinok: C:\Faktury\2025                    [Vybrať] │
├──────────┬─────────────────────┬────────────────────────────┤
│ PDF súbory│    Náhľad PDF      │  Nájdené čísla faktúr     │
│          │                     │                            │
│ scan1.pdf│   ┌───────────┐    │  [x] 2025010076            │
│ scan2.pdf│   │  FAKTÚRA  │    │  [ ] 2059689 (VS)          │
│ scan3.pdf│   │           │    │                            │
│          │   │  ████████ │    │  Manuálne: [___________]   │
│          │   └───────────┘    │                            │
│          │                     │  [✓ PREMENOVAŤ]           │
└──────────┴─────────────────────┴────────────────────────────┘
```

## 🚀 Inštalácia

### 1. Python
Stiahni a nainštaluj z [python.org](https://www.python.org/downloads/)
> ⚠️ Pri inštalácii zaškrtni **"Add Python to PATH"**

### 2. Tesseract OCR (pre naskenované PDF)
Stiahni z [GitHub](https://github.com/UB-Mannheim/tesseract/wiki)
> Pri inštalácii pridaj jazyky: Slovak, Czech

### 3. Python knižnice
```bash
pip install pdfplumber pymupdf Pillow pytesseract
```

Alebo spusti `Instalovat_kniznice.bat`

## 📖 Použitie

### Spustenie
```bash
python faktura_renamer_gui.py
```
Alebo dvojklik na `Spustit_FakturaRenamer.bat`

### Postup
1. Vyber priečinok s PDF faktúrami
2. Program automaticky nájde čísla faktúr
3. Vyber správne číslo alebo zadaj manuálne
4. Klikni "Premenovať" alebo stlač Enter

### Klávesové skratky
| Klávesa | Akcia |
|---------|-------|
| `Enter` | Premenovať |
| `Escape` | Preskočiť |
| `Ctrl+O` | Otvoriť priečinok |

## 📋 Podporované formáty faktúr

| Formát | Príklad |
|--------|---------|
| METRO | `0/0(026)0058/003755` |
| Rok + číslo | `2025010076` |
| S prefixom | `FV2024001` |
| S lomkou | `2024/00123` |
| Variabilný symbol | `1234567890` |

## 🔧 Konfigurácia

### Tesseract v inej ceste
Uprav riadok v `faktura_renamer_gui.py`:
```python
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

## 📁 Súbory

| Súbor | Popis |
|-------|-------|
| `faktura_renamer_gui.py` | Hlavný program (GUI) |
| `faktura_renamer.py` | CLI verzia |
| `Spustit_FakturaRenamer.bat` | Spúšťač pre Windows |
| `Instalovat_kniznice.bat` | Inštalátor knižníc |
| `INSTALACIA.md` | Podrobný návod |

## 🐛 Riešenie problémov

| Problém | Riešenie |
|---------|----------|
| OCR nedostupné | Nainštaluj Tesseract |
| Nenájde číslo | Zadaj manuálne |
| Chyba pri premenovaní | Zavri PDF v inom programe |

## 📄 Licencia

MIT License - voľne použiteľné aj pre komerčné účely.

## 🤝 Prispievanie

Pull requesty sú vítané! Pre väčšie zmeny najprv otvor issue.

---

Vyrobené s ❤️ pre účtovníkov na Slovensku 🇸🇰
